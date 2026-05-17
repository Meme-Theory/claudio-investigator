"""Album-art analysis via Claude vision.

This tool is special — it's the only one that costs us Anthropic tokens
*and* it's how the synthetic-album-art signal lands. The agent should reach
for it sparingly, when cheaper signals are ambiguous.

The runner enforces a per-investigation vision-pass cap via the budget; the
agent itself doesn't need to track it.

Implementation note (Phase 4): use a small, focused vision prompt that asks
specifically about Midjourney/SD fingerprints — banding artifacts, hand
malformations, signature compositional patterns. Don't ask the model to
"describe the image"; ask it to identify AI tells.
"""

from __future__ import annotations

from typing import Any

TOOLS = [
    {
        "name": "analyze_album_art",
        "description": (
            "Run a Claude vision pass on an album-cover image URL. Returns an "
            "assessment of AI-generation likelihood and specific fingerprints "
            "(Midjourney / Stable Diffusion / etc.) detected. EXPENSIVE — use only "
            "when metadata signals are ambiguous. Limited to 2 calls per investigation."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"image_url": {"type": "string"}},
            "required": ["image_url"],
        },
    },
]


def analyze_album_art(image_url: str, *, budget=None, **_: Any) -> dict:
    """Vision pass; charges the budget for both the pass-count and tokens."""
    raise NotImplementedError("Phase 4.")


RUNNERS = {"analyze_album_art": analyze_album_art}
