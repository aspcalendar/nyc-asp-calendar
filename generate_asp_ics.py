import re
import hashlib
import datetime as dt
import requests
import feedparser
import os

SRC = "https://www.nyc.gov/apps/311/311Today.rss"
OUT = "docs/asp.ics"

def iso_date(s):
    try:
        return dt.date.fromisoformat(s.strip())
    except Exception:
        return None

def find_asp_status(text):
    m = re.search(r"(Alternate side parking[^.<\n]*)", text, flags=re.IGNORECASE)
    if not m:
        return None
    return re.sub(r"\s+", " ", m.group(1).strip())

def uid_for(day, summary):
    raw = f"{day.isoformat()}|{summary}".encode("utf-8")
    return f"nycasp-{hashlib.sha1(raw).hexdigest()}@nyc.gov"

def main():
    feed = feedparser.parse(requests.get(SRC, timeout=30).text)

    events = []
    for e in feed.entries:
        day = iso_date(e.get("dc_coverage", "") or "")
        if not day:
            continue

        html = ""
        if getattr(e, "content", None):
            html = e.content[0].value or ""
        else:
            html = e.get("summary", "") or ""

        text = html.replace("<br />", "\n").replace("<br/>", "\n")
        status = find_asp_status(text)
        if not status:
            continue

        if "suspend" in status.lower():
            summary = "NYC ASP: Suspended"
        else:
            summary = "NYC ASP: In Effect"

        events.append((day, summary, status))

    os.makedirs("docs", exist_ok=True)

    now = dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//NYC ASP Live//EN",
        "CALSCALE:GREGORIAN",
        "X-WR-CALNAME:NYC Alternate Side Parking (Live)",
    ]

    seen = set()
    for day, summary, desc in sorted(events):
        if day in seen:
            continue
        seen.add(day)

        lines += [
            "BEGIN:VEVENT",
            f"UID:{uid_for(day, summary)}",
            f"DTSTAMP:{now}",
            f"DTSTART;VALUE=DATE:{day.strftime('%Y%m%d')}",
            f"DTEND;VALUE=DATE:{(day + dt.timedelta(days=1)).strftime('%Y%m%d')}",
            f"SUMMARY:{summary}",
            f"DESCRIPTION:{desc}",
            "END:VEVENT",
        ]

    lines.append("END:VCALENDAR")

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

if __name__ == "__main__":
    main()
