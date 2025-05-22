import os
import re
import hashlib
import sqlite3
from datetime import datetime
from collections import defaultdict
import json
from typing import List, Dict, Any, Optional, Set, Tuple

from langchain_openai.embeddings import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_text_splitters import RecursiveCharacterTextSplitter

class ObsidianVault:
    """Advanced Obsidian vault processor"""
    
    def __init__(self, 
                 vault_path: str, 
                 persistent_path: str,
                 llm_model: str = "gpt-4.1-nano",
                 embedding_model: str = "text-embedding-3-small" # better, more expensive: "text-embedding-ada-002"
                 ):
        """Initialize the Obsidian processor
        
        Args:
            vault_path: Path to the Obsidian vault
            db_path: Path to the SQLite database for tracking changes
            llm_model: LLM model to use for processing
            embedding_model: Embedding model to use for retrieval
            api_key: OpenAI API key (will use environment variable if not provided)
        """
        self.vault_path = vault_path
        self.db_path = os.path.join(persistent_path, 'obsidian_index.db')

        curr_path = os.path.dirname(os.path.abspath(__file__))
        self.faiss_index_path = os.path.join(curr_path, '..', persistent_path, 'faiss_index')
            
        # Initialize embedding model
        self.embeddings = OpenAIEmbeddings(model=embedding_model)
        
        # Initialize storage and indexes
        self.setup_database()
        self.vector_store = None
        self.link_processor = ObsidianLinkProcessor(vault_path)

        # Initialize text splitter for chunking
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1500,  # Adjust this based on your content and embedding model limits
            chunk_overlap=150, # Ensures context is maintained across chunks
            length_function=len, 
            separators=["\n\n", "\n", " ", ""] 
        )
        
    def setup_database(self):
        """Set up SQLite database to track files and their hashes"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS files (
            path TEXT PRIMARY KEY,
            hash TEXT,
            last_indexed TEXT
        )
        ''')
        
        # Table for processed outputs
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS processed_outputs (
            id TEXT PRIMARY KEY,
            input_files TEXT,  -- JSON array of file paths
            output_type TEXT,  -- flashcard, summary, etc.
            content TEXT,
            created_at TEXT
        )
        ''')
        conn.commit()
        conn.close()
        
    def get_file_hash(self, file_path):
        """Calculate MD5 hash of a file to detect changes"""
        with open(file_path, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()
            
    def find_changed_files(self):
        """Identify new or modified markdown files"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        changed_files = []
        for root, _, files in os.walk(self.vault_path):
            for file in files:
                if file.endswith('.md'):
                    file_path = os.path.join(root, file)
                    current_hash = self.get_file_hash(file_path)
                    
                    cursor.execute("SELECT hash FROM files WHERE path = ?", (file_path,))
                    result = cursor.fetchone()
                    
                    if not result or result[0] != current_hash:
                        changed_files.append(file_path)
        
        conn.close()
        return changed_files
        
    def update_file_record(self, file_path):
        """Update the database record for a file"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        file_hash = self.get_file_hash(file_path) if os.path.exists(file_path) else None
        cursor.execute(
            "INSERT OR REPLACE INTO files VALUES (?, ?, ?)",
            (file_path, file_hash, datetime.now().isoformat())
        )
        conn.commit()
        conn.close()
        
    def update_index(self):
        """Update the vector store with changed files"""
        self.link_processor.build_link_graph()
        
        changed_files = self.find_changed_files()
        
        total_indexed_docs = 0
        
        if self.vector_store is None:
            try:
                self.vector_store = FAISS.load_local(self.faiss_index_path, self.embeddings, allow_dangerous_deserialization=True)
                print(f"Loaded existing FAISS index from {self.faiss_index_path}.")
            except Exception as e:
                print(f"Could not load FAISS index from {self.faiss_index_path}. Creating a new one.")
                self.vector_store = None 

        # We'll process all changed files, but add their *chunks* in smaller batches to OpenAI
        all_new_chunks = []
        
        for file_path in changed_files:
            docs = self.process_file_with_links(file_path)
            all_new_chunks.extend(docs) # 'docs' are already chunks here
            self.update_file_record(file_path) # Update database for each file as it's processed

        # --- IMPORTANT CHANGE START ---
        # Now, take all the collected chunks and batch them for embedding
        # This batch size should be significantly smaller than the 'file batch size'
        # to ensure the total tokens sent to OpenAI stays under 300,000.
        # A batch_size of ~100-500 chunks is usually safe depending on chunk_size.
        # Let's set a 'chunk_api_batch_size' that limits the number of individual chunks
        # sent in one API call for embeddings.
        chunk_api_batch_size = 200 # Adjust this value based on your chunk_size and OpenAI limit
                                   # Example: if chunk_size=1500, then 200 chunks = 300,000 tokens
                                   # This value directly affects the API call size.
        
        for i in range(0, len(all_new_chunks), chunk_api_batch_size):
            batch_of_chunks = all_new_chunks[i:i + chunk_api_batch_size]
            
            if not batch_of_chunks:
                continue # Skip if batch is empty

            texts_to_embed = [doc["content"] for doc in batch_of_chunks]
            metadatas_for_embed = [doc["metadata"] for doc in batch_of_chunks]

            try:
                if self.vector_store is None:
                    # If this is the very first batch and vector store is None, initialize it
                    self.vector_store = FAISS.from_texts(
                        texts_to_embed, self.embeddings, metadatas=metadatas_for_embed
                    )
                else:
                    self.vector_store.add_texts(texts_to_embed, metadatas=metadatas_for_embed)
                
                total_indexed_docs += len(batch_of_chunks)
                print(f"Indexed {len(batch_of_chunks)} chunks in current API batch. Total: {total_indexed_docs}")

            except Exception as e:
                print(f"Error during embedding API call for a batch of chunks: {e}")
                # You might want to log 'batch_of_chunks' here or implement retry logic
                # For now, we'll just re-raise to see the full traceback if it persists
                raise 

        # --- IMPORTANT CHANGE END ---

        if self.vector_store:
            self.vector_store.save_local(self.faiss_index_path)
            print(f"FAISS index saved to {self.faiss_index_path}")
            
        return total_indexed_docs
    
    def process_file_with_links(self, file_path):
        """Process a markdown file with link awareness"""
        note_name = os.path.basename(file_path).replace('.md', '')
        
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        links = self.link_processor.extract_links(content)
        backlinks = list(self.link_processor.backlinks.get(note_name, []))
        
        frontmatter = {}
        if content.startswith('---'):
            end_idx = content.find('---', 3)
            if end_idx != -1:
                frontmatter_text = content[3:end_idx].strip()
                for line in frontmatter_text.split('\n'):
                    if ':' in line:
                        key, value = line.split(':', 1)
                        frontmatter[key.strip()] = value.strip()
                
                content = content[end_idx+3:].strip()
        
        # Use the initialized text splitter to chunk the content
        chunks = self.text_splitter.split_text(content)
        
        docs = []
        for i, chunk in enumerate(chunks):
            chunk_links = self.link_processor.extract_links(chunk)
            
            docs.append({
                "content": chunk,
                "metadata": {
                    "source": file_path,
                    "chunk_id": i,
                    "title": note_name,
                    "links": chunk_links,
                    "all_note_links": links,
                    "backlinks": backlinks,
                    "frontmatter": frontmatter
                }
            })
        
        return docs
    
    def record_processed_output(self,
                                output_id_prefix: str,
                                input_files: List[str],
                                output_type: str,
                                content: str,
                                status: str = "success", # Optional: for more detailed logging
                                error_message: Optional[str] = None # Optional
                            ) -> Optional[str]:
        """
        Records a processed output (typically from an LLM) into the SQLite database.

        Args:
            output_id_prefix: A prefix for the generated ID (e.g., "summary", "flashcards_llm").
                            A timestamp will be appended to ensure uniqueness.
            input_files: A list of source file paths that were used as input.
            output_type: A string describing the type of output (e.g., "llm_summary", "llm_flashcards").
            content: The actual generated content.
            status: Optional status of the processing (e.g., "success", "failure").
            error_message: Optional error message if status is not "success".

        Returns:
            The generated unique ID for the record, or None if an error occurred.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        # Generate a more unique ID, perhaps including microseconds
        unique_id = f"{output_id_prefix}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
        created_at_iso = datetime.now().isoformat()

        try:
            # Let's assume your processed_outputs table might evolve to include status/error
            # If not, you can simplify the INSERT and remove these from the table definition
            # For now, let's stick to your original table structure for the main fields:
            # id, input_files, output_type, content, created_at

            cursor.execute(
                """
                INSERT INTO processed_outputs (id, input_files, output_type, content, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    unique_id,
                    json.dumps(input_files),
                    output_type,
                    content, # Could be error_message if status is failure and content is not applicable
                    created_at_iso
                )
            )
            conn.commit()
            print(f"Successfully recorded processed output: {unique_id}")
            return unique_id
        except sqlite3.Error as e:
            print(f"SQLite error while recording processed output '{unique_id}': {e}")
            # You might want to log this error more formally
            return None
        finally:
            conn.close()
    
    def fetch_note_paths(self, where_clause=None, where_args=()):
        """
        Fetch a list of note paths from the database based on an optional WHERE clause

        Args:
            where_clause: Optional SQL WHERE clause to filter the results
            where_args: Arguments to be used in the WHERE clause

        Returns:
            A list of paths to notes that match the WHERE clause
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        query = "SELECT path FROM files"
        if where_clause:
            query += " WHERE " + where_clause
        cursor.execute(query, where_args)
        note_paths = [row[0] for row in cursor.fetchall()]
        conn.close()
        return note_paths
    
    

    ####################################################
    # General Processing Methods
    ####################################################

    def vector_query(self, query_text, top_k=5):
        """Search the vector store for relevant content"""
        if self.vector_store is None:
            try:
                self.vector_store = FAISS.load_local(self.faiss_index_path, self.embeddings, allow_dangerous_deserialization=True)
            except:
                print("No index found. Please run update_index() first.")
                return []
            
        results = self.vector_store.similarity_search(query_text, k=top_k)
        
        # Format results for display
        formatted_results = []
        for doc in results:
            formatted_results.append({
                "content": doc.page_content,
                "source": doc.metadata["source"],
                "title": doc.metadata["title"],
                "similarity": doc.metadata.get("score", "Unknown")
            })
            
        return formatted_results
    
    def get_note_content(self, note_path):
        """Get the content of a note"""
        with open(note_path, 'r', encoding='utf-8') as f:
            return f.read()
    
    def save_note(self, note_path, content):
        """Save content to a note"""
        with open(note_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        # Update the file record
        self.update_file_record(note_path)
    
    def create_new_note(self, title, content, folder=""):
        """Create a new note in the vault"""
        # Sanitize title for filename
        safe_title = title.replace('/', '-').replace('\\', '-')
        
        if folder:
            os.makedirs(os.path.join(self.vault_path, folder), exist_ok=True)
            note_path = os.path.join(self.vault_path, folder, f"{safe_title}.md")
        else:
            note_path = os.path.join(self.vault_path, f"{safe_title}.md")
        
        self.save_note(note_path, content)
        return note_path
    
    def remove_note(self, note_path):
        """Remove a note from the vault"""
        os.remove(note_path)
        
        # Update the file record
        self.update_file_record(note_path)

    
class ObsidianLinkProcessor:
    """Process Obsidian links and build link graph"""
    
    def __init__(self, vault_path):
        self.vault_path = vault_path
        self.link_graph = defaultdict(set)  # Maps note -> set of linked notes
        self.backlinks = defaultdict(set)   # Maps note -> set of notes linking to it
        
    def extract_links(self, content):
        """Extract all [[wiki-style]] links from content"""
        # Match standard [[links]] and [[links|with alt text]]
        pattern = r'\[\[(.*?)(?:\|.*?)?\]\]'
        return [match.group(1) for match in re.finditer(pattern, content)]
    
    def build_link_graph(self):
        """Build a graph of all links in the vault"""
        self.link_graph = defaultdict(set)
        self.backlinks = defaultdict(set)
        
        for root, _, files in os.walk(self.vault_path):
            for file in files:
                if file.endswith('.md'):
                    file_path = os.path.join(root, file)
                    note_name = os.path.basename(file_path).replace('.md', '')
                    
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    links = self.extract_links(content)
                    self.link_graph[note_name] = set(links)
                    
                    # Build backlinks
                    for link in links:
                        self.backlinks[link].add(note_name)



# Example usage
if __name__ == "__main__":
    
    # Set paths
    curr_path = os.path.dirname(os.path.abspath(__file__))
    vault_path = f"{curr_path}/../persistant/test_vault"

    relative_persistant_path = "./persistant"
    
    # Initialize the processor
    processor = ObsidianVault(vault_path, relative_persistant_path)
    
    # Update the index
    num_docs = processor.update_index()
    print(f"Indexed {num_docs} new/changed documents")


    # Example: query on indexed documents
    if False:
        # Test 1: Simple Keyword Query (Retrieval Only)
        print("\n--- Test 1: Simple Keyword Query ---")
        query_term = "Yann LeCun" # Replace with a term you know is in your notes
        results = processor.vector_query(query_term, top_k=3) # Get top 3 most relevant chunks

        if results:
            print(f"Results for '{query_term}':")
            for i, res in enumerate(results):
                print(f"  Result {i+1}:")
                print(f"    Source: {res['source']}")
                print(f"    Title: {res['title']}")
                print(f"    Content (first 200 chars): {res['content'][:200]}...")
                print("-" * 20)
        else:
            print(f"No results found for '{query_term}'.")

