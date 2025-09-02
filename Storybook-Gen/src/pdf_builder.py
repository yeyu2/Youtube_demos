from __future__ import annotations

import os
from pathlib import Path
from typing import List, Tuple

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from .models import PagePlan


# Get absolute path to the fonts directory
FONTS_DIR = Path(os.path.dirname(os.path.abspath(__file__))).parent / "fonts"
COMIC_NEUE_DIR = FONTS_DIR / "Comic_Neue"

# Define font variables with defaults
TITLE_FONT = 'Helvetica-Bold'     # Default font for titles
BODY_FONT = 'Helvetica'           # Default font for body text
COMIC_FONT_LOADED = False         # Flag to track if comic font was loaded


def register_comic_fonts():
    """Register Comic Neue fonts if available."""
    global TITLE_FONT, BODY_FONT, COMIC_FONT_LOADED
    
    try:
        # Check if Comic Neue font files exist
        comic_regular = COMIC_NEUE_DIR / "ComicNeue-Regular.ttf"
        comic_bold = COMIC_NEUE_DIR / "ComicNeue-Bold.ttf"
        
        if comic_regular.exists() and comic_bold.exists():
            # Register the fonts with ReportLab
            pdfmetrics.registerFont(TTFont('ComicNeue', str(comic_regular)))
            pdfmetrics.registerFont(TTFont('ComicNeue-Bold', str(comic_bold)))
            
            # Update the global font variables
            TITLE_FONT = 'ComicNeue-Bold'
            BODY_FONT = 'ComicNeue'
            COMIC_FONT_LOADED = True
            
            print("Comic Neue fonts registered successfully!")
            return True
        else:
            print(f"Comic Neue font files not found at {COMIC_NEUE_DIR}")
            return False
    except Exception as e:
        print(f"Failed to register Comic Neue fonts: {e}")
        print("Using default fonts instead")
        return False


def get_child_friendly_fonts():
    """Get child-friendly fonts for the PDF."""
    global TITLE_FONT, BODY_FONT
    
    # Try to register Comic Neue fonts first
    if register_comic_fonts():
        return
    
    # Fallback to Courier if Comic Neue fails
    TITLE_FONT = 'Courier-Bold'
    BODY_FONT = 'Courier'
    
    print(f"Using fallback child-friendly fonts: {TITLE_FONT} and {BODY_FONT}")


def get_age_appropriate_font_size(age: int = 8) -> dict:
    """
    Returns appropriate font sizes based on child's age:
    - Younger children (4-6): Larger text
    - Middle (7-9): Medium-large text
    - Older (10+): Standard text with more content
    """
    if age <= 6:
        return {
            "title": 28,      # Very large titles
            "header": 20,     # Large page headers
            "body": 18,       # Large body text for beginning readers
            "leading": 24     # Extra space between lines
        }
    elif age <= 9:
        return {
            "title": 26,      # Large titles
            "header": 18,     # Medium-large page headers
            "body": 16,       # Medium-large body text
            "leading": 22     # Good spacing for developing readers
        }
    else:
        return {
            "title": 24,      # Standard title size
            "header": 16,     # Standard header size
            "body": 14,       # Standard body size for confident readers
            "leading": 20     # Standard line spacing
        }


def build_pdf(output_pdf: Path, title: str, cover_image: Path, pages: List[PagePlan], child_age: int = 8) -> Path:
    """
    Build a PDF storybook with the following layout:
    - Cover page: Full-bleed image only (no title overlay)
    - For each story page: 
        - Image page: Full-page image
        - Text page: Text centered on page with decorative header
        
    Args:
        output_pdf: Path to save the PDF
        title: Story title
        cover_image: Path to the cover image
        pages: List of PagePlan objects
        child_age: Age of the child for appropriate font sizing
    """
    # Use child-friendly fonts
    get_child_friendly_fonts()
    
    c = canvas.Canvas(str(output_pdf), pagesize=LETTER)
    width, height = LETTER
    
    # Get age-appropriate font sizes
    font_sizes = get_age_appropriate_font_size(child_age)
    
    # Define colors and styles
    title_color = HexColor('#1A365D')  # Deep blue
    header_color = HexColor('#2C5282')  # Medium blue
    text_color = HexColor('#2D3748')   # Dark slate
    
    # Print debugging info about fonts
    print(f"PDF Builder using fonts - Title: {TITLE_FONT}, Body: {BODY_FONT}")
    
    # 1) Cover page (full-bleed image only, no title overlay)
    if cover_image.exists():
        c.drawImage(str(cover_image), 0, 0, width=width, height=height, preserveAspectRatio=True, anchor='c')
    
    # No title overlay since it's already in the image
    c.showPage()
    
    # 2) For each story page: image page then text page
    for p in pages:
        # Image page (full-bleed style within page bounds)
        img = Path(p.image_path) if p.image_path else None
        if img and img.exists():
            c.drawImage(str(img), 0, 0, width=width, height=height, preserveAspectRatio=True, anchor='c')
        else:
            # If image missing, draw a simple placeholder
            c.setFillColorRGB(0.95, 0.95, 0.95)  # Light gray background
            c.rect(0, 0, width, height, fill=1, stroke=0)
            
            c.setFont(TITLE_FONT, font_sizes["header"])
            c.setFillColor(header_color)
            c.drawCentredString(width / 2, height / 2, f"Illustration for Page {p.index}")
            
            c.setFont(BODY_FONT, font_sizes["body"])
            c.setFillColor(text_color)
            c.drawCentredString(width / 2, height / 2 - 30, "(Image not found)")
        c.showPage()
        
        # Text page (text centered on page with decorative elements)
        # Draw a light background color with soft gradient
        c.setFillColorRGB(0.98, 0.98, 1.0)  # Very light blue background
        c.rect(0, 0, width, height, fill=1, stroke=0)
        
        # Add a subtle pattern or texture for visual interest
        for i in range(20):
            c.setFillColorRGB(0.95, 0.95, 1.0, 0.1)  # Very light with low opacity
            c.circle(width * (i/20), height * (i/20), 50, fill=1, stroke=0)
        
        # Draw decorative header
        c.setFont(TITLE_FONT, font_sizes["header"])
        c.setFillColor(header_color)
        header = f"Page {p.index}"
        c.drawCentredString(width / 2, height - 1.0 * inch, header)
        
        # Draw a decorative line under the header
        c.setStrokeColor(header_color)
        c.setLineWidth(1)
        c.line(width / 2 - 1.5 * inch, height - 1.1 * inch, width / 2 + 1.5 * inch, height - 1.1 * inch)
        
        # Text content with proper wrapping and child-friendly styling
        text_style = ParagraphStyle(
            name='StoryText',
            fontName=BODY_FONT,
            fontSize=font_sizes["body"],
            leading=font_sizes["leading"],  # Line spacing
            alignment=4,  # Center aligned
            textColor=text_color,
            spaceAfter=12,
            spaceBefore=12,
        )
        
        # Create paragraph and calculate height
        text_width = width - 2 * (1.5 * inch)  # Margins on both sides
        p_text = Paragraph(p.text, text_style)
        text_height = p_text.wrap(text_width, height)[1]
        
        # Position text in the vertical center of the page
        y_position = (height + text_height) / 2
        p_text.drawOn(c, 1.5 * inch, y_position)
        
        # Draw decorative footer
        c.setStrokeColor(header_color)
        c.line(width / 2 - 1.0 * inch, 1.0 * inch, width / 2 + 1.0 * inch, 1.0 * inch)
        
        c.showPage()
    
    c.save()
    return output_pdf


def wrap_text(text: str, width: int) -> List[str]:
    """
    Wrap text to fit within a certain character width.
    This is a fallback if Paragraph wrapping doesn't work.
    """
    words = text.split()
    lines = []
    current: List[str] = []
    current_len = 0
    for w in words:
        if current_len + len(w) + (1 if current_len > 0 else 0) > width:
            lines.append(" ".join(current))
            current = [w]
            current_len = len(w)
        else:
            current.append(w)
            current_len += len(w) + (1 if current_len > 0 else 0)
    if current:
        lines.append(" ".join(current))
    return lines 