#!/usr/bin/env python3
"""
Script to analyze the structure of a PDF file and verify it follows the expected layout.
"""

import argparse
import os
import sys
from pathlib import Path

try:
    from PyPDF2 import PdfReader
except ImportError:
    print("PyPDF2 is required. Installing...")
    os.system(f"{sys.executable} -m pip install PyPDF2")
    from PyPDF2 import PdfReader

def analyze_pdf(pdf_path):
    """Analyze the structure of a PDF file."""
    print(f"Analyzing PDF: {pdf_path}")
    
    # Check if file exists
    if not Path(pdf_path).exists():
        print(f"Error: File not found: {pdf_path}")
        return
    
    # Open and analyze the PDF
    try:
        reader = PdfReader(pdf_path)
        page_count = len(reader.pages)
        
        print(f"Total pages: {page_count}")
        
        # Check if the structure follows the expected pattern:
        # 1. Cover page
        # 2. Image page 1
        # 3. Text page 1
        # 4. Image page 2
        # 5. Text page 2
        # ...
        
        if page_count < 1:
            print("Error: PDF has no pages")
            return
            
        print("\nPDF Structure:")
        print("1. Cover page")
        
        story_pages = (page_count - 1) // 2
        for i in range(story_pages):
            page_num = i + 1
            image_page_num = 2 * i + 2
            text_page_num = 2 * i + 3
            
            print(f"{image_page_num}. Image page {page_num}")
            
            if text_page_num <= page_count:
                print(f"{text_page_num}. Text page {page_num}")
        
        print(f"\nStory has {story_pages} pages (image+text pairs)")
        
        if (page_count - 1) % 2 != 0:
            print("Warning: PDF structure is not balanced. There should be an equal number of image and text pages.")
        
    except Exception as e:
        print(f"Error analyzing PDF: {e}")

def main():
    parser = argparse.ArgumentParser(description="Analyze the structure of a PDF file")
    parser.add_argument("pdf_path", help="Path to the PDF file to analyze")
    args = parser.parse_args()
    
    analyze_pdf(args.pdf_path)

if __name__ == "__main__":
    main() 