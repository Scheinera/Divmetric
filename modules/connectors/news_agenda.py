"""Agenda / notícias — RSS + notícias BCB (camada editorial operacional)."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from typing import Any
from urllib.parse import urlparse

import requests

TIMEOUT = 25
UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/rss+xml, application/xml, text/xml, application/json, */*",
}

FEEDS = [
    {
        "id": "infomoney",
        "label": "InfoMoney",
        "url": "https://www.infomoney.com.br/feed/",
        "trust": "editorial",
    },
    {
        "id": "moneytimes",
        "label": "Money Times",
        "url": "https://www.moneytimes.com.br/feed/",
        "trust": "editorial",
    },
    {
        "id": "agenciabrasil",
        "label": "Agência Brasil",
        "url": "https://agenciabrasil.ebc.com.br/rss/ultimasnoticias/feed.xml",
        "trust": "official_editorial",
    },
]

KEYWORDS = {
    "copom": ["copom", "selic", "banco central", "política monetária"],
    "earnings_br": ["balanço", "resultado", "lucro", "trimestral", "divulga resultado"],
    "earnings_world": ["earnings", "results", "quarter", "guidance"],
    "markets": ["ibovespa", "ifix", "dólar", "petróleo", "minério", "bolsa", "nasdaq", "s&p"],
}


def _strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", unescape(text)).strip()


def _parse_rss(xml_bytes: bytes, source_id: str, source_label: str) -> list[dict[str, Any]]:
    root = ET.fromstring(xml_bytes)
    items = []
    for node in root.findall(".//item")[:40]:
        title = _strip_html(node.findtext("title") or "")
        link = (node.findtext("link") or "").strip()
        desc = _strip_html(node.findtext("description") or "")
        pub = node.findtext("pubDate") or node.findtext("{http://purl.org/dc/elements/1.1/}date")
        published = None
        if pub:
            try:
                published = parsedate_to_datetime(pub).astimezone(timezone.utc).isoformat()
            except Exception:
                published = pub
        if not title:
            continue
        items.append(
            {
                "title": title[:220],
                "url": link,
                "summary": desc[:280] if desc else None,
                "published_at": published,
                "source_id": source_id,
                "source_label": source_label,
            }
        )
    return items


def _tag_item(item: dict[str, Any]) -> list[str]:
    blob = f"{item.get('title','')} {item.get('summary') or ''}".lower()
    tags = []
    for tag, words in KEYWORDS.items():
        if any(w in blob for w in words):
            tags.append(tag)
    return tags or ["geral"]


def fetch_bcb_noticias(limit: int = 12) -> list[dict[str, Any]]:
    url = f"https://www.bcb.gov.br/api/servico/sitebcb/noticias?quantidade={limit}"
    res = requests.get(url, timeout=TIMEOUT, headers=UA)
    res.raise_for_status()
    payload = res.json()
    out = []
    for row in payload.get("conteudo") or []:
        title = row.get("titulo") or ""
        if not title:
            continue
        out.append(
            {
                "title": title[:220],
                "url": f"https://www.bcb.gov.br{row.get('url')}" if row.get("url") and str(row.get("url")).startswith("/") else row.get("url"),
                "summary": _strip_html(row.get("corpo") or row.get("conteudo") or "")[:280] or None,
                "published_at": row.get("dataPublicacao") or row.get("Data"),
                "source_id": "bcb",
                "source_label": "Banco Central",
                "tags": ["copom", "oficial"] if "copom" in title.lower() or "selic" in title.lower() else ["oficial"],
            }
        )
    return out


def fetch_news_and_digest(limit_per_feed: int = 12) -> dict[str, Any]:
    errors: list[str] = []
    all_items: list[dict[str, Any]] = []

    for feed in FEEDS:
        try:
            res = requests.get(feed["url"], timeout=TIMEOUT, headers=UA)
            res.raise_for_status()
            parsed = _parse_rss(res.content, feed["id"], feed["label"])[:limit_per_feed]
            for item in parsed:
                item["tags"] = _tag_item(item)
                all_items.append(item)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{feed['id']}: {exc}")

    try:
        for item in fetch_bcb_noticias(10):
            all_items.append(item)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"bcb_noticias: {exc}")

    # dedupe by title
    seen = set()
    unique = []
    for item in all_items:
        key = (item.get("title") or "").lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)

    def sort_key(x: dict[str, Any]) -> str:
        return x.get("published_at") or ""

    unique = sorted(unique, key=sort_key, reverse=True)

    by_tag: dict[str, list] = {}
    for item in unique:
        for tag in item.get("tags") or ["geral"]:
            by_tag.setdefault(tag, []).append(item)

    highlights = unique[:12]
    copom_news = (by_tag.get("copom") or [])[:8]
    earnings = (by_tag.get("earnings_br") or [])[:8] + (by_tag.get("earnings_world") or [])[:4]
    markets = (by_tag.get("markets") or [])[:10]

    return {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "as_of": datetime.now(timezone.utc).date().isoformat(),
        "status": "live",
        "source": "RSS InfoMoney/Money Times/Agência Brasil + API notícias BCB",
        "feeds": [{"id": f["id"], "label": f["label"], "url": f["url"]} for f in FEEDS],
        "highlights": highlights,
        "copom_related": copom_news,
        "earnings": earnings[:10],
        "markets": markets,
        "all_count": len(unique),
        "errors": errors,
        "disclaimer": "Seleção automática por palavras-chave. Editorial — não é recomendação.",
    }
