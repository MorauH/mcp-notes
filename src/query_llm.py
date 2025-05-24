import os
from datetime import datetime

from langchain_openai.chat_models import ChatOpenAI
from langchain.schema import HumanMessage, SystemMessage

from vault_obsidian import ObsidianVault
from vault import Vault


class LLMVaultProcessor:
    def __init__(self, vault: Vault, llm_model: str = "gpt-4.1-nano"):
        """Initialize the LLM processor
        
        Args:
            vault: Vault object to operate on
            llm_model: LLM model to use for processing
        """

        self.vault = vault

        # Initialize LLM
        self.llm = ChatOpenAI(model_name=llm_model, temperature=0.2)
    

    def invoke_llm(self, messages):
        """Process content with LLM"""
        return self.llm.invoke(messages)

    def generate_flashcards(self, note_paths, output_folder="Flashcards"):
        """Generate flashcards from notes
        
        Args:
            note_paths: List of paths to notes to generate flashcards from
            output_folder: Folder to save flashcards in
            
        Returns:
            Path to the generated flashcards note
        """
        # Collect content from all notes
        all_content = []
        for path in note_paths:
            all_content.append(self.vault.get_note_content(path))
        
        combined_content = "\n\n---\n\n".join(all_content)
        
        # Prepare messages for LLM
        messages = [
            SystemMessage(content="""You are an expert flashcard creator. 
            Extract key concepts from the provided notes and create effective flashcards.
            Each flashcard should have a question on the front and a concise answer on the back.
            Format each flashcard as:
            
            [Question text]
            ?
            [Answer text]
                          
            Do not include any other text or letters in the flashcards.
            
            Create 5-15 flashcards depending on the content density."""),
            HumanMessage(content=f"Please create flashcards from the following notes:\n\n{combined_content}")
        ]
        
        # Generate flashcards
        response = self.invoke_llm(messages)
        
        # Create a filename based on the source notes
        source_names = [os.path.basename(path).replace('.md', '') for path in note_paths]
        if len(source_names) > 2:
            filename = f"{source_names[0]}_and_others_flashcards"
        else:
            filename = "_".join(source_names) + "_flashcards"
        
        # Add frontmatter with source notes
        frontmatter = "---\n"
        frontmatter += "type: flashcards\n"
        frontmatter += f"sources: {', '.join(source_names)}\n"
        frontmatter += f"created: {datetime.now().strftime('%Y-%m-%d')}\n"
        frontmatter += "---\n\n"
        frontmatter += f"#flashcards/{filename}\n".replace(' ', '_')
        
        content = frontmatter + response.content
        
        # Save to a new note
        flashcard_path = self.vault.create_new_note(filename, content, folder=output_folder)
        
        # Record operation in database
        self.vault.record_processed_output(
            output_id_prefix="flashcards", 
            input_files=note_paths, 
            output_type="flashcards", 
            content=content
        )
        
        return flashcard_path
    
    def restructure_note(self, note_path, instructions):
        """Restructure a note based on instructions
        
        Args:
            note_path: Path to the note to restructure
            instructions: Instructions for restructuring (e.g., "organize by topic",
                         "add headings", "extract key points", etc.)
                         
        Returns:
            Path to the restructured note
        """
        # Get note content
        content = self.vault.get_note_content(note_path)
        note_name = os.path.basename(note_path).replace('.md', '')
        
        # Prepare messages for LLM
        messages = [
            SystemMessage(content=f"""You are an expert note organizer and restructurer.
            Restructure the provided note according to the user's instructions.
            Preserve all important information from the original note.
            Maintain existing links and formatting where appropriate.
            If the note has frontmatter (YAML between --- lines at the top), preserve it unless specifically instructed to modify it."""),
            HumanMessage(content=f"Instructions: {instructions}\n\nNote content:\n\n{content}")
        ]
        
        # Generate restructured note
        response = self.invoke_llm(messages)
        
        # Create a new note with the restructured content
        restructured_path = self.vault.create_new_note(
            f"{note_name}_restructured", 
            response.content,
            folder="Restructured"
        )

        # record to database
        self.vault.record_processed_output(
            output_id_prefix="restructure",
            input_files=[note_path],
            output_type="restructure",
            content=response.content
        )
        
        return restructured_path
    
    def add_context(self, note_path, context_type="references"):
        """Add context to a note
        
        Args:
            note_path: Path to the note to add context to
            context_type: Type of context to add ("references", "examples", "background", etc.)
            
        Returns:
            Path to the enhanced note
        """
        # Get note content
        content = self.vault.get_note_content(note_path)
        note_name = os.path.basename(note_path).replace('.md', '')
        
        # Find relevant documents
        results = self.vault.vector_query(content, top_k=10)
        
        # Get content of related notes
        related_content = []
        for result in results:
            if result["source"] != note_path:  # Skip the source note itself
                related_content.append({
                    "title": result["title"],
                    "content": result["content"],
                    "source": result["source"]
                })
        
        # Format related content for LLM
        related_text = "\n\n".join([f"## {r['title']}\n{r['content']}" for r in related_content[:5]])
        
        # Prepare messages for LLM
        messages = [
            SystemMessage(content=f"""You are an expert at enhancing notes with additional context.
            For the provided note, add {context_type} based on the related notes provided.
            Integrate the new context seamlessly with the original content.
            Add clear headings to separate original content from added context.
            Preserve all links and formatting from the original note."""),
            HumanMessage(content=f"Original note:\n\n{content}\n\nRelated notes to draw context from:\n\n{related_text}")
        ]
        
        # Generate enhanced note
        response = self.invoke_llm(messages)
        
        # Create a new note with the enhanced content
        enhanced_path = self.create_new_note(
            f"{note_name}_with_{context_type}", 
            response.content,
            folder="Enhanced"
        )

        # record in database
        self.vault.record_processed_output(
            output_id_prefix="context",
            input_files=[note_path],
            output_type="context",
            content=response.content
        )
        
        return enhanced_path
    
    def summarize_notes(self, note_paths, summary_type="concise"):
        """Create a summary of one or more notes
        
        Args:
            note_paths: List of paths to notes to summarize
            summary_type: Type of summary to create ("concise", "detailed", "bullet_points")
            
        Returns:
            Path to the summary note
        """
        # Collect content from all notes
        all_content = []
        for path in note_paths:
            all_content.append(self.vault.get_note_content(path))
        
        combined_content = "\n\n---\n\n".join(all_content)
        
        # Prepare messages for LLM
        messages = [
            SystemMessage(content=f"""You are an expert note summarizer.
            Create a {summary_type} summary of the provided notes.
            Capture all key concepts, arguments, and conclusions.
            Organize the summary with clear headings and structure.
            For concise summaries, aim for 1/4 the length of the original.
            For detailed summaries, aim for 1/2 the length of the original.
            For bullet point summaries, use a hierarchical bullet point structure."""),
            HumanMessage(content=f"Notes to summarize:\n\n{combined_content}")
        ]
        
        # Generate summary
        response = self.invoke_llm(messages)
        
        # Create a filename based on the source notes
        source_names = [os.path.basename(path).replace('.md', '') for path in note_paths]
        if len(source_names) > 2:
            filename = f"{source_names[0]}_and_others_summary"
        else:
            filename = "_".join(source_names) + "_summary"
        
        # Create a new note with the summary
        summary_path = self.vault.create_new_note(
            filename, 
            response.content,
            folder="Summaries"
        )
        
        # record to database
        self.vault.record_processed_output(
            output_id_prefix="summary",
            input_files=note_paths,
            output_type="summary",
            content=response.content
        )
        
        return summary_path
    
    def summarize_topic_from_notes(self, topic: str, include_extended_context: bool = False, output_folder: str = "Summaries"):
        """
        Generates a summary for a given topic by querying existing notes.
        Allows for inclusion of extended context from the LLM, clearly labeled.

        Args:
            topic: The topic to summarize.
            include_extended_context: If True, the LLM is allowed to provide
                                      additional context beyond the provided notes,
                                      but it must clearly label such sections.
                                      If False, the LLM will strictly answer from
                                      the provided notes.
            output_folder: The subfolder within the vault to save the summary note.

        Returns:
            Path to the created summary note.
        """
        # Find relevant documents based on the topic
        # Increased top_k to get more context for a comprehensive summary
        results = self.vault.vector_query(topic, top_k=15) 
        
        # Get content of related notes
        related_content = []
        source_paths = [] # To store paths for database record
        for result in results:
            related_content.append({
                "title": result["title"],
                "content": result["content"],
                "source": result["source"]
            })
            source_paths.append(result["source"])
        
        # Format related content for LLM
        # If no related content, provide a fallback message
        if related_content:
            context_text = "\n\n".join([f"## From: [[{r['title']}]]\n{r['content']}" for r in related_content])
        else:
            context_text = "No direct notes found on this topic in your vault. The summary will be based on general knowledge if extended context is allowed."

        # Prepare messages for LLM
        system_message_content = f"""You are an expert summarizer and knowledge synthesizer.
        Your task is to create a comprehensive summary on the topic: "{topic}".
        
        You will be provided with relevant notes from the user's personal Obsidian vault.
        
        Guidelines:
        - Structure the summary with clear headings and subheadings (e.g., Markdown #, ##, ###).
        - Include key concepts, definitions, main arguments, and relevant examples.
        - Ensure the summary is coherent, well-organized, and easy to understand.
        - Where information is directly from the provided notes, you may optionally reference the source note using obsidian wikilinks: [[Note Title]]. Format: [[Note1_Title]].
        """
        
        if include_extended_context:
            system_message_content += """
        - **IMPORTANT**: You are allowed to include additional, general knowledge or extended context if it significantly enhances the summary.
          However, **ANY** information that is *not* directly from the provided notes MUST be clearly labeled under a section like "### Extended Context" or "### General Knowledge" to distinguish it from the vault's content.
        """
        else:
            system_message_content += """
        - **CRITICAL**: Strictly limit your summary to the information found ONLY within the provided notes. Do NOT introduce any external knowledge or make assumptions beyond the given context. If the provided notes do not contain enough information to summarize the topic, state that clearly.
        """

        messages = [
            SystemMessage(content=system_message_content),
            HumanMessage(content=f"Please summarize the topic: '{topic}'\n\nProvided Notes:\n\n{context_text}")
        ]
        
        # Generate summary
        print(f"Generating summary for topic: '{topic}'...")
        response = self.invoke_llm(messages)
        
        # Create a filename for the new note
        filename = f"{topic.replace(' ', '_')}_Summary"
        
        # Add frontmatter to the summary note
        frontmatter = "---\n"
        frontmatter += "type: summary\n"
        frontmatter += f"topic: {topic}\n"
        frontmatter += f"created: {datetime.now().strftime('%Y-%m-%d')}\n"
        frontmatter += f"sources: {', '.join(set(source_paths)) if source_paths else 'No direct sources'}\n"
        frontmatter += "---\n\n"
        
        content = frontmatter + response.content
        
        # Save to a new note
        summary_note_path = self.vault.create_new_note(filename, content, folder=output_folder)
        
        # record to database
        self.vault.record_processed_output(
            output_id_prefix="summary",
            input_files=source_paths,
            output_type="summary",
            content=response.content
            
        )
        
        print(f"Topic summary for '{topic}' created at: {summary_note_path}")
        return summary_note_path

    def generate_topic_clusters(self, note_paths=None, num_clusters=5, content_limit=500, notes_limit=50):
        """Generate topic clusters from notes
        
        Args:
            note_paths: List of paths to notes to cluster (if None, use all indexed notes)
            num_clusters: Number of clusters to create
            
        Returns:
            Path to the topic clusters note
        """
        # If no note paths provided, get all indexed notes
        if note_paths is None:
            note_paths = self.vault.fetch_note_paths()
        
        # Collect title and content for each note
        notes = []
        for path in note_paths:
            title = os.path.basename(path).replace('.md', '')
            content = self.get_note_content(path)
            notes.append({
                "title": title,
                "content": content[:content_limit],  # Limit content for processing
                "path": path
            })
        
        # Format notes for LLM
        notes_text = "\n\n".join([f"## {n['title']}\n{n['content']}" for n in notes[:notes_limit]])
        
        # Prepare messages for LLM
        messages = [
            SystemMessage(content=f"""You are an expert at organizing notes into topic clusters.
            Review the provided notes and organize them into {num_clusters} distinct topic clusters.
            For each cluster:
            1. Provide a descriptive name
            2. List the notes that belong to that cluster using Obsidian wikilinks. Format: [[Note1_Title]]
            3. Provide a brief description of what unifies the cluster
            
            Format your response with markdown, using headings for each cluster.
            If a note could belong to multiple clusters, assign it to the most relevant one."""),
            HumanMessage(content=f"Notes to organize:\n\n{notes_text}")
        ]
        
        # Generate clusters
        response = self.invoke_llm(messages)
        
        # Create a new note with the clusters
        clusters_path = self.create_new_note(
            f"Topic_Clusters_{datetime.now().strftime('%Y%m%d')}", 
            response.content,
            folder="Topic Clusters"
        )

        # record in database
        source_paths = [n["path"] for n in notes]
        self.vault.record_processed_output(
            output_id_prefix="clusters",
            input_files=source_paths,
            output_type="topic_clusters",
            content=response.content
        )
        
        return clusters_path


# Example usage
if __name__ == "__main__":
    
    # Set paths
    curr_path = os.path.dirname(os.path.abspath(__file__))
    vault_path = f"{curr_path}/../persistant/test_vault"

    relative_persistant_path = "./persistant"
    
    # Initialize the vault
    vault = ObsidianVault(vault_path, relative_persistant_path)
    
    # Update the index
    num_docs = vault.update_index()
    print(f"Indexed {num_docs} new/changed documents")

    # Initialize LLM Vault Processor
    llm_processor = LLMVaultProcessor(vault=vault, llm_model="gpt-4.1-nano")

    # Example: query on indexed documents
    if False:
        # Test 1: Simple Keyword Query (Retrieval Only)
        print("\n--- Test 1: Simple Keyword Query ---")
        query_term = "Yann LeCun" # Replace with a term you know is in your notes
        results = vault.vector_query(query_term, top_k=3) # Get top 3 most relevant chunks

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


    # Example: generate flashcards
    if False:
        note_paths = [
            os.path.join(vault_path, "Synaptic pruning in adolescent brains.md")
        ]
        flashcard_path = llm_processor.generate_flashcards(note_paths)
        print(f"Flashcards created at: {flashcard_path}")

    # Example: Summarize all notes on topic
    if False:
        summary_path_strict = llm_processor.summarize_topic_from_notes(
            topic="Machine Learning",
            include_extended_context=True,   # Optional: include extended context (Info not present in notes)
            #output_folder="valut_subdir" 
        )
        print(f"Summary created at: {summary_path_strict}")

    
    # Example: Restructure a note
    if False:
        note_path = os.path.join(vault_path, "Lex Fridman - Yann LeCun.md")
        instructions = "Organize this note by topics, add clear headings, and create a table of contents at the top"
        restructured_path = llm_processor.restructure_note(note_path, instructions)
        print(f"Restructured note created at: {restructured_path}")