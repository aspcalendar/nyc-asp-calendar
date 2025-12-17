#!/usr/bin/env python3
"""
Generate a public ICS calendar of NYC Alternate Side Parking (ASP) SUSPENSIONS.

Behavior:
- Only creates events on dates when ASP is SUSPENDED.
- Scheduled suspensions come from: data/asp_suspensions_YYYY.json
  (e.g., data/asp_suspensions_2026.json)
- Live / same-day suspensions are detected from a NYC 311 status page (HTML scrape).
- Output file: docs/asp.ics (so GitHub Pages can serve it)

Event titles:
  🚫🅿️ Suspended — Christmas Day 🎄
  🚫🅿️ Suspended — Good Friday / Passover ✝️🕎
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
from typing import Dict, List, Optional, Tuple

import requests

# ----------------------------
# CONFIG
# ----------------------------

OUT_PATH = "docs/asp.ics"

# If you already have a working NYC 311 URL in your previous script, replace this.
LIVE_STATUS_URL = os.environ.get(
    "ASP_LIVE_STATUS_URL",
    "https://portal.311.nyc.gov/article/?kanumber=KA-01011",
)

# How many years forward to include scheduled JSON files if present
YEARS_FORWARD = int(os.environ.get("ASP_YEARS_FORWARD", "5"))

# Calendar display name
CAL_NAME = "NYC Alternate Side Parking — Suspensions (Live + Scheduled)"

# ----------------------------
# EMOJI / TITLE HELPERS
# ----------------------------

HOLIDAY_EMOJI = {
    "New Year": "🎉",
    "Martin Luther King": "✊🏽",
    "Presidents": "🇺🇸",
    "Lincoln": "🎩",
    "Washington": "🇺🇸",
    "Good Friday": "✝️",
    "Easter": "🐣",
    "Passover": "🕎",
    "Memorial Day": "🎖️",
    "Juneteenth": "✊🏿",
    "Independence Day": "🎆",
    "Labor Day": "🛠️",
    "Rosh Hashanah": "🍯",
    "Yom Kippur": "🙏",
    "Sukkoth": "🌿",
    "Thanksgiving": "🦃",
    "Christmas": "🎄",
    "Columbus": "🧭",
    "Veterans": "🎗️",
    "Election Day": "🗳️",
    "Lunar New Year": "🧧",
    "Ramadan": "🌙",
    "Eid": "🌙",
    "Ash Wednesday": "✝️",
    "Purim": "🎭",
    "All Saints": "⛪",
    "Halloween": "🎃",
}

SUSPENDED_PREFIX = "🚫🅿️ Suspended"

def emojis_for_holidays(holidays: List[str]) -> str:
    found: List[str] = []
    for h in holidays:
        for key, emo in HOLIDAY_EMOJI.items():
            if key.lower() in h.lower():
                found.append(emo)
    # de-dupe while preserving order
    seen = set()
    out = []
    for e in found:
        if e not in seen:
            seen.add(e)
            out.append(e)
    return "".join(out)

def build_summary(holidays: List[str]) -> str:
    if holidays:
        title = f"{SUSPENDED_PREFIX} — " + " / ".join(holidays)
        title += f" {emojis_for_holidays(holidays)}".rstrip()
        return title.strip()
    return SUSPENDED_PREFIX

# ----------------------------
# DATA LOADING
# ----------------------------

def load_scheduled_suspensions(start_year: int, years_forward: int) -> Dict[dt.date, List[str]]:
    """
    Loads all available data/asp_suspensions_YYYY.json files for a range of years.
    Each JSON is expected to be:
      { "YYYY-MM-DD": ["Holiday", "Holiday2"], ... }
    """
    susp: Dict[dt.date, List[str]] = {}

    for year in range(start_year, start_year + years_forward + 1):
        path = f"data/asp_suspensions_{year}.json"
        if not os.path.exists(path):
            continue

        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)

        for date_str, holidays in raw.items():
            try:
                d = dt.date.fromisoformat(date_str)
            except ValueError:
                continue
            if not isinstance(holidays, list):
                holidays = [str(holidays)]
            # merge if date already present
            existing = susp.get(d, [])
            merged = existing + [h for h in holidays if h not in existing]
            susp[d] = merged

    return susp

# ----------------------------
# LIVE (NYC 311) DETECTION
# ----------------------------

SUSPENDED_PATTERNS = [
    re.compile(r"\b(suspended)\b", re.IGNORECASE),
    re.compile(r"\b(not in effect)\b", re.IGNORECASE),
]
TODAY_PATTERNS = [
    re.compile(r"\btoday\b", re.IGNORECASE),
    re.compile(r"\bon\s+(\w+),?\s+(\w+)\s+(\d{1,2}),?\s+(\d{4})\b", re.IGNORECASE),
]

def fetch_live_today_suspension(url: str) -> Optional[Tuple[dt.date, List[str], str]]:
    """
    Best-effort HTML scrape of NYC 311 ASP status.
    Returns (date, holidays/reason list, raw_snippet) if it looks suspended.
    Otherwise None.

    This is intentionally conservative: if we can't confidently detect "suspended",
    we return None.
    """
    try:
        r = requests.get(url, timeout=20, headers={"User-Agent": "aspcalendar-bot/1.0"})
        r.raise_for_status()
        html = r.text
    except Exception:
        return None

    # Quick check for suspension keywords
    if not any(p.search(html) for p in SUSPENDED_PATTERNS):
        return None

    # We assume "today" if page indicates suspension; that's how NYC311 usually phrases it.
    today = dt.date.today()

    # Try to extract a "reason" line/snippet near the word "suspended"
    idx = html.lower().find("suspend")
    snippet = ""
    if idx != -1:
        snippet = re.sub(r"\s+", " ", html[max(0, idx - 120) : idx + 240])

    # Try to pull a holiday/reason name from the snippet
    # (Very light heuristic: look for “because …” or “for …” phrases.)
    reasons: List[str] = []
    m = re.search(r"(?:because of|for)\s+([A-Za-z0-9 ,’'\-()\/]+)", snippet, re.IGNORECASE)
    if m:
        reason = m.group(1).strip()
        # trim at first HTML tag boundary-ish
        reason = re.split(r"[<>{}\[\]\n\r]", reason)[0].strip()
        # keep it short
        if 3 <= len(reason) <= 80:
            reasons = [reason]

    if not reasons:
        reasons = ["NYC 311 update"]

    return (today, reasons, snippet)

# ----------------------------
# ICS WRITER
# ----------------------------

def ics_escape(s: str) -> str:
    return (
        s.replace("\\", "\\\\")
         .replace(";", r"\;")
         .replace(",", r"\,")
         .replace("\n", r"\n")
    )

def uid_for(date_: dt.date, summary: str) -> str:
    h = hashlib.sha1(f"{date_.isoformat()}|{summary}".encode("utf-8")).hexdigest()[:16]
    return f"asp-{date_.isoformat()}-{h}@aspcalendar"

def build_all_day_event(date_: dt.date, summary: str, description: str) -> List[str]:
    # All-day event: DTSTART;VALUE=DATE and DTEND;VALUE=DATE is next day
    dtend = date_ + dt.timedelta(days=1)
    now_utc = dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    return [
        "BEGIN:VEVENT",
        f"UID:{uid_for(date_, summary)}",
        f"DTSTAMP:{now_utc}",
        f"DTSTART;VALUE=DATE:{date_.strftime('%Y%m%d')}",
        f"DTEND;VALUE=DATE:{dtend.strftime('%Y%m%d')}",
        f"SUMMARY:{ics_escape(summary)}",
        f"DESCRIPTION:{ics_escape(description)}",
        "TRANSP:TRANSPARENT",
        "END:VEVENT",
    ]

def write_calendar(events: List[List[str]]) -> None:
    lines: List[str] = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//NYC ASP Suspensions//EN",
        "CALSCALE:GREGORIAN",
        f"X-WR-CALNAME:{ics_escape(CAL_NAME)}",
        "X-WR-TIMEZONE:America/New_York",
    ]

    for ev in events:
        lines.extend(ev)

    lines.append("END:VCALENDAR")

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))

# ----------------------------
# MAIN
# ----------------------------

def main() -> None:
    today = dt.date.today()
    scheduled = load_scheduled_suspensions(today.year, YEARS_FORWARD)

    # Optional: add a live “today” suspension if NYC311 indicates it
    live = fetch_live_today_suspension(LIVE_STATUS_URL)

    # Combine suspensions (one event per date)
    combined: Dict[dt.date, List[str]] = dict(scheduled)

    if live:
        d, reasons, _snippet = live
        if d in combined:
            # merge reasons into existing list (no duplicates)
            existing = combined[d]
            for r in reasons:
                if r not in existing:
                    existing.append(r)
            combined[d] = existing
        else:
            combined[d] = reasons

    # Build VEVENTs for ALL suspended days we know about
    # (Only suspended days are included; no “normal ASP” days)
    events: List[List[str]] = []
    for d in sorted(combined.keys()):
        holidays_or_reasons = combined[d]
        summary = build_summary(holidays_or_reasons)

        desc = (
            "NYC Alternate Side Parking is SUSPENDED.\n"
            "Sources: Scheduled suspension list + NYC 311 live status.\n"
            f"Generated: {dt.datetime.now().isoformat(timespec='seconds')}\n"
        )
        events.append(build_all_day_event(d, summary, desc))

    write_calendar(events)

if __name__ == "__main__":
    main()
