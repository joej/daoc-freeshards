#!/usr/bin/env python3
"""Turn the saved DOL portal server pages into data/dol-portal/server-pages-<date>.csv.

Reads raw/dol-portal/server-pages-<date>.jsonl.gz (written by crawl.py --pack, with public IP addresses and
email addresses redacted) and data/dol-portal/ip-info.csv (written by ip_info.py from the unredacted pages).
Standard library only; no network.

    python3 -I tools/dol_portal/parse.py

The portal shows dates as "5 years ago". Each is kept as written plus a range of months counted back from the
page's fetch time. The portal rounds down, so "5 years ago" means 5 to just under 6 years before the fetch,
and "1 decade ago" means 10 to 20 years.
"""

import csv
import gzip
import html
import ipaddress
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
IP_MARK = "[ip-redacted]"
BAD_IP_MARK = "[bad-ip-redacted]"
UNITS = {"second": 1 / 86400, "minute": 1 / 1440, "hour": 1 / 24, "day": 1, "week": 7, "month": 30.44,
         "year": 365.25, "decade": 3652.5}
FIELDS = ["portal_id", "name", "fetched_at", "type", "language", "home_page", "irc", "address", "address_kind",
          "ip_country", "ip_country_from", "network", "online", "online_players", "last_update", "last_update_from",
          "last_update_to", "peak_players", "record_max", "registered_name", "registered_ago", "registered_from",
          "registered_to", "news_count", "news", "managers", "image", "description"]


def text(fragment: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


def ago_range(phrase: str, fetched: datetime) -> tuple[str, str]:
    """'5 years ago' -> (earliest, latest) as YYYY-MM."""
    m = re.match(r"(\d+|an?|one)\s+(second|minute|hour|day|week|month|year|decade)s?\s+ago", phrase.strip())
    if not m:
        return "", ""
    n = 1 if m.group(1) in ("a", "an", "one") else int(m.group(1))
    days = UNITS[m.group(2)]
    latest = fetched - timedelta(days=n * days)
    earliest = fetched - timedelta(days=(n + 1) * days)
    return earliest.strftime("%Y-%m"), latest.strftime("%Y-%m")


def dotted_quad(s: str):
    """An IPv4 address written as four numbers, leading zeros allowed ("10.0.0.01"); "bad" if a number is over
    255; None if s isn't four dot-separated numbers."""
    parts = s.split(".")
    if len(parts) != 4 or not all(p.isdigit() and len(p) <= 3 for p in parts):
        return None
    if any(int(p) > 255 for p in parts):
        return "bad"
    return ipaddress.IPv4Address(".".join(str(int(p)) for p in parts))


def address_kind(host: str) -> str:
    host = host.strip()
    if not host:
        return "none"
    if host == IP_MARK:
        return "public"  # redacted: a public address
    if host == BAD_IP_MARK or dotted_quad(host) == "bad":
        return "invalid"  # four numbers, one over 255: mistyped
    try:
        ip = dotted_quad(host) or ipaddress.ip_address(host)
    except ValueError:
        return "hostname"
    if ip.is_loopback:
        return "loopback"
    if ip.is_private or ip.is_link_local or ip.is_reserved or ip.is_unspecified:
        return "private"
    return "public"


def connect_address(page: str) -> tuple[str, str]:
    """The host and port of the page's "Connect" link (daoc://host:port)."""
    bar = page[page.find("<h1>"):page.find("Server Description")]
    m = re.search(r'href="daoc://([^"]*)"', bar)
    hostport = m.group(1) if m else ""
    if ":" in hostport:
        host, _, port = hostport.rpartition(":")
        return host, port
    return hostport, ""


def parse(sid: int, page: str, fetched: datetime) -> dict:
    r = {"portal_id": sid, "fetched_at": fetched.strftime("%Y-%m-%dT%H:%M:%SZ")}
    m = re.search(r"<h1>(.*?)</h1>", page, re.S)
    r["name"] = text(m.group(1)) if m else ""
    bar = page[page.find("<h1>"):page.find("Server Description")]
    m = re.search(r'<a href="([^"]+)">Home Page</a>', bar)
    r["home_page"] = m.group(1) if m else ""
    m = re.search(r'<a href="(irc://[^"]+)">IRC</a>', bar)
    r["irc"] = m.group(1) if m else ""
    host, port = connect_address(page)
    r["address"] = f"{host}:{port}" if port else host
    r["address_kind"] = address_kind(host)
    m = re.search(r"<b>(Online|Offline)</b>\s*(?:(\d+)\s*Players)?", bar)
    r["online"], r["online_players"] = (m.group(1), m.group(2) or "") if m else ("", "")

    m = re.search(r"Server Description</h2>(.*?)</div>", page, re.S)
    r["description"] = text(m.group(1)) if m else ""

    info = page[page.find("Server Info</h2>"):]
    m = re.search(r'<img src="([^"]+)" alt="Server Image"', info)
    img = m.group(1) if m else ""
    r["image"] = "" if "noimage.png" in img else img
    for key, pat in [("type", r"type of this server is set as <strong>(.*?)</strong>"),
                     ("language", r"language for this server is set as <strong>(.*?)</strong>"),
                     ("last_update", r"last update we received from this server was <strong>(.*?)</strong>"),
                     ("peak_players", r"most players we have seen on this server is <strong>(\d+)</strong>")]:
        m = re.search(pat, info, re.S)
        r[key] = text(m.group(1)) if m else ""
    r["last_update_from"], r["last_update_to"] = ago_range(r["last_update"], fetched)

    # News: the latest item (a large paragraph and a grey one) and older items (list entries with two spans).
    news = []
    sect = page[page.find("Latest News</h2>"):page.find("Server Reviews")]
    for m in re.finditer(r"<p style='font-size:1.7em;'>(.*?)</p><p[^>]*>(.*?)</p>", sect, re.S):
        news.append((text(m.group(1)), text(m.group(2))))
    for m in re.finditer(r"<li><span[^>]*>(.*?)</span><br />\s*<span[^>]*>(.*?)</span></li>", sect, re.S):
        news.append((text(m.group(1)), text(m.group(2))))
    r["news_count"] = len(news)
    reg = next(((t, a) for t, a in news if "has registered a new server" in t), None)
    r["registered_ago"] = reg[1] if reg else ""
    r["registered_from"], r["registered_to"] = ago_range(reg[1], fetched) if reg else ("", "")
    m = re.search(r"registered a new server '(.*?)'", reg[0]) if reg else None
    r["registered_name"] = m.group(1) if m else ""
    records = [int(re.search(r"\((\d+)\)", t).group(1)) for t, _ in news
               if t.startswith("Record number") and re.search(r"\((\d+)\)", t)]
    r["record_max"] = max(records, default="")
    r["news"] = " | ".join(f"{a}: {t}" for t, a in news)

    mgr = page[page.find("Server Managers</h2>"):]
    mgr = mgr[:mgr.find("</ul>")]
    r["managers"] = "; ".join(f"{text(n)} {text(role)}" for n, role in
                              re.findall(r"class='username-coloured'>(.*?)</a><br />(\(.*?\))", mgr)) or \
        "; ".join(text(n) for n in re.findall(r"memberlist\.php[^>]*>(.*?)</a>", mgr))
    return r


def placeholder(host: str) -> bool:
    """Addresses typed in as filler: 1.1.1.1, 55.55.55.55, 1.2.3.4, 123.123.123.123 and the like."""
    o = host.split(".")
    return len(set(o)) == 1 or host.startswith(("1.1.1.", "1.2.3.", "123.12.34.", "123.123.", "222.222.", "111.111."))


def ip_info() -> dict:
    """portal_id -> {"network": ..., snapshot day: country, ...} from ip-info.csv."""
    path = ROOT / "data/dol-portal/ip-info.csv"
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as f:
        return {int(row.pop("portal_id")): row for row in csv.DictReader(f)}


def months(ym: str) -> int:
    return int(ym[:4]) * 12 + int(ym[5:7])


def country_for(snapshots: dict, last_from: str, last_to: str) -> tuple[str, str]:
    """The registered country on the snapshot day nearest the entry's last report, skipping days with none."""
    when = (months(last_from) + months(last_to)) / 2
    for day in sorted(snapshots, key=lambda d: abs(months(d) - when)):
        if snapshots[day]:
            return snapshots[day], day
    return "", ""


def build(raw: Path) -> list[dict]:
    info = ip_info()
    rows = []
    with gzip.open(raw, "rt", encoding="utf-8") as f:
        for line in f:
            p = json.loads(line)
            r = parse(p["id"], p["html"], datetime.strptime(p["fetched_at"], "%Y-%m-%dT%H:%M:%SZ"))
            # A country only for entries that reported to the portal at least once: an address typed into an entry
            # that never ran shows nothing about where a server was.
            reported = r["last_update"] not in ("", "Never")
            row = dict(info.get(p["id"], {}))
            r["network"] = row.pop("network", "")
            r["ip_country"], r["ip_country_from"] = "", ""
            if reported and r["last_update_from"] and row:
                r["ip_country"], r["ip_country_from"] = country_for(row, r["last_update_from"], r["last_update_to"])
            rows.append({k: r[k] for k in FIELDS})
    return rows


def write(rows: list[dict], out: Path) -> None:
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def main() -> int:
    for raw in sorted((ROOT / "raw/dol-portal").glob("server-pages-*.jsonl.gz")):
        out = ROOT / "data/dol-portal" / raw.name.replace(".jsonl.gz", ".csv")
        rows = build(raw)
        write(rows, out)
        print(f"{len(rows)} pages -> {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
