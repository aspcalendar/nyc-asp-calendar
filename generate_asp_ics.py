import re
import hashlib
import datetime as dt
import requests
import feedparser
import os

SRC = "https://www.nyc.gov/apps/311/311Today.rss"
OUT = "docs/asp.ics"
TEST_MODE = True  # set True to create a test suspended event for today
TZID = "America/New_York"

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

    suspensions = []
    for e in feed.entries:
        day = iso_date(e.get("dc_coverage", "") or "")
        if not day:
            continue

        html = ""
        if getattr(e, "content", None):
            html = e.content[0].value or ""
        else:
            html = e.get("summary", "") or ""

        text = html.replace("<br />", "\n").replace("<br/>", "\n").replace("<br>", "\n")
        status = find_asp_status(text)
        if not status:
            continue

        if "suspend" in status.lower():
            suspensions.append((day, status))

    os.makedirs("docs", exist_ok=True)

    now = dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//NYC ASP Suspended Alerts//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:NYC ASP Suspended (All-Day + 8AM Alert)",
        f"X-WR-TIMEZONE:{TZID}",
    ]

    seen = set()
    for day, status in sorted(suspensions):
        if day in seen:
            continue
        seen.add(day)

        summary = "🚫🅿️ ASP SUSPENDED"

        lines += [
            "BEGIN:VEVENT",
            f"UID:{uid_for(day, summary)}",
            f"DTSTAMP:{now}",
            f"DTSTART;VALUE=DATE:{day.strftime('%Y%m%d')}",
            f"DTEND;VALUE=DATE:{(day + dt.timedelta(days=1)).strftime('%Y%m%d')}",
            f"SUMMARY:{summary}",
            f"DESCRIPTION:{status}",
            "BEGIN:VALARM",
            "TRIGGER:PT8H",  # 8 hours after 12:00 AM local = 8:00 AM
            "ACTION:DISPLAY",
            "DESCRIPTION:🚫🅿️ NYC Alternate Side Parking is SUSPENDED today.",
            "END:VALARM",
            "END:VEVENT",
        ]

        if TEST_MODE:
        day = dt.date.today()
        summary = "🚫🅿️ TEST: ASP SUSPENDED"
        lines += [
            "BEGIN:VEVENT",
            f"UID:{uid_for(day, summary)}",
            f"DTSTAMP:{now}",
            f"DTSTART;VALUE=DATE:{day.strftime('%Y%m%d')}",
            f"DTEND;VALUE=DATE:{(day + dt.timedelta(days=1)).strftime('%Y%m%d')}",
            f"SUMMARY:{summary}",
            "DESCRIPTION:Test event to verify alerts/subscription.",
            "BEGIN:VALARM",
            "TRIGGER:PT8H",
            "ACTION:DISPLAY",
            "DESCRIPTION:🚫🅿️ Test alert at 8AM ET.",
            "END:VALARM",
            "END:VEVENT",
        ]
lines.append("END:VCALENDAR")

    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))

if __name__ == "__main__":
    main()
