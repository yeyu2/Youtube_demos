# Copyright 2025 DeepMind Technologies Limited. All Rights Reserved.
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

import asyncio
import logging
import os
import io
from typing import AsyncIterable, Optional, Tuple
import base64

# To install dependencies:
# pip install genai-processors "google-api-python-client>=2.100.0" "google-auth-httplib2>=0.1.0" "google-auth-oauthlib>=0.5.1" pillow
from genai_processors import content_api, processor
from genai_processors.core import genai_model
import google.auth
from googleapiclient.discovery import build
from google.genai import types as genai_types
# OAuth libs
from google.oauth2.credentials import Credentials as OAuthCredentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.errors import HttpError
from PIL import Image

# --- Configuration ---
# Set your Gemini API Key as an environment variable or replace the string below.
# Get a key from https://aistudio.google.com/app/apikey
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")

# --- Input Source Processor ---

@processor.source()
async def TerminalInput(prompt: str) -> AsyncIterable[content_api.ProcessorPartTypes]:
    """A source processor that yields text from the user's terminal input.
    
    This pattern is from the processor_intro.ipynb example. It creates an
    endless stream of user inputs, which is perfect for an interactive app.
    """
    while True:
        try:
            # We run the blocking `input()` function in a separate thread
            # to keep the asyncio event loop from stalling.
            input_text = await asyncio.to_thread(input, prompt)
            if input_text.lower() == 'q' or input_text.lower() == 'quit':
                logging.info("Exiting application.")
                break
            if input_text:
                yield input_text
        except (KeyboardInterrupt, EOFError):
            logging.info("\nExiting application.")
            break


# --- Text Buffer Processor ---

class TextBufferProcessor(processor.Processor):
    """A Processor that buffers text content until a turn is complete, then emits it as a single part."""
    
    def __init__(self):
        self._buffer = ""
        
    async def call(self, content: AsyncIterable[content_api.ProcessorPartTypes]) -> AsyncIterable[content_api.ProcessorPart]:
        """Collects all text parts from a stream and yields them as a single part at the end."""
        self._buffer = ""
        async for part in content:
            # If part is not a ProcessorPart yet, convert it
            if not isinstance(part, processor.ProcessorPart):
                part = processor.ProcessorPart(part)
                
            if part.text:
                self._buffer += part.text
                
        # Once all parts are collected, yield the complete text
        if self._buffer:
            yield processor.ProcessorPart(self._buffer)


# --- Image Generator Processor ---

class ImageGeneratorProcessor(processor.Processor):
    """A processor that generates an image based on the blog title/topic."""
    
    def __init__(self, api_key: str):
        self._api_key = api_key
        from google import genai
        self._client = genai.Client(api_key=api_key)
        
    async def call(self, content: AsyncIterable[content_api.ProcessorPartTypes]) -> AsyncIterable[content_api.ProcessorPart]:
        """Generate an image based on the blog topic."""
        buffer = ""
        async for part in content:
            # If part is not a ProcessorPart yet, convert it
            if not isinstance(part, processor.ProcessorPart):
                part = processor.ProcessorPart(part)
                
            if part.text:
                buffer += part.text
                # Also yield the text part downstream
                yield part
        
        if buffer:
            # Extract title from the blog post
            title = buffer.split('\n', 1)[0].strip("# ")
            
            # Generate prompt for the image
            image_prompt = f"Create an eye-catching header image for a blog post about: {title}"
            
            logging.info(f"Generating header image for: {title}")
            
            try:
                # Call Gemini to generate the image
                response = await asyncio.to_thread(
                    lambda: self._client.models.generate_content(
                        model="gemini-2.0-flash-preview-image-generation",
                        contents=image_prompt,
                        config=genai_types.GenerateContentConfig(
                            response_modalities=['TEXT', 'IMAGE']
                        )
                    )
                )
                
                # Extract image data from response
                logging.info(f"Image generation response received with {len(response.candidates)} candidates")
                
                for candidate in response.candidates:
                    for part in candidate.content.parts:
                        if part.text is not None:
                            logging.info(f"Text part from image generation: {part.text}")
                        elif part.inline_data is not None:
                            # Convert image to bytes for downstream processing
                            image_bytes = part.inline_data.data
                            
                            logging.info(f"Image data received, size: {len(image_bytes)} bytes")
                            
                            # Create a PIL image for potential further processing
                            image = Image.open(io.BytesIO(image_bytes))
                            
                            # Save image to local file for debugging
                            try:
                                file_title = title.replace(" ", "_").replace(":", "").replace("/", "_")[:50]
                                image_path = f"{file_title}_header.png"
                                with open(image_path, "wb") as img_file:
                                    img_file.write(image_bytes)
                                logging.info(f"Saved image to local file: {image_path}")
                            except Exception as save_error:
                                logging.error(f"Error saving image to file: {save_error}")
                            
                            # Yield image as a processor part
                            yield processor.ProcessorPart(
                                image_bytes,
                                mimetype="image/png",
                                metadata={"title": title, "purpose": "header_image"}
                            )
                            
                            logging.info(f"Successfully generated header image, dimensions: {image.size}")
                            
            except Exception as e:
                logging.error(f"Failed to generate header image: {e}")


# --- Custom Processor to Create a Google Doc with Image and Text ---

class OAuthDocWithImageProcessor(processor.PartProcessor):
    """PartProcessor that creates a Google Doc using OAuth desktop credentials,
    including both text content and header image."""

    # Filenames used for OAuth – placed in project root
    _CLIENT_SECRETS = "credentials.json"  # downloaded from Cloud Console
    _TOKEN_FILE = "token.json"            # cached after first consent
    _SCOPES = [
        "https://www.googleapis.com/auth/drive.file",  # create & edit files you own/share
        "https://www.googleapis.com/auth/documents",
    ]

    def __init__(self):
        # Load or obtain user credentials the first time.
        self.creds = self._get_user_credentials()
        self.drive_service = build("drive", "v3", credentials=self.creds)
        self.docs_service = build("docs", "v1", credentials=self.creds)
        # Store the header image temporarily
        self.header_image_bytes = None
        self.blog_content = None
        self.title = None
        self._doc_created = False  # ensure we create only once per blog

    def _get_user_credentials(self) -> OAuthCredentials:
        """Return user creds; run local-server flow if no cached token."""
        if os.path.exists(self._TOKEN_FILE):
            creds = OAuthCredentials.from_authorized_user_file(self._TOKEN_FILE, self._SCOPES)
            if creds and creds.valid and not creds.expired:
                return creds
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                with open(self._TOKEN_FILE, "w") as fh:
                    fh.write(creds.to_json())
                return creds

        if not os.path.exists(self._CLIENT_SECRETS):
            raise FileNotFoundError(
                f"OAuth client secrets '{self._CLIENT_SECRETS}' not found. "
                "Download it from Cloud Console → Credentials and place next to this script."
            )

        flow = InstalledAppFlow.from_client_secrets_file(self._CLIENT_SECRETS, self._SCOPES)
        creds = flow.run_local_server(port=0, prompt="consent")
        with open(self._TOKEN_FILE, "w") as fh:
            fh.write(creds.to_json())
        return creds

    async def call(self, part: content_api.ProcessorPart) -> AsyncIterable[content_api.ProcessorPart]:
        """Process either text content or image."""
        if self._doc_created:
            return  # ignore any parts after doc is created

        # Check part type
        if part.metadata and part.metadata.get("purpose") == "header_image":
            self.header_image_bytes = part.bytes
            if not self.title:
                self.title = part.metadata.get("title")
        elif content_api.is_text(part.mimetype):
            self.blog_content = part.text
            self.title = self.blog_content.split('\n', 1)[0].strip("# ") or "AI-Generated Blog Post"

        # Proceed only when we have blog_content (always) and header image status known (could be None if not provided or already set)

        if self.blog_content is None:
            return  # wait for text

        # If we have text but no image yet, wait until image part arrives
        if self.header_image_bytes is None and not (part.metadata and part.metadata.get("purpose") == "header_image"):
            # Text arrived first, but image not yet – wait for image part
            return

        # At this point we have blog_content and maybe header_image_bytes
        try:
            self._doc_created = True
            
            # Step 1: create empty doc via Drive
            file_metadata = {
                "name": self.title,
                "mimeType": "application/vnd.google-apps.document",
            }
            file = await asyncio.to_thread(
                lambda: self.drive_service.files().create(body=file_metadata, fields="id, webViewLink").execute()
            )
            doc_id = file["id"]
            doc_url = file["webViewLink"]
            
            # Step 2: if image available, upload
            image_id = None
            if self.header_image_bytes:
                image_file_metadata = {
                    'name': f'{self.title} - Header Image',
                    'mimeType': 'image/png'
                }
                from googleapiclient.http import MediaInMemoryUpload
                media = MediaInMemoryUpload(self.header_image_bytes, mimetype='image/png')
                image_file = await asyncio.to_thread(
                    lambda: self.drive_service.files().create(
                        body=image_file_metadata,
                        media_body=media,
                        fields='id'
                    ).execute()
                )
                image_id = image_file.get('id')
                # make public
                try:
                    await asyncio.to_thread(
                        lambda: self.drive_service.permissions().create(
                            fileId=image_id,
                            body={"role": "reader", "type": "anyone"}
                        ).execute()
                    )
                except Exception as perm_error:
                    logging.error(f"Permission error: {perm_error}")

            # Step 3: build requests as earlier (image first)
            if image_id:
                image_url = f"https://drive.google.com/uc?export=view&id={image_id}"
                requests_img = [
                    {
                        "insertInlineImage": {
                            "location": {"index": 1},
                            "uri": image_url,
                            "objectSize": {
                                "width": {"magnitude": 600, "unit": "PT"},
                                "height": {"magnitude": 300, "unit": "PT"}
                            }
                        }
                    },
                    {"insertText": {"location": {"index": 2}, "text": "\n\n"}}
                ]
                await asyncio.to_thread(lambda: self.docs_service.documents().batchUpdate(documentId=doc_id, body={"requests": requests_img}).execute())
                # then text
                text_requests = [
                    {"insertText": {"endOfSegmentLocation": {}, "text": self.blog_content}},
                    {"insertText": {"endOfSegmentLocation": {}, "text": f"\n\n(Header image URL: {image_url})\n"}}
                ]
                await asyncio.to_thread(lambda: self.docs_service.documents().batchUpdate(documentId=doc_id, body={"requests": text_requests}).execute())
            else:
                # no image
                await asyncio.to_thread(lambda: self.docs_service.documents().batchUpdate(documentId=doc_id, body={"requests": [{"insertText": {"location": {"index": 1}, "text": self.blog_content}}]}).execute())

            yield processor.status(f"Created doc: {doc_url}")
        except HttpError as e:
            logging.error(f"Failed to create Google Doc: {e}")
            yield processor.status(f"Error creating Google Doc: {e}")
        finally:
            # reset for next run
            self.header_image_bytes = None
            self.blog_content = None
            self.title = None


async def main():
    """Main function to define the pipeline and run the interactive loop."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if "YOUR_GEMINI_API_KEY" in GOOGLE_API_KEY:
        logging.error("Please set your GOOGLE_API_KEY before running.")
        return

    # --- 1. Define the Processors ---
    blog_writer = genai_model.GenaiModel(
        model_name="gemini-2.5-flash",
        api_key=GOOGLE_API_KEY,
        generate_content_config=genai_types.GenerateContentConfig(
            system_instruction=(
                "You are a helpful and creative technical writer. "
                "Generate a well-structured blog post for a Google Doc based on the given topic. "
                "Start with a clear title on the first line (plain text, no leading symbols). "
                "Use plain paragraphs separated by blank lines. "
                "Do NOT use markdown characters such as #, *, -, or backticks. "
                "Keep formatting simple so it renders cleanly in Google Docs."
            )
        )
    )
    
    # Image generator processor
    image_generator = ImageGeneratorProcessor(api_key=GOOGLE_API_KEY)
    
    # Text buffer to collect all text chunks
    text_buffer = TextBufferProcessor()
    
    # OAuth-based Doc creator that supports images (opens browser for first-time consent)
    try:
        doc_creator = OAuthDocWithImageProcessor()
    except Exception as e:
        logging.error(str(e))
        return

    # --- 2. Assemble the Pipeline ---
    # Chain: blog_writer -> text_buffer -> image_generator -> doc_creator
    pipeline = blog_writer + text_buffer + image_generator + doc_creator.to_processor()

    # --- 3. Define the Input Source ---
    # This creates our interactive terminal input stream.
    terminal_source = TerminalInput("Enter a blog post topic (or 'q' to quit) > ")

    # --- 4. Run the Interactive Pipeline ---
    logging.info("AI Blog Post Generator with Header Images is ready.")
    
    # The `pipeline` processor is called with the `terminal_source` as its input.
    # The `async for` loop will now wait for the user to provide input.
    async for part in pipeline(terminal_source):
        # The loop will only receive 'status' parts back from the pipeline,
        # which we can log to give the user feedback.
        if part.substream_name == "status":
            logging.info(f"[PIPELINE STATUS] {part.text}")


if __name__ == "__main__":
    # This is the standard entry point to run an async main function.
    asyncio.run(main()) 