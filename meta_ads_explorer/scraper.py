from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, AsyncIterator
from urllib.parse import urlencode

from playwright.async_api import Response, async_playwright

from .models import Ad

AD_LIBRARY_BASE = "https://www.facebook.com/ads/library/"
GRAPHQL_PATH_HINTS = ("/api/graphql/", "/ads/library/async/search_ads/")


@dataclass
class SearchParams:
    country: str = "AR"
    query: str | None = None
    page_id: str | None = None
    ad_type: str = "all"  # all | political_and_issue_ads | employment_ads | housing_ads | credit_ads
    active_status: str = "active"  # active | inactive | all
    media_type: str = "all"  # all | image | meme | video | none
    search_type: str = "keyword_unordered"

    def to_url(self) -> str:
        params: dict[str, str] = {
            "active_status": self.active_status,
            "ad_type": self.ad_type,
            "country": self.country,
            "media_type": self.media_type,
            "search_type": self.search_type,
        }
        if self.query:
            params["q"] = self.query
        if self.page_id:
            params["view_all_page_id"] = self.page_id
            params.pop("search_type", None)
        return f"{AD_LIBRARY_BASE}?{urlencode(params)}"


def _parse_ts(ts: Any) -> datetime | None:
    if ts in (None, "", 0):
        return None
    try:
        if isinstance(ts, (int, float)):
            return datetime.fromtimestamp(int(ts), tz=timezone.utc)
        if isinstance(ts, str) and ts.isdigit():
            return datetime.fromtimestamp(int(ts), tz=timezone.utc)
    except (ValueError, OSError):
        return None
    return None


def _walk_for_ads(obj: Any) -> list[dict]:
    """Recorre recursivamente la respuesta y junta dicts que parecen tarjetas de anuncio."""
    found: list[dict] = []

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            if "ad_archive_id" in node and isinstance(node.get("ad_archive_id"), (str, int)):
                found.append(node)
            for v in node.values():
                visit(v)
        elif isinstance(node, list):
            for v in node:
                visit(v)

    visit(obj)
    return found


def _normalize_ad(raw: dict) -> Ad:
    snapshot = raw.get("snapshot") or {}
    cards = snapshot.get("cards") or []
    body = snapshot.get("body") or {}
    body_text = body.get("text") if isinstance(body, dict) else (body if isinstance(body, str) else None)

    images: list[str] = []
    videos: list[str] = []
    for src_key in ("original_image_url", "resized_image_url"):
        if snapshot.get(src_key):
            images.append(snapshot[src_key])
    for img in snapshot.get("images", []) or []:
        if isinstance(img, dict):
            url = img.get("original_image_url") or img.get("resized_image_url")
            if url:
                images.append(url)
    for vid in snapshot.get("videos", []) or []:
        if isinstance(vid, dict):
            url = vid.get("video_hd_url") or vid.get("video_sd_url") or vid.get("video_preview_image_url")
            if url:
                videos.append(url)
    for card in cards:
        if isinstance(card, dict):
            for k in ("original_image_url", "resized_image_url"):
                if card.get(k):
                    images.append(card[k])
            for k in ("video_hd_url", "video_sd_url"):
                if card.get(k):
                    videos.append(card[k])

    cta = snapshot.get("cta_text") or snapshot.get("call_to_action") or None
    link_url = snapshot.get("link_url") or snapshot.get("caption") or None

    return Ad(
        ad_archive_id=str(raw["ad_archive_id"]),
        page_id=str(raw.get("page_id")) if raw.get("page_id") else None,
        page_name=raw.get("page_name") or snapshot.get("page_name"),
        page_profile_uri=snapshot.get("page_profile_uri"),
        page_profile_picture_url=snapshot.get("page_profile_picture_url"),
        start_date=_parse_ts(raw.get("start_date") or raw.get("start_date_string")),
        end_date=_parse_ts(raw.get("end_date") or raw.get("end_date_string")),
        is_active=raw.get("is_active"),
        publisher_platforms=list(raw.get("publisher_platform") or raw.get("publisher_platforms") or []),
        body_text=body_text,
        title=snapshot.get("title"),
        caption=snapshot.get("caption"),
        cta_text=cta,
        cta_type=snapshot.get("cta_type"),
        link_url=link_url,
        images=list(dict.fromkeys(images)),
        videos=list(dict.fromkeys(videos)),
        currency=snapshot.get("currency"),
        raw=raw,
    )


async def _parse_response(resp: Response) -> list[dict]:
    """Parsea respuestas GraphQL que Meta a veces sirve como JSON multi-línea."""
    try:
        text = await resp.text()
    except Exception:
        return []
    if not text:
        return []

    chunks: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            chunks.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    if not chunks:
        try:
            chunks = [json.loads(text)]
        except json.JSONDecodeError:
            return []
    return chunks


class AdLibraryScraper:
    def __init__(self, headless: bool = True, scroll_delay: float = 1.8) -> None:
        self.headless = headless
        self.scroll_delay = scroll_delay

    async def scrape(
        self,
        params: SearchParams,
        max_ads: int = 100,
        max_scrolls: int = 40,
    ) -> AsyncIterator[Ad]:
        seen_ids: set[str] = set()
        ad_queue: asyncio.Queue[Ad] = asyncio.Queue()
        finished = asyncio.Event()
        url = params.to_url()

        async def handle_response(resp: Response) -> None:
            u = resp.url
            if not any(h in u for h in GRAPHQL_PATH_HINTS):
                return
            try:
                payloads = await _parse_response(resp)
            except Exception:
                return
            for p in payloads:
                for raw_ad in _walk_for_ads(p):
                    aid = str(raw_ad.get("ad_archive_id"))
                    if not aid or aid in seen_ids:
                        continue
                    seen_ids.add(aid)
                    try:
                        await ad_queue.put(_normalize_ad(raw_ad))
                    except Exception:
                        continue

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=self.headless)
            context = await browser.new_context(
                viewport={"width": 1366, "height": 900},
                locale="es-AR",
                user_agent=(
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
                ),
            )
            page = await context.new_page()
            page.on("response", lambda r: asyncio.create_task(handle_response(r)))

            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
            except Exception as e:
                await browser.close()
                raise RuntimeError(f"No se pudo abrir Ad Library: {e}") from e

            # Cierra el modal de cookies/login si aparece.
            for selector in ('div[aria-label="Allow all cookies"]', 'div[aria-label="Permitir todas las cookies"]'):
                try:
                    btn = await page.query_selector(selector)
                    if btn:
                        await btn.click()
                        await page.wait_for_timeout(500)
                except Exception:
                    pass

            scrolls = 0
            stagnant = 0
            last_count = 0
            while scrolls < max_scrolls and len(seen_ids) < max_ads:
                await page.mouse.wheel(0, 2400)
                await asyncio.sleep(self.scroll_delay)
                scrolls += 1
                while not ad_queue.empty() and len(seen_ids) < max_ads + 50:
                    ad = await ad_queue.get()
                    yield ad
                if len(seen_ids) == last_count:
                    stagnant += 1
                else:
                    stagnant = 0
                    last_count = len(seen_ids)
                if stagnant >= 4:
                    break

            # Drena lo que quedó pendiente.
            await asyncio.sleep(self.scroll_delay)
            while not ad_queue.empty():
                ad = await ad_queue.get()
                yield ad

            finished.set()
            await browser.close()


async def scrape_to_list(params: SearchParams, max_ads: int, headless: bool, scroll_delay: float) -> list[Ad]:
    scraper = AdLibraryScraper(headless=headless, scroll_delay=scroll_delay)
    ads: list[Ad] = []
    async for ad in scraper.scrape(params, max_ads=max_ads):
        ads.append(ad)
        if len(ads) >= max_ads:
            break
    return ads


PAGE_ID_RE = re.compile(r"view_all_page_id=(\d+)")


def extract_page_id_from_url(url: str) -> str | None:
    m = PAGE_ID_RE.search(url)
    return m.group(1) if m else None
