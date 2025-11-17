# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Simple File Search Tool - Searches pre-indexed documents

This tool searches documents that were pre-uploaded using setup_file_store.py
"""

import os
import json
from pathlib import Path
from typing import Dict, Any
from google import genai
from google.genai import types
from google.adk.tools import FunctionTool, ToolContext


def load_file_store_config() -> Dict[str, Any]:
    """Load the file search store configuration"""
    config_path = Path(__file__).parent.parent / 'file_store_config.json'
    
    if not config_path.exists():
        return {
            'error': True,
            'message': 'No file store configured. Please run setup_file_store.py first.'
        }
    
    with open(config_path, 'r') as f:
        return json.load(f)


def search_documents(query: str, tool_context: ToolContext) -> Dict[str, Any]:
    """
    Search through pre-indexed documents using semantic search.
    
    This tool searches documents that were uploaded and indexed using the 
    setup_file_store.py script. It uses Gemini's File Search capability to 
    find relevant information and answer questions.
    
    Args:
        query: The search query or question to find information about in the documents
        tool_context: The tool context (automatically provided by ADK)
    
    Returns:
        A dictionary containing:
        - status: "success" or "error"
        - answer: The answer found in the documents
        - sources: List of source document names where information was found
        - query: The original query
        - message: Error message if status is "error"
    """
    
    # Load configuration
    config = load_file_store_config()
    
    if config.get('error'):
        return {
            "status": "error",
            "message": config['message'],
            "answer": "",
            "sources": [],
            "query": query
        }
    
    store_name = config.get('file_search_store_name')
    indexed_files = config.get('uploaded_files', [])
    
    if not store_name:
        return {
            "status": "error",
            "message": "File store name not found in configuration",
            "answer": "",
            "sources": [],
            "query": query
        }
    
    try:
        # Initialize Gemini client
        # Use FILE_SEARCH_API_KEY if set, otherwise fall back to GOOGLE_API_KEY
        api_key = os.getenv('FILE_SEARCH_API_KEY') or os.getenv('GOOGLE_API_KEY')
        if not api_key:
            return {
                "status": "error",
                "message": "Neither FILE_SEARCH_API_KEY nor GOOGLE_API_KEY found in environment",
                "answer": "",
                "sources": [],
                "query": query
            }
        
        # Log which key is being used (without revealing the key)
        key_source = "FILE_SEARCH_API_KEY" if os.getenv('FILE_SEARCH_API_KEY') else "GOOGLE_API_KEY"
        print(f"[FileSearch] Using API key from: {key_source}")
        
        client = genai.Client(api_key=api_key)
        
        print(f"[FileSearch] Searching in store: {store_name}")
        print(f"[FileSearch] Query: {query}")
        
        # Perform file search
        # Note: Using gemini-2.5-flash as it's required for file search
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=query,
            config=types.GenerateContentConfig(
                tools=[types.Tool(
                    file_search=types.FileSearch(
                        file_search_store_names=[store_name]
                    )
                )]
            )
        )
        
        # Extract grounding sources
        sources = []
        if response.candidates and response.candidates[0].grounding_metadata:
            grounding = response.candidates[0].grounding_metadata
            sources = [
                c.retrieved_context.title 
                for c in grounding.grounding_chunks 
                if hasattr(c, 'retrieved_context') and hasattr(c.retrieved_context, 'title')
            ]
        
        print(f"[FileSearch] Found {len(sources)} source(s)")
        
        # Store in session state for debugging
        tool_context.state['last_search'] = {
            "query": query,
            "found_sources": len(sources),
            "indexed_files": indexed_files
        }
        
        return {
            "status": "success",
            "answer": response.text,
            "sources": list(set(sources)),  # Remove duplicates
            "query": query,
            "indexed_files": indexed_files
        }
        
    except Exception as e:
        error_msg = f"Search failed: {str(e)}"
        print(f"[FileSearch] Error: {error_msg}")
        
        return {
            "status": "error",
            "message": error_msg,
            "answer": "",
            "sources": [],
            "query": query
        }


# Create the FunctionTool for use in the agent
search_tool = FunctionTool(search_documents)
