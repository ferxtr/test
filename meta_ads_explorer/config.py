from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str | None
    claude_model: str
    country: str
    db_path: Path
    creatives_dir: Path
    headless: bool
    scroll_delay: float

    @classmethod
    def load(cls) -> "Settings":
        return cls(
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
            claude_model=os.getenv("MAE_CLAUDE_MODEL", "claude-sonnet-4-6"),
            country=os.getenv("MAE_COUNTRY", "AR"),
            db_path=Path(os.getenv("MAE_DB_PATH", "./meta_ads.db")).expanduser(),
            creatives_dir=Path(os.getenv("MAE_CREATIVES_DIR", "./creatives")).expanduser(),
            headless=os.getenv("MAE_HEADLESS", "true").lower() in ("1", "true", "yes"),
            scroll_delay=float(os.getenv("MAE_SCROLL_DELAY", "1.8")),
        )
