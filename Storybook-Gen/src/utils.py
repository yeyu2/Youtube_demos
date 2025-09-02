from __future__ import annotations

import base64
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv


def load_environment() -> None:
    # Load .env if present
    load_dotenv(override=False)


def get_env(key: str, default: Optional[str] = None) -> Optional[str]:
    return os.getenv(key, default)


def ensure_output_dir(base_dir: Optional[str] = None) -> Path:
    root = Path(base_dir or get_env("OUTPUT_DIR", "outputs"))
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    out = root / timestamp
    out.mkdir(parents=True, exist_ok=True)
    (out / "pages").mkdir(parents=True, exist_ok=True)
    return out


def save_base64_png(b64_data: str, path: Path) -> None:
    binary = base64.b64decode(b64_data)
    path.write_bytes(binary)


def write_json(path: Path, data: Dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False)) 