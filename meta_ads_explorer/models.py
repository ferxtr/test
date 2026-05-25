from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class Ad(BaseModel):
    """Anuncio normalizado desde la Ad Library."""

    ad_archive_id: str
    page_id: str | None = None
    page_name: str | None = None
    page_profile_uri: str | None = None
    page_profile_picture_url: str | None = None

    start_date: datetime | None = None
    end_date: datetime | None = None
    is_active: bool | None = None

    publisher_platforms: list[str] = Field(default_factory=list)
    body_text: str | None = None
    title: str | None = None
    caption: str | None = None
    cta_text: str | None = None
    cta_type: str | None = None
    link_url: str | None = None

    images: list[str] = Field(default_factory=list)
    videos: list[str] = Field(default_factory=list)

    impressions_text: str | None = None
    spend_text: str | None = None
    currency: str | None = None

    raw: dict[str, Any] = Field(default_factory=dict)
