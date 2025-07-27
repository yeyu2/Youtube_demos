# AI Blog Generator with Header Images

This script generates blog posts using Gemini AI, including an automatically generated header image based on the blog topic. The content is then published to Google Docs for easy access and further editing.

## Features

- Interactive command-line interface for blog topic input
- AI-generated blog content using Gemini 2.5 Flash model
- Automatic header image generation using Gemini image generation capabilities 
- Combined text and image publication to Google Docs
- OAuth authentication for Google services

## Prerequisites

- Python 3.8+ with pip
- Google account
- Gemini API key (get one from [Google AI Studio](https://aistudio.google.com/app/apikey))
- Google Cloud OAuth credentials for Google Docs access

## Installation

1. Install the dependencies:
   ```bash
   pip install --upgrade "genai-processors==1.0.4" "google-api-python-client>=2.100.0" "google-auth-httplib2>=0.1.0" "google-auth-oauthlib>=0.5.1" pillow "google-genai==1.26.0"
   ```

2. Set up your Google Cloud OAuth credentials:
   - Go to the [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project or select an existing one
   - Enable the Google Drive API and Google Docs API
   - Create OAuth credentials (Desktop app type)
   - Download the credentials.json file and save it in the root directory of this project

## Usage

1. Set your Gemini API key as an environment variable (or replace the placeholder in the script):
   ```bash
   export GOOGLE_API_KEY="your-api-key-here"
   ```

2. Run the script:
   ```bash
   python blog_image_generator.py
   ```

3. Enter your blog topic when prompted. The script will:
   - Generate a blog post about your topic
   - Create a header image that matches the topic
   - Publish both to a new Google Doc
   - Provide you with a link to the created document

4. On first run, your browser will open to authenticate with Google. Follow the prompts to grant access.

5. Type 'q' or 'quit' to exit the application.

## Pipeline Structure

The script uses a modular pipeline architecture:

1. `TerminalInput` - Accepts user input topics
2. `blog_writer` - Generates blog content using Gemini
3. `text_buffer` - Collects text chunks into complete blog posts
4. `image_generator` - Creates header images based on blog topics
5. `doc_creator` - Combines text and images into Google Docs

## Customization

- Modify the `system_instruction` in the blog_writer to change the style or format of generated blog posts
- Adjust the image generation prompt in the `ImageGeneratorProcessor` class
- Change image placement in the document by modifying the `OAuthDocWithImageProcessor`

## Troubleshooting

- **Authentication issues**: Ensure credentials.json is in the root directory
- **API key errors**: Verify your Gemini API key is valid and properly set
- **Image generation failures**: Check your prompt and API access for image generation

## License

Licensed under the Apache License, Version 2.0 