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

from vault.vault import LinkProcessor, Vault

class ObsidianVault(Vault):
    """Advanced Obsidian vault processor"""
    
    def __init__(self, 
                 vault_path: str, 
                 persistent_path: str,
                 embedding_model: str = "text-embedding-3-small",
                 ):
        super().__init__(
            vault_path=vault_path,
            persistent_path=persistent_path,
            link_processor=ObsidianLinkProcessor(vault_path=vault_path),
            embedding_model=embedding_model
        )
    
class ObsidianLinkProcessor(LinkProcessor):
    """Process Obsidian links and build link graph"""
    
    def extract_links(self, content):
        """Extract all [[wiki-style]] links from content"""
        # Match standard [[links]] and [[links|with alt text]]
        pattern = r'\[\[(.*?)(?:\|.*?)?\]\]'
        return [match.group(1) for match in re.finditer(pattern, content)]
    


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

