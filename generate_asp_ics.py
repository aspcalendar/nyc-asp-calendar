#!/usr/bin/env python3
import json
import os
import glob
import hashlib
from datetime import datetime, date, timedelta

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(REPO_ROOT, "data")
OUT_ICS = os.path.join(REPO_ROOT, "docs", "asp.ics")

# If you previously added a "test" date, set this to False (or just remove the test date from JSON).
TEST_MODE = False

EMOJI_BY_KEYWORD = [
    ("christmas", "🎄"),
    ("new year", "🎆"),
    ("thanksgiving", "🦃"),
    ("independence", "🇺🇸"),
    ("july 4", "🇺🇸"),
    ("memorial", "🪖"),
    ("labor", "🔧"),
    ("columbus", "🧭"),
    ("veterans", "🎖️"),
    ("mlk", "✊"),
    ("martin luther king", "✊"),
    ("easter", "🐣"),
    ("good friday", "✝️"),
    ("passover", "🍷"),
    ("rosh hashanah", "🍎"),
    ("yom kippur", "🕯️"),
    ("hanukkah", "🕎"),
    ("ramadan", "🌙"),
    ("eid", "🌙"),
    ("diwali", "🪔"),
    ("lunar new year", "🧧"),
    ("juneteenth", "🖤"),
]

DEFAULT_EMOJI = "🚫"


def emoji_for(holiday_names: list[str]) -> str:
    joined = " ".join(holiday_names).lower()
    for key, emo in EMOJI_BY_KEYWORD:
        if key in joined:
            return emo
    return DEFAULT_EMOJI


def ics_escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace(";", r"\;")
        .replace(",", r"\,")
        .replace("\n", r"\n")
    )


def uid_for(d: date, title: str) -> str:
    raw = f"{d.isoformat()}|{title}"
    h = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return f"asp-{d.strftime('%Y%m%d')}-{h}@aspcalendar"


def load_all_suspensions() -> dict[date, list[str]]:
    """
    Expects files like:
      data/asp_suspensions_2026.json
    with shape:
      { "2026-12-25": ["Christmas Day", "…"], ... }
    """
    merged: dict[date, list[str]] = {}

    for path in sorted(glob.glob(os.path.join(DATA_DIR, "asp_suspensions_*.json"))):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for day_str, names in data.items():
            d = datetime.strptime(day_str, "%Y-%m-%d").date()
            if not isinstance(names, list):
                names = [str(names)]
            # Merge / de-dupe names for same day
            existing = merged.get(d, [])
            merged[d] = sorted(set(existing + [str(x) for x in names if str(x).strip()]))

    # Optional: add a temporary test event (turn off by setting TEST_MODE=False)
    if TEST_MODE:
        tomorrow = date.today() + timedelta(days=1)
        merged[tomorrow] = sorted(set(merged.get(tomorrow, []) + ["TEST — ASP Suspended"]))

    return merged


def build_ics(events_by_day: dict[date, list[str]]) -> str:
    now_utc = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//NYC ASP Live//EN",
        "CALSCALE:GREGORIAN",
        "X-WR-CALNAME:NYC Alternate Side Parking (Suspensions)",
        "X-WR-TIMEZONE:America/New_York",
    ]

    for d in sorted(events_by_day.keys()):
        holidays = events_by_day[d]
        if not holidays:
            continue

        emo = emoji_for(holidays)
        holiday_text = " / ".join(holidays)
        summary = f"{emo} ASP Suspended — {holiday_text}"

        # All-day event: DTEND is next day (exclusive)
        dtstart = d.strftime("%Y%m%d")
        dtend = (d + timedelta(days=1)).strftime("%Y%m%d")

        description = (
            f"Alternate Side Parking is suspended.\n"
            f"Reason(s): {holiday_text}\n"
            f"Source: NYC 311 / NYC DOT"
        )

        uid = uid_for(d, summary)

        lines += [
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{now_utc}",
            f"DTSTART;VALUE=DATE:{dtstart}",
            f"DTEND;VALUE=DATE:{dtend}",
            f"SUMMARY:{ics_escape(summary)}",
            f"DESCRIPTION:{ics_escape(description)}",
            # 8:00am alert the day-of (works in Apple Calendar for subscribed calendars)
            "BEGIN:VALARM",
            "ACTION:DISPLAY",
            f"DESCRIPTION:{ics_escape(summary)}",
            "TRIGGER;RELATED=START:PT8H",
            "END:VALARM",
            "END:VEVENT",
        ]

    lines.append("END:VCALENDAR")
    return "\n".join(lines) + "\n"


def main():
    os.makedirs(os.path.dirname(OUT_ICS), exist_ok=True)
    events = load_all_suspensions()
    ics = build_ics(events)

    with open(OUT_ICS, "w", encoding="utf-8") as f:
        f.write(ics)

    print(f"Wrote {OUT_ICS} with {len(events)} suspended-day entries.")


if __name__ == "__main__":
    main()
