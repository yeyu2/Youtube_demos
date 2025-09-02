# Storybook Generator

AI-powered personalized children's storybook generator.

## Setup

1. Install dependencies:
```
pip install -r requirements.txt
```

2. Configure environment:
```
cp env.example .env
```
Edit `.env` and add your `OPENAI_API_KEY`.

## Run

### Standard Version (with reference images for character consistency)
```
python generate_storybook.py
```

### Alternative Version (without reference images)
```
python generate_storybook_v2.py
```

## Environment Settings

- `TEXT_MODEL`: Text model for story generation (default: gpt-5-mini)
- `IMAGE_MODEL`: Image model for illustrations (default: gpt-image-1)
- `PAGE_COUNT`: Number of pages (default: 6, range 3-10)
- `IMAGE_SIZE`: Image dimensions (default: 1024x1536)
- `OUTPUT_DIR`: Output directory (default: outputs) 