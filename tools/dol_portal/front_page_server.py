"""One server's rows from saved DOL portal front-page captures (Wayback `id_` copies).

    python3 -I tools/dol_portal/front_page_server.py --server 11 --out data/dol-portal/uthgard-2-front-pages.csv PAGE.html...

Each PAGE is named <wayback timestamp>.html (14 digits, UTC). For every capture it writes one row: the capture
time, the server's name and online count as the front page shows them (empty when the server isn't listed), and
the newest "Record number of clients have connected (N)" item the page's news feed has for that server, with the
feed's own relative age ("3 weeks ago"). The record is per server. The pages themselves are not committed: they
are the Wayback Machine's, fetched one at a time from https://web.archive.org/web/<timestamp>id_/<url>.
"""
import argparse
import csv
import html
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

PORTAL = "http://www.dolserver.net/daocportal/"
ROW = re.compile(r"href='server\.php\?s=(\d+)'>([^<]*)</a>.*?<td[^>]*>\s*(\d+)\s*</td>", re.S)
RECORD = re.compile(r"Record number of clients have connected \((\d+)\)</p><p><a href='server\.php\?s=(\d+)'>"
                    r"[^<]*</a><br /><span[^>]*>([^<]*)<")
COLUMNS = ["captured_utc", "listed", "server", "players_online", "record_clients", "record_age", "archive_url"]


def parse(text, server):
    """(name, online) for the server's front-page row, or (None, None); and (record, age) from the news feed."""
    name = online = None
    for m in ROW.finditer(text):
        if m.group(1) == server:
            name, online = html.unescape(m.group(2)).strip(), int(m.group(3))
            break
    record = age = None
    for m in RECORD.finditer(text):  # the feed is newest first
        if m.group(2) == server:
            record, age = int(m.group(1)), m.group(3).strip()
            break
    return name, online, record, age


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", required=True, help="the portal's server id, e.g. 11 for Uthgard")
    ap.add_argument("--out", required=True)
    ap.add_argument("pages", nargs="+")
    a = ap.parse_args(argv)
    rows = []
    for p in sorted(a.pages):
        ts = Path(p).stem
        if not re.fullmatch(r"\d{14}", ts):
            sys.exit(f"{p}: name must be a 14-digit Wayback timestamp")
        when = datetime.strptime(ts, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
        name, online, record, age = parse(Path(p).read_text(encoding="latin-1"), a.server)
        rows.append({"captured_utc": when.strftime("%Y-%m-%dT%H:%M:%SZ"), "listed": "yes" if name else "no",
                     "server": name or "", "players_online": "" if online is None else online,
                     "record_clients": "" if record is None else record, "record_age": age or "",
                     "archive_url": f"https://web.archive.org/web/{ts}/{PORTAL}"})
    with open(a.out, "w", newline="") as f:
        w = csv.DictWriter(f, COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} rows -> {a.out}")


if __name__ == "__main__":
    main()
