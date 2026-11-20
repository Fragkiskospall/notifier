"""RSS/Atom → Item."""
from __future__ import annotations

import feedparser

from .models import Item
from .text import clean_text


def parse_feed(content: bytes, source: str, uid_prefix: str) -> list[Item]:
    feed = feedparser.parse(content)
    items = []
    for e in feed.entries:
        key = e.get("id") or e.get("guid") or e.get("link") or e.get("title")
        if not key:
            continue
        summary = e.get("summary", "")
        if not clean_text(summary) and e.get("content"):
            summary = e.content[0].get("value", "")
        items.append(Item(
            uid=f"{uid_prefix}:{key}",
            source=source,
            title=clean_text(e.get("title", "(χωρίς τίτλο)"), 200),
            link=e.get("link", ""),
            summary=clean_text(summary),
        ))
    return items
