"""Deal and error-fare feeds - the part no price API can give you.

A price API answers "what does *this* route cost". It cannot answer "where is
something absurdly cheap right now" - and that second question is where the
real savings are. Error fares, flash sales and mistake pricing get spotted by
people, published within minutes, and are gone in hours.

Several deal sites publish plain RSS, free and without any key. Verified live
(06.08.2026): urlaubspiraten.de, travelfree.info and fly4free.com all return
valid RSS 2.0. secretflying.com serves HTML on /feed/ and is therefore not
included - a scraper for it would break on their next redesign.

Deliberately **not** parsed into Offers with prices: a headline like "Mallorca
ab 39 EUR" is an advertisement, not a bookable itinerary for the user's dates.
Turning it into a priced row would repeat the exact mistake this project has
already made once. These are links with titles, presented as what they are.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone

import requests

# Free, key-less RSS. Each entry is (label, url, language).
DEAL_FEEDS = [
    ("Urlaubspiraten", "https://www.urlaubspiraten.de/feed", "de"),
    ("Travelfree", "https://travelfree.info/feed/", "en"),
    ("Fly4free", "https://www.fly4free.com/feed/", "en"),
]

HEADERS = {
    "User-Agent": "HackYourTrip/1.0 (+https://github.com/kalivolut/hackyourtrip)",
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}

MAX_ITEMS_PER_FEED = 15
_TAG_RE = re.compile(r"<[^>]+>")


@dataclass
class DealPost:
    """One published deal. No price field on purpose - see module docstring."""
    source: str
    title: str
    url: str
    published: str = ""
    summary: str = ""

    def mentions(self, *needles: str) -> bool:
        """Does this post mention any of these places? Used to surface the
        handful of posts relevant to a route instead of a generic feed."""
        haystack = f"{self.title} {self.summary}".lower()
        return any(n.lower() in haystack for n in needles if n and len(n) > 2)


def _text(node, tag: str) -> str:
    found = node.find(tag)
    return (found.text or "").strip() if found is not None and found.text else ""


def _strip_html(value: str, limit: int = 240) -> str:
    return _TAG_RE.sub("", value).strip()[:limit]


def fetch_feed(label: str, url: str, session: requests.Session | None = None) -> list[DealPost]:
    """One feed's recent posts; never raises - a dead feed must not take the
    others (or the whole run) down."""
    session = session or requests.Session()
    try:
        resp = session.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
    except (requests.RequestException, ET.ParseError) as exc:
        print(f"[dealfeeds] {label} failed: {exc}")
        return []

    posts = []
    for item in root.iter("item"):
        title = _text(item, "title")
        link = _text(item, "link")
        if not title or not link:
            continue
        posts.append(DealPost(
            source=label,
            title=_strip_html(title, 200),
            url=link,
            published=_text(item, "pubDate"),
            summary=_strip_html(_text(item, "description")),
        ))
        if len(posts) >= MAX_ITEMS_PER_FEED:
            break
    return posts


def fetch_all(session: requests.Session | None = None) -> list[DealPost]:
    session = session or requests.Session()
    posts: list[DealPost] = []
    for label, url, _lang in DEAL_FEEDS:
        posts.extend(fetch_feed(label, url, session))
    return posts


def relevant_for(posts: list[DealPost], *places: str, limit: int = 8) -> list[DealPost]:
    """Posts mentioning any of the given places, newest-feed order preserved.

    Falls back to nothing rather than to "here are some random deals": an
    unrelated Mallorca offer is noise on a Hamburg->Lyon search.
    """
    return [p for p in posts if p.mentions(*places)][:limit]


def as_dicts(posts: list[DealPost]) -> list[dict]:
    return [{"source": p.source, "title": p.title, "url": p.url,
             "published": p.published, "summary": p.summary} for p in posts]
