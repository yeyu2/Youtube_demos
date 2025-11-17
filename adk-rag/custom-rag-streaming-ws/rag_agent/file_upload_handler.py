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
File Upload Handler - Indexes uploaded files into the file search store
"""

import os
import json
import time
import tempfile
from pathlib import Path
from typing import Dict, Any
from google import genai
from google.genai import types
from google.adk.tools import FunctionTool, ToolContext


def load_or_create_config() -> Dict[str, Any]:
    """Load existing config or create new one"""
    config_path = Path(__file__).parent.parent / 'file_store_config.json'
    
    if config_path.exists():
        with open(config_path, 'r') as f:
            return json.load(f)
    
    # No config exists - need to create store
    return {
        'file_search_store_name': None,
        'uploaded_files': []
    }


def save_config(config: Dict[str, Any]):
    """Save configuration to file"""
    config_path = Path(__file__).parent.parent / 'file_store_config.json'
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2)


def create_file_search_store() -> str:
    """Create a new file search store if one doesn't exist"""
    api_key = os.getenv('FILE_SEARCH_API_KEY') or os.getenv('GOOGLE_API_KEY')
    if not api_key:
        raise ValueError("No API key found")
    
    client = genai.Client(api_key=api_key)
    store = client.file_search_stores.create(config={'display_name': 'rag-agent-runtime-store'})
    
    print(f"[FileUpload] Created new file search store: {store.name}")
    return store.name


async def index_uploaded_file(filename: str, tool_context: ToolContext) -> Dict[str, Any]:
    """
    Index a file that was uploaded via the ADK web UI.
    
    This tool takes a file uploaded through the web UI (stored as an artifact)
    and indexes it into the file search store so it can be searched.
    
    Args:
        filename: The name of the uploaded file (e.g., "document.pdf")
        tool_context: The tool context (automatically provided by ADK)
    
    Returns:
        A dictionary containing:
        - status: "success" or "error"
        - message: Description of what happened
        - filename: The name of the indexed file
        - store_name: The file search store name
    """
    
    print(f"[FileUpload] ====== index_uploaded_file CALLED with filename='{filename}' ======")
    
    try:
        # Get API key
        api_key = os.getenv('FILE_SEARCH_API_KEY') or os.getenv('GOOGLE_API_KEY')
        if not api_key:
            return {
                "status": "error",
                "message": "No API key found in environment",
                "filename": filename
            }
        
        # Load or create config
        config = load_or_create_config()
        store_name = config.get('file_search_store_name')
        
        # Create store if it doesn't exist
        if not store_name:
            store_name = create_file_search_store()
            config['file_search_store_name'] = store_name
            config['uploaded_files'] = []
            config['created_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
            save_config(config)
        
        # Check if already indexed
        if filename in config.get('uploaded_files', []):
            return {
                "status": "already_indexed",
                "message": f"File '{filename}' is already indexed",
                "filename": filename,
                "store_name": store_name
            }
        
        # Try to load the artifact from storage first
        print(f"[FileUpload] Loading artifact: {filename}")
        artifact_part = await tool_context.load_artifact(filename)
        
        file_data = None
        mime_type = None
        
        if artifact_part and artifact_part.inline_data:
            # Found in artifact storage
            file_data = artifact_part.inline_data.data
            mime_type = artifact_part.inline_data.mime_type
            print(f"[FileUpload] Loaded from artifact storage")
        else:
            # Not in storage, check session history for inline_data
            print(f"[FileUpload] Not in storage, checking session history for inline uploads...")
            if hasattr(tool_context, '_invocation_context'):
                ctx = tool_context._invocation_context
                if ctx and ctx.session and ctx.session.events:
                    # Check recent events for inline_data matching the filename
                    for event in reversed(ctx.session.events[-5:]):
                        if event.content and event.content.parts:
                            for part in event.content.parts:
                                if part.inline_data:
                                    # Found inline data!
                                    file_data = part.inline_data.data
                                    mime_type = part.inline_data.mime_type
                                    print(f"[FileUpload] Loaded from session inline_data: {mime_type}")
                                    break
                        if file_data:
                            break
        
        if not file_data or not mime_type:
            available = await tool_context.list_artifacts()
            return {
                "status": "error",
                "message": f"File '{filename}' not found in storage or session history. Available artifacts: {available}",
                "filename": filename
            }
        
        print(f"[FileUpload] File size: {len(file_data)} bytes, MIME: {mime_type}")
        
        # Save to temporary file for upload
        temp_dir = Path(tempfile.gettempdir()) / "rag_uploads"
        temp_dir.mkdir(exist_ok=True)
        temp_file = temp_dir / filename
        
        with open(temp_file, 'wb') as f:
            f.write(file_data)
        
        # Upload to file search store
        client = genai.Client(api_key=api_key)
        
        print(f"[FileUpload] Uploading to store: {store_name}")
        upload_op = client.file_search_stores.upload_to_file_search_store(
            file_search_store_name=store_name,
            file=str(temp_file)
        )
        
        # Wait for upload (with timeout)
        timeout = 120  # 2 minutes
        elapsed = 0
        while not upload_op.done and elapsed < timeout:
            time.sleep(3)
            elapsed += 3
            upload_op = client.operations.get(upload_op)
            print(f"[FileUpload] Uploading... {elapsed}s")
        
        if not upload_op.done:
            return {
                "status": "error",
                "message": f"Upload timed out after {timeout}s",
                "filename": filename
            }
        
        # Update config
        config['uploaded_files'].append(filename)
        save_config(config)
        
        # Store in session state
        tool_context.state['last_indexed_file'] = filename
        tool_context.state['indexed_files'] = config['uploaded_files']
        
        print(f"[FileUpload] Successfully indexed: {filename}")
        
        return {
            "status": "success",
            "message": f"Successfully indexed '{filename}' into the search store",
            "filename": filename,
            "store_name": store_name,
            "total_indexed": len(config['uploaded_files'])
        }
        
    except Exception as e:
        error_msg = f"Failed to index '{filename}': {str(e)}"
        print(f"[FileUpload] Error: {error_msg}")
        
        return {
            "status": "error",
            "message": error_msg,
            "filename": filename
        }


async def list_uploaded_files(tool_context: ToolContext) -> Dict[str, Any]:
    """
    List files that have been uploaded via the ADK web UI.
    
    Shows which files are available in artifacts and which have been indexed.
    
    Args:
        tool_context: The tool context (automatically provided by ADK)
    
    Returns:
        A dictionary containing:
        - status: "success"
        - uploaded_files: List of files uploaded via UI (artifacts)
        - indexed_files: List of files indexed in the search store
        - not_indexed: Files uploaded but not yet indexed
    """
    
    print(f"[FileUpload] ====== list_uploaded_files CALLED ======")
    
    try:
        # Get uploaded artifacts (saved ones)
        print(f"[FileUpload] Calling tool_context.list_artifacts()...")
        uploaded_files = await tool_context.list_artifacts()
        print(f"[FileUpload] Found {len(uploaded_files)} artifacts from storage: {uploaded_files}")
        
        # ALSO check session history for inline_data uploads
        inline_uploads = []
        if hasattr(tool_context, '_invocation_context'):
            ctx = tool_context._invocation_context
            if ctx and ctx.session and ctx.session.events:
                # Check recent events for inline_data
                for event in reversed(ctx.session.events[-5:]):  # Check last 5 events
                    if event.content and event.content.parts:
                        for idx, part in enumerate(event.content.parts):
                            if part.inline_data:
                                mime_type = part.inline_data.mime_type
                                ext = mime_type.split('/')[-1]
                                filename = f"uploaded_document.{ext}"
                                if filename not in inline_uploads:
                                    inline_uploads.append(filename)
                                    print(f"[FileUpload] Found inline upload: {filename} ({mime_type})")
        
        # Combine both sources
        all_files = list(set(uploaded_files + inline_uploads))
        print(f"[FileUpload] Total files available: {len(all_files)} - {all_files}")
        
        # Load config to see what's indexed
        config = load_or_create_config()
        indexed_files = config.get('uploaded_files', [])
        
        # Find files not yet indexed
        not_indexed = [f for f in all_files if f not in indexed_files]
        
        message = f"Found {len(all_files)} uploaded file(s)"
        if not_indexed:
            message += f", {len(not_indexed)} need indexing: {', '.join(not_indexed)}"
        if indexed_files:
            message += f", {len(indexed_files)} already indexed"
        
        return {
            "status": "success",
            "uploaded_files": all_files,
            "indexed_files": indexed_files,
            "not_indexed": not_indexed,
            "message": message,
            "store_name": config.get('file_search_store_name')
        }
        
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to list files: {str(e)}",
            "uploaded_files": [],
            "indexed_files": [],
            "not_indexed": []
        }


# Create the FunctionTools
index_file_tool = FunctionTool(index_uploaded_file)
list_files_tool = FunctionTool(list_uploaded_files)

