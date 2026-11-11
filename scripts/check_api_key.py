"""Live check that the key and model in .env work. Makes one small API call.

    .venv/bin/python scripts/check_api_key.py

Prints Claude's greeting, or the error type and status. Never prints the key.
"""
import os
import sys
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

missing = [name for name in ("ANTHROPIC_API_KEY", "MODEL_ID") if not os.environ.get(name)]
if missing:
    sys.exit(f"Missing from .env: {', '.join(missing)}")

try:
    reply = anthropic.Anthropic().messages.create(
        model=os.environ["MODEL_ID"],
        max_tokens=50,
        messages=[{"role": "user", "content": "Say hello and identify your model in one sentence."}],
    )
except anthropic.APIStatusError as err:
    sys.exit(f"Failed: {type(err).__name__} (HTTP {err.status_code})")
except anthropic.APIConnectionError as err:
    sys.exit(f"Failed: {type(err).__name__}")

print(reply.content[0].text)
