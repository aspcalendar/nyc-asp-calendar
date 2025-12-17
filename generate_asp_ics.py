import os, json, re, hashlib, datetime as dt
import requests, feedparser

SRC = "https://www.nyc.gov/apps/311/311Today.rss"
OUT = "docs/asp.ics"
TZID = "America/New_York"

EMOJI_RULES = [
    (r"Christmas", "🎄"),
    (r"Thanksgiving", "🦃"),
    (r"New Year", "🎆"),
    (r"Independence Day", "🇺🇸"),
    (r"Election Day", "🗳️"),
    (r"Veterans", "🎖️"),
    (r"Memorial Day", "🪖"),
    (r"Juneteenth", "✊🏾"),
    (r"Diwali", "🪔"),
    (r"Lunar New Year", "🧧"),
    (r"(Eid|Idul)", "🌙"),
    (r"(Passover|Rosh Hashanah|Yom Kippur|Succoth|Shavuoth|Shemini|Simchas|Tisha)", "✡️"),
    (r"(Holy Thursday|Good Friday|Ascension|All Saints|Immaculate|Assumption)", "✝️"),
]

def iso_date(s):
    try: return dt.date.fromisoformat(s.strip())
    except Exception: return None

def find_asp_status(text):
    m = re.search(r"(Alternate side parking[^.<\n]*)", text, flags=re.IGNORECASE)
    if not m: return None
    return re.sub(r"\s+", " ", m.group(1).strip())

def uid_for(day, summary):
    raw = f"{day.isoformat()}|{summary}".encode("utf-8")
    return f"nycasp-{hashlib.sha1(raw).hexdigest()}@nyc.gov"

def emojis_for(holiday_names):
    s = " / ".join(holiday_names)
    out = []
    for pat, emo in EMOJI_RULES:
        if re.search(pat, s, flags=re.IGNORECASE) and emo not in out:
            out.append(emo)
    return "".join(out)

def load_scheduled():
    scheduled = {}  # date -> [holiday names]
    data_dir = "data"
    if not os.path.isdir(data_dir):
        return scheduled
    for fn in os.listdir(data_dir):
        if not fn.startswith("asp_suspensions_") or not fn.endswith(".json"):
            continue
        path = os.path.join(data_dir, fn)
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
        for date_str, names in d.items():
            scheduled.setdefault(date_str, [])
            for n in names:
                if n not in scheduled[date_str]:
                    scheduled[date_str].append(n)
    return scheduled

def load_live_suspensions():
    live = {}  # date -> status line
    feed = feedparser.parse(requests.get(SRC, timeout=30).text)
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
        if status and "suspend" in status.lower():
            live[day.isoformat()] = status
    return live

def main():
    scheduled = load_scheduled()
    live = load_live_suspensions()

    # union of scheduled + live suspended
    all_dates = set(scheduled.keys()) | set(live.keys())

    os.makedirs("docs", exist_ok=True)
    now = dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//NYC ASP Suspended (Scheduled + Live)//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:NYC ASP Suspended (All-Day + 8AM Alert)",
        f"X-WR-TIMEZONE:{TZID}",
    ]

    for date_str in sorted(all_dates):
        day = dt.date.fromisoformat(date_str)

        holiday_names = scheduled.get(date_str, [])
        status_line = live.get(date_str)

        # Build title (include holidays if we have them)
        title_parts = []
        if holiday_names:
            title_parts.append(" / ".join(holiday_names))
        # If live-only, keep title generic but still clear
        if not title_parts:
            title_parts.append("NYC 311")

        emo = emojis_for(holiday_names) or "🚫🅿️"
        summary = f"🚫🅿️ Suspended — {title_parts[0]} {emo}".strip()

        description = status_line or ("ASP suspension (scheduled).")

        lines += [
            "BEGIN:VEVENT",
            f"UID:{uid_for(day, summary)}",
            f"DTSTAMP:{now}",
            f"DTSTART;VALUE=DATE:{day.strftime('%Y%m%d')}",
            f"DTEND;VALUE=DATE:{(day + dt.timedelta(days=1)).strftime('%Y%m%d')}",
            f"SUMMARY:{summary}",
            f"DESCRIPTION:{description}",
            "BEGIN:VALARM",
            "TRIGGER:PT8H",
            "ACTION:DISPLAY",
            f"DESCRIPTION:{summary}",
            "END:VALARM",
            "END:VEVENT",
        ]

    lines.append("END:VCALENDAR")

    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))

if __name__ == "__main__":
    main()
