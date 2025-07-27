#!/usr/bin/env python3
"""Generate a short podcast (script + audio + header image) introducing a GitHub repo.

Input: GitHub repository URL or `owner/repo` slug typed in the terminal.
Pipeline:
1. TerminalInput – user provides repo URL
2. GithubProcessor   – fetch README & metadata
3. GenaiModel        – summarise repo as a 1-2-minute podcast script (plain text)
4. TextBuffer        – collect script into a single part
5. HeaderImage       – generate an eye-catching cover image
6. TextToSpeech      – synthesise narration audio from the script
7. SaveAssets        – write image → PNG, audio → MP3/WAV, script → .txt and show paths

Run:
  python repo_podcast_generator.py
"""

import asyncio
import logging
import os
import re
from typing import AsyncIterable
from pathlib import Path

from google.genai import types as genai_types
from genai_processors import content_api, processor
# we will call Gemini TTS directly instead of the built-in processor that
# requires GCP ADC credentials.
from genai_processors.core import genai_model, github
from PIL import Image
from google import genai  # for direct TTS call

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
# GitHub personal-access token (optional but recommended). Generate at
# https://github.com/settings/tokens (classic) or fine-grained. Minimum scope: `public_repo`.
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(exist_ok=True)
# Speaker names
SPEAKER_1 = "Host"
SPEAKER_2 = "Guest"

# -----------------------------------------------------------------------------
# Source – read GitHub URL from user
# -----------------------------------------------------------------------------

@processor.source()
async def TerminalGitHubInput(prompt: str) -> AsyncIterable[content_api.ProcessorPartTypes]:
    while True:
        try:
            inp = await asyncio.to_thread(input, prompt)
            if inp.lower() in {"q", "quit"}:
                break
            if inp:
                yield inp.strip()
        except (EOFError, KeyboardInterrupt):
            break

# -----------------------------------------------------------------------------
# Simple buffer
# -----------------------------------------------------------------------------

class TextBuffer(processor.Processor):
    def __init__(self):
        self._buf = ""

    async def call(self, content):
        self._buf = ""
        async for part in content:
            if not isinstance(part, processor.ProcessorPart):
                part = processor.ProcessorPart(part)
            if part.text:
                self._buf += part.text
        if self._buf:
            yield processor.ProcessorPart(self._buf)

# -----------------------------------------------------------------------------
# Header image generator (same as in previous script but shorter)
# -----------------------------------------------------------------------------

class HeaderImage(processor.Processor):
    def __init__(self, api_key: str):
        from google import genai
        self._client = genai.Client(api_key=api_key)

    async def call(self, content):
        text = ""
        async for part in content:
            if not isinstance(part, processor.ProcessorPart):
                part = processor.ProcessorPart(part)
            if content_api.is_text(part.mimetype):
                text += part.text
            # forward everything downstream unchanged
            yield part
        if not text:
            return
        title_line = text.split("\n", 1)[0].strip()
        prompt = f"Create a podcast cover image (16:9) illustrating: '{title_line}'. Futuristic, vibrant, tech-style."
        try:
            response = await asyncio.to_thread(
                lambda: self._client.models.generate_content(
                    model="gemini-2.0-flash-preview-image-generation",
                    contents=prompt,
                    config=genai_types.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"]),
                )
            )
            for cand in response.candidates:
                for p in cand.content.parts:
                    if p.inline_data is not None:
                        yield processor.ProcessorPart(p.inline_data.data, mimetype="image/png")
                        return
        except Exception as e:
            logging.error(f"Image gen failed: {e}")

# -----------------------------------------------------------------------------
# Gemini TTS processor (multi-speaker)
# -----------------------------------------------------------------------------


class GeminiTTSProcessor(processor.Processor):
    """Call Gemini preview TTS model and emit an AUDIO part."""

    def __init__(self, api_key: str):
        self._client = genai.Client(api_key=api_key)

    async def call(self, content):
        full_text = ""
        async for part in content:
            if not isinstance(part, processor.ProcessorPart):
                part = processor.ProcessorPart(part)
            if content_api.is_text(part.mimetype):
                full_text += part.text
            # forward every part unchanged
            yield part

        if not full_text:
            return

        # Ensure script is formatted with "Speaker: …" lines. If it isn't, wrap every paragraph alternating speakers.
        if ":" not in full_text.split("\n", 1)[0]:
            # auto-prefix lines
            lines = []
            current = SPEAKER_1
            for para in full_text.splitlines():
                if para.strip():
                    lines.append(f"{current}: {para.strip()}")
                    current = SPEAKER_2 if current == SPEAKER_1 else SPEAKER_1
            script_for_tts = "\n".join(lines)
        else:
            script_for_tts = full_text

        prompt = f"TTS the following conversation between {SPEAKER_1} and {SPEAKER_2}:\n{script_for_tts}"

        try:
            response = await asyncio.to_thread(
                lambda: self._client.models.generate_content(
                    model="gemini-2.5-flash-preview-tts",
                    contents=prompt,
                    config=genai_types.GenerateContentConfig(
                        response_modalities=["AUDIO"],
                        speech_config=genai_types.SpeechConfig(
                            multi_speaker_voice_config=genai_types.MultiSpeakerVoiceConfig(
                                speaker_voice_configs=[
                                    genai_types.SpeakerVoiceConfig(
                                        speaker=SPEAKER_1,
                                        voice_config=genai_types.VoiceConfig(
                                            prebuilt_voice_config=genai_types.PrebuiltVoiceConfig(voice_name="Kore")
                                        ),
                                    ),
                                    genai_types.SpeakerVoiceConfig(
                                        speaker=SPEAKER_2,
                                        voice_config=genai_types.VoiceConfig(
                                            prebuilt_voice_config=genai_types.PrebuiltVoiceConfig(voice_name="Puck")
                                        ),
                                    ),
                                ]
                            ),
                        ),
                    ),
                )
            )

            audio_bytes = response.candidates[0].content.parts[0].inline_data.data
            logging.info(f"Gemini TTS returned {len(audio_bytes)} bytes")
            yield processor.ProcessorPart(audio_bytes, mimetype="audio/wav")
        except Exception as e:
            logging.error(f"Gemini TTS failed: {e}")

# -----------------------------------------------------------------------------
# Save assets
# -----------------------------------------------------------------------------

class SaveAssets(processor.Processor):
    """Save incoming parts to files inside OUTPUT_DIR and emit status."""
    def __init__(self):
        self.count_img = 0
        self.count_audio = 0
        self.script_written = False

    async def call(self, content):
        async for part in content:
            if not isinstance(part, processor.ProcessorPart):
                part = processor.ProcessorPart(part)
            if content_api.is_text(part.mimetype) and not self.script_written:
                txt_path = OUTPUT_DIR / "podcast_script.txt"
                txt_path.write_text(part.text)
                self.script_written = True
                yield processor.status(f"Script saved ➜ {txt_path}")
            elif content_api.is_image(part.mimetype):
                self.count_img += 1
                img_path = OUTPUT_DIR / f"cover_{self.count_img}.png"
                img_path.write_bytes(part.bytes)
                yield processor.status(f"Image saved ➜ {img_path}")
            elif content_api.is_audio(part.mimetype):
                self.count_audio += 1
                # Gemini preview TTS returns raw 16-bit little-endian PCM at 24 kHz.
                wav_path = OUTPUT_DIR / f"podcast_{self.count_audio}.wav"
                import wave
                with wave.open(str(wav_path), "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)  # 16-bit
                    wf.setframerate(24000)
                    wf.writeframes(part.bytes)
                yield processor.status(f"Audio saved ➜ {wav_path}")
            else:
                # pass through any other part
                yield part

# -----------------------------------------------------------------------------
# Build pipeline
# -----------------------------------------------------------------------------

def build_pipeline(api_key: str):
    # 1. Fetch repo – use token if provided to avoid low anonymous rate-limit
    gh_proc = github.GithubProcessor(api_key=GITHUB_TOKEN or None)

    # 2. LLM to create podcast script
    podcast_writer = genai_model.GenaiModel(
        model_name="gemini-2.5-flash",
        api_key=api_key,
        generate_content_config=genai_types.GenerateContentConfig(
            system_instruction=(
                "You are an engaging podcast host. "
                "Using the repository README and metadata provided, "
                "write a conversational podcast script **about 150-180 words** "
                "as a dialogue between Host and Guest that introduces the repository. "
                "First line is an episode title, plain text, no markdown."
            ),
        ),
    )

    # 3. Gemini TTS processor
    tts_proc = GeminiTTSProcessor(api_key)

    return gh_proc + podcast_writer + TextBuffer() + HeaderImage(api_key) + tts_proc + SaveAssets()

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

async def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    if GOOGLE_API_KEY.startswith("YOUR_"):
        logging.error("Set GOOGLE_API_KEY env var.")
        return
    if not GITHUB_TOKEN:
        logging.warning("No GITHUB_TOKEN provided – GitHub API quota will be very limited (60 req/h) and private repos won't work.")

    pipeline = build_pipeline(GOOGLE_API_KEY)
    async for part in pipeline(TerminalGitHubInput("GitHub repo URL > ")):
        if part.substream_name == "status":
            logging.info(part.text)

if __name__ == "__main__":
    asyncio.run(main()) 