from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import httpx
from anthropic import Anthropic

from .config import Settings
from .models import Ad

SYSTEM_PROMPT = """Sos un analista senior de publicidad en Meta Ads (Facebook/Instagram).
Para cada anuncio te paso copy + creatividades. Devolvés SIEMPRE un JSON válido con esta forma:

{
  "angle": "string - el ángulo principal del mensaje (ej: 'miedo a perder oportunidad', 'aspiracional', 'descuento agresivo', 'autoridad/experto', etc.)",
  "hook": "string - el hook de las primeras 3 líneas / primer frame",
  "format": "image|video|carousel|reels|story|unknown",
  "audience_signal": "string - audiencia inferida por tono, edad, intereses",
  "pain_points": ["lista", "de", "dolores", "abordados"],
  "promises": ["lista", "de", "promesas/beneficios"],
  "cta_strength": "weak|medium|strong",
  "ad_type": "lead_gen|sales|brand|awareness|community|other",
  "originality": 1-10,
  "estimated_quality": 1-10,
  "red_flags": ["claims dudosos, exageraciones, faltantes legales, etc."],
  "key_phrases": ["frases clave verbatim del copy"],
  "summary": "1-2 oraciones en español rioplatense, directo"
}

No incluyas texto fuera del JSON. No uses bloques de markdown."""


def _download_image(url: str, dest: Path, timeout: float = 20.0) -> Path | None:
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            r = client.get(url)
            r.raise_for_status()
            content = r.content
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)
        return dest
    except Exception:
        return None


def _image_to_b64(path: Path) -> tuple[str, str] | None:
    suffix = path.suffix.lower().lstrip(".")
    media_type = {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "webp": "image/webp",
        "gif": "image/gif",
    }.get(suffix, "image/jpeg")
    try:
        data = base64.standard_b64encode(path.read_bytes()).decode("ascii")
    except OSError:
        return None
    return media_type, data


class CreativeAnalyzer:
    def __init__(self, settings: Settings) -> None:
        if not settings.anthropic_api_key:
            raise RuntimeError(
                "Falta ANTHROPIC_API_KEY en el entorno (.env). Necesario para análisis con Claude."
            )
        self.settings = settings
        self.client = Anthropic(api_key=settings.anthropic_api_key)

    def analyze(self, ad: Ad, max_images: int = 2) -> dict[str, Any]:
        creatives_dir = self.settings.creatives_dir / ad.ad_archive_id
        creatives_dir.mkdir(parents=True, exist_ok=True)

        image_blocks: list[dict[str, Any]] = []
        for idx, img_url in enumerate(ad.images[:max_images]):
            ext = Path(img_url.split("?")[0]).suffix or ".jpg"
            path = creatives_dir / f"img_{idx}{ext}"
            if not path.exists():
                _download_image(img_url, path)
            if not path.exists():
                continue
            encoded = _image_to_b64(path)
            if not encoded:
                continue
            media_type, data = encoded
            image_blocks.append(
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": media_type, "data": data},
                }
            )

        copy_block = {
            "type": "text",
            "text": json.dumps(
                {
                    "page_name": ad.page_name,
                    "title": ad.title,
                    "body_text": ad.body_text,
                    "caption": ad.caption,
                    "cta_text": ad.cta_text,
                    "cta_type": ad.cta_type,
                    "link_url": ad.link_url,
                    "platforms": ad.publisher_platforms,
                    "has_video": bool(ad.videos),
                    "video_preview_urls": ad.videos[:1],
                },
                ensure_ascii=False,
                indent=2,
            ),
        }

        response = self.client.messages.create(
            model=self.settings.claude_model,
            max_tokens=1200,
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[
                {
                    "role": "user",
                    "content": [
                        *image_blocks,
                        copy_block,
                        {
                            "type": "text",
                            "text": "Analizá este anuncio y devolvé sólo el JSON pedido.",
                        },
                    ],
                }
            ],
        )

        text = "".join(block.text for block in response.content if getattr(block, "type", None) == "text").strip()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = {"raw_response": text, "parse_error": True}
        parsed["_meta"] = {
            "model": self.settings.claude_model,
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "cache_read_input_tokens": getattr(response.usage, "cache_read_input_tokens", 0),
            "cache_creation_input_tokens": getattr(response.usage, "cache_creation_input_tokens", 0),
            "images_analyzed": len(image_blocks),
        }
        return parsed
