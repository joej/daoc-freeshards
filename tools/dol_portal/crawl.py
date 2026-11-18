#!/usr/bin/env python3
"""Save every DOL portal server page (dolserver.sourceforge.net/serverlisting/server.php?s=N) to SQLite.

Polite by design:
- one request at a time, --delay seconds apart (default 10);
- a descriptive User-Agent with a contact URL;
- honours Retry-After on 429/503 and backs off on errors; an id that fails twice is recorded as broken and skipped; stops after --max-server-errors (default 3) different ids fail in a row;
- stops at once on 403: if the site starts refusing us, we don't work around it;
- resumable: IDs already saved are skipped.

Pages are stored raw (gzip) with the fetch time, so parsing can be redone later without fetching again.
The working database (raw/dol-portal/pages.sqlite) is not committed; --pack writes the server pages to the
committed file raw/dol-portal/server-pages-<date>.jsonl.gz, which parse.py reads, with public IP addresses and
email addresses redacted. ip_info.py reads the working database for what it needs from the addresses.

Usage:
    python3 -I tools/dol_portal/crawl.py                  # IDs 1.. until --stop-after misses past the last hit
    python3 -I tools/dol_portal/crawl.py --start 1190 --end 1210
    python3 -I tools/dol_portal/crawl.py --recheck 50     # after a crawl: is "not found" reliable?
    python3 -I tools/dol_portal/crawl.py --pack raw/dol-portal/server-pages-2026-11-18.jsonl.gz
"""

import argparse
import gzip
import hashlib
import json
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import parse  # noqa: E402

BASE = "https://dolserver.sourceforge.net/serverlisting/server.php?s={}"
UA = "daoc-freeshards-archiver/0.1 (+https://github.com/joej/daoc-freeshards)"
NOT_FOUND = b"Server not found!"

SCHEMA = """
CREATE TABLE IF NOT EXISTS pages (
    id          INTEGER PRIMARY KEY,   -- portal server id (s=)
    status      INTEGER NOT NULL,      -- HTTP status
    found       INTEGER NOT NULL,      -- 1 = a server page, 0 = "Server not found!"
    fetched_at  TEXT NOT NULL,         -- UTC, ISO 8601
    sha256      TEXT NOT NULL,         -- of the decoded body
    html_gz     BLOB NOT NULL          -- gzip of the decoded body
);
CREATE TABLE IF NOT EXISTS rechecks (      -- second fetches of "not found" ids, to test whether "not found" is reliable
    id          INTEGER NOT NULL,
    fetched_at  TEXT NOT NULL,
    status      INTEGER NOT NULL,
    found       INTEGER NOT NULL,
    html_gz     BLOB NOT NULL
);
"""


def recheck(db: sqlite3.Connection, n: int, delay: float) -> int:
    """Fetch a random sample of n "not found" ids again. A changed answer means "not found" can't be trusted."""
    ids = [r[0] for r in db.execute(
        "SELECT id FROM pages WHERE status = 200 AND found = 0 ORDER BY random() LIMIT ?", (n,))]
    flipped = []
    for i, sid in enumerate(ids, 1):
        status, body, _ = fetch(sid)
        found = int(status == 200 and NOT_FOUND not in body)
        db.execute("INSERT INTO rechecks VALUES (?, ?, ?, ?, ?)", (sid, now(), status, found, gzip.compress(body)))
        db.commit()
        if status == 403:
            print(f"s={sid} 403: stopping", flush=True)
            return 2
        if found:
            flipped.append(sid)
            # Keep the real page: it replaces the wrong "not found".
            db.execute("INSERT OR REPLACE INTO pages VALUES (?, ?, 1, ?, ?, ?)",
                       (sid, status, now(), hashlib.sha256(body).hexdigest(), gzip.compress(body)))
            db.commit()
        print(f"[{i}/{len(ids)}] s={sid} {status} {'FOUND (was not found)' if found else 'still not found' if status == 200 else 'error'}",
              flush=True)
        time.sleep(delay)
    print(f"recheck done: {len(flipped)} of {len(ids)} changed to found: {flipped}", flush=True)
    return 0


EMAIL_MARK = "[email-redacted]"
IPV4 = re.compile(r"(?<![\d.])\d{1,3}(?:\.\d{1,3}){3}(?![\d.])")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def redact(page: str) -> str:
    """Blank public IPv4 addresses and email addresses.

    Many servers ran from someone's home connection, and those addresses have since passed to other households,
    so the published pages don't carry them. Addresses typed with leading zeros count ("08.08.8.8"); ones with
    a number over 255 are usually a real address mistyped, so they go too. Private-network and loopback addresses
    are kept: they identify no one. Hostnames are kept: an operator chose to publish them.
    """
    def ip(m: re.Match) -> str:
        a = parse.dotted_quad(m.group(0))
        if a == "bad":
            return parse.BAD_IP_MARK
        return parse.IP_MARK if a.is_global else m.group(0)
    return EMAIL.sub(EMAIL_MARK, IPV4.sub(ip, page))


def pack(db: sqlite3.Connection, out: str) -> int:
    """Write every server page to a gzipped JSON-lines file, one page per line, in id order.

    phpBB puts a guest session id (sid=...) into the page's links; it differs on every fetch and means nothing,
    so it is blanked. Public IP addresses and email addresses are redacted (see redact). Nothing else in the page
    is changed. The output is byte-for-byte reproducible.
    """
    n = 0
    with open(out, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0, filename="") as f:
        for sid, fetched, h in db.execute("SELECT id, fetched_at, html_gz FROM pages WHERE found = 1 ORDER BY id"):
            page = re.sub(r"sid=[0-9a-f]{32}", "sid=", gzip.decompress(h).decode("utf-8", "replace"))
            line = {"id": sid, "url": BASE.format(sid), "fetched_at": fetched, "html": redact(page)}
            f.write((json.dumps(line, ensure_ascii=False) + "\n").encode("utf-8"))
            n += 1
    print(f"{n} server pages -> {out}")
    return 0


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch(sid: int) -> tuple[int, bytes, float | None]:
    """Return (status, body, retry_after_seconds)."""
    req = urllib.request.Request(BASE.format(sid), headers={"User-Agent": UA, "Accept-Encoding": "gzip"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read()
            if r.headers.get("Content-Encoding") == "gzip":
                body = gzip.decompress(body)
            return r.status, body, None
    except urllib.error.HTTPError as e:
        ra = e.headers.get("Retry-After")
        try:
            body = e.read()
            if e.headers.get("Content-Encoding") == "gzip":
                body = gzip.decompress(body)
        except Exception:
            body = b""
        return e.code, body, float(ra) if ra and ra.isdigit() else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(Path(__file__).resolve().parents[2] / "raw/dol-portal/pages.sqlite"))
    ap.add_argument("--start", type=int, default=1)
    ap.add_argument("--end", type=int, help="last id; default: stop after --stop-after misses past the last hit")
    ap.add_argument("--stop-after", type=int, default=300)
    ap.add_argument("--delay", type=float, default=10.0)
    ap.add_argument("--recheck", type=int, metavar="N", help="instead of crawling, re-fetch N random 'not found' ids")
    ap.add_argument("--pack", metavar="OUT", help="instead of crawling, write the saved server pages to OUT (.jsonl.gz)")
    ap.add_argument("--max-server-errors", type=int, default=3, help="stop after this many different ids fail (5xx twice) in a row")
    args = ap.parse_args()
    if args.delay < 1:
        sys.exit("--delay below 1 second is not polite")

    db = sqlite3.connect(args.db)
    db.executescript(SCHEMA)
    if args.pack:
        return pack(db, args.pack)
    if args.recheck:
        return recheck(db, args.recheck, args.delay)
    done = {r[0] for r in db.execute("SELECT id FROM pages WHERE status = 200")}
    last_hit = max((r[0] for r in db.execute("SELECT id FROM pages WHERE found = 1")), default=0)

    sid, misses, backoff = args.start, 0, 60.0
    failed_ids, last_error_id = 0, None
    while True:
        if args.end is not None and sid > args.end:
            break
        if args.end is None and sid > last_hit and misses >= args.stop_after:
            break
        if sid in done:
            found = db.execute("SELECT found FROM pages WHERE id = ?", (sid,)).fetchone()[0]
            misses = 0 if found else misses + 1
            sid += 1
            continue

        try:
            status, body, retry_after = fetch(sid)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            print(f"s={sid} network error: {e}; waiting {backoff:.0f}s", flush=True)
            time.sleep(backoff)
            backoff = min(backoff * 2, 3600)
            continue

        if status == 403:
            print(f"s={sid} 403: the site is refusing us. Stopping; not working around it.", flush=True)
            return 2
        if status == 429:
            wait = retry_after or backoff
            print(f"s={sid} 429; waiting {wait:.0f}s", flush=True)
            time.sleep(wait)
            backoff = min(backoff * 2, 3600)
            continue
        if status >= 500:
            # Some entries fail every time (a broken record), so a 5xx on one id is not proof the site is down.
            # Retry the same id once after a pause; if it fails again, record it and move on. Stop only when
            # several *different* ids fail in a row.
            if sid != last_error_id:
                last_error_id = sid
                wait = retry_after or backoff
                snippet = " ".join(re.sub(rb"<[^>]+>", b" ", body).decode("utf-8", "replace").split())[:300]
                print(f"s={sid} {status}; retrying once in {wait:.0f}s; Retry-After={retry_after}; body: {snippet!r}",
                      flush=True)
                time.sleep(wait)
                continue
            failed_ids += 1
            db.execute(
                "INSERT OR REPLACE INTO pages VALUES (?, ?, 0, ?, '', ?)", (sid, status, now(), gzip.compress(body))
            )
            db.commit()
            print(f"s={sid} {status} twice: recorded as broken, moving on", flush=True)
            if failed_ids >= args.max_server_errors:
                print(f"{failed_ids} different ids failed in a row. The site looks down; stopping. "
                      "Rerun later to resume (broken ids are retried).", flush=True)
                return 3
            sid += 1
            time.sleep(args.delay)
            continue
        backoff, failed_ids, last_error_id = 60.0, 0, None

        found = int(status == 200 and NOT_FOUND not in body)
        db.execute(
            "INSERT OR REPLACE INTO pages VALUES (?, ?, ?, ?, ?, ?)",
            (sid, status, found, now(), hashlib.sha256(body).hexdigest(), gzip.compress(body)),
        )
        db.commit()
        if found:
            last_hit, misses = sid, 0
        else:
            misses += 1
        print(f"s={sid} {status} {'found' if found else 'not found'}", flush=True)
        sid += 1
        time.sleep(args.delay)

    n = db.execute("SELECT count(*) FROM pages WHERE found = 1").fetchone()[0]
    print(f"done: {n} server pages saved; last found id {last_hit}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
