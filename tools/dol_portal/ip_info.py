#!/usr/bin/env python3
"""What the DOL portal pages' server addresses tell us, without publishing the addresses.

Reads the working database raw/dol-portal/pages.sqlite (written by crawl.py, not committed), because the
committed pages have public IP addresses redacted. Writes data/dol-portal/ip-info.csv, one row per server page
whose Connect address is a public IPv4 address, keyed by portal_id:

- one column per snapshot of the regional internet registries' "delegated" statistics files (ARIN, RIPE NCC,
  APNIC, LACNIC, AFRINIC): 2010, 2014 (the date of listing-2014-06-17.csv), 2018, 2022 and the current files.
  Each cell is the country the registries had the address delegated to on that day, or empty if it wasn't
  delegated. This is the country of the organisation the block was delegated to, not geolocation: a hosting
  company's block shows the hosting company's country. Addresses are traded, so parse.py takes the snapshot
  nearest the entry's last report to the portal.
- network: "home" or "hosting", from the address's reverse DNS name when this script runs, or empty when the
  name doesn't say. Only for entries that reported within two years of the fetch: older addresses have likely
  passed to someone else, so today's name says nothing about the server.

Filler addresses (1.1.1.1, 1.2.3.4, ...) get no row. Downloads 25 registry files (about 70 MB) into raw/rir/,
which is not committed; the reverse DNS lookups need the network too.

    python3 -I tools/dol_portal/ip_info.py
"""

import bisect
import bz2
import concurrent.futures
import csv
import gzip
import ipaddress
import re
import socket
import sqlite3
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import parse  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "raw/rir"
DB = ROOT / "raw/dol-portal/pages.sqlite"
OUT = ROOT / "data/dol-portal/ip-info.csv"
UA = "daoc-freeshards-archiver/0.1 (+https://github.com/joej/daoc-freeshards)"
RECENT_MONTHS = 24

# Reverse DNS names. Hosting is checked first: some hosting names also contain "static" or "client".
HOSTING = re.compile(r"your-server\.de|hetzner|ovh|kimsufi|contabo|online\.net|poneytelecom|scaleway|amazonaws|"
                     r"linode|digitalocean|vultr|leaseweb|ionos|1and1|strato|server|vps|dedi|cloud", re.I)
HOME = re.compile(r"dip0\.t-ipconnect|wanadoo|abo\.|proxad|comcast|hsd1|res\.spectrum|\brr\.com|fios|verizon|"
                  r"cox\.net|virginm|bredband|telia|dsl|cable|dyn|pool|ftth|cust|broadband|ziggo|telenet|kabel", re.I)


def snapshot(day: str) -> list[str]:
    y, d = day[:4], day.replace("-", "")
    arin = f"delegated-arin-{d}.gz" if y < "2013" else f"delegated-arin-extended-{d}.gz"
    return [f"https://ftp.arin.net/pub/stats/arin/archive/{y}/{arin}",
            f"https://ftp.ripe.net/pub/stats/ripencc/{y}/delegated-ripencc-{d}.bz2",
            f"https://ftp.apnic.net/stats/apnic/{y}/delegated-apnic-{d}.gz",
            f"https://ftp.lacnic.net/pub/stats/lacnic/archive/{y}/delegated-lacnic-{d}",
            f"https://ftp.afrinic.net/pub/stats/afrinic/{y}/delegated-afrinic-{d}"]


SNAPSHOTS = {day: snapshot(day) for day in ("2010-06-01", "2014-06-17", "2018-06-01", "2022-06-01")}
SNAPSHOTS["latest"] = [
    "https://ftp.arin.net/pub/stats/arin/delegated-arin-extended-latest",
    "https://ftp.ripe.net/pub/stats/ripencc/delegated-ripencc-extended-latest",
    "https://ftp.apnic.net/stats/apnic/delegated-apnic-extended-latest",
    "https://ftp.lacnic.net/pub/stats/lacnic/delegated-lacnic-extended-latest",
    "https://ftp.afrinic.net/pub/stats/afrinic/delegated-afrinic-extended-latest",
]


def fetch(url: str) -> Path:
    path = CACHE / url.rsplit("/", 1)[1]
    if not path.exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=120) as r:
            path.write_bytes(r.read())
        print(f"downloaded {path.name}", file=sys.stderr)
    return path


def lines(path: Path):
    data = path.read_bytes()
    if path.suffix == ".gz":
        data = gzip.decompress(data)
    elif path.suffix == ".bz2":
        data = bz2.decompress(data)
    return data.decode("utf-8", "replace").splitlines()


def table(urls):
    """Sorted (first, last, country) IPv4 ranges, and the newest data date of the files.

    File format: a version line "version|registry|serial|records|startdate|enddate|UTCoffset", summary lines
    "registry|*|type|*|count|summary", then records "registry|cc|type|start|value|date|status[|...]".
    """
    ranges, newest = [], ""
    for url in urls:
        for ln in lines(fetch(url)):
            if ln.startswith("#"):
                continue
            f = ln.split("|")
            if f[0][:1].isdigit():  # version line
                if len(f) >= 6 and f[5].isdigit() and len(f[5]) == 8:
                    newest = max(newest, f[5])
                continue
            if len(f) < 7 or f[2] != "ipv4" or f[1] in ("*", "") or f[6] not in ("allocated", "assigned"):
                continue
            first = int(ipaddress.IPv4Address(f[3]))
            ranges.append((first, first + int(f[4]) - 1, f[1].upper()))
    ranges.sort()
    return ranges, newest


def lookup(ranges, starts, ip: int) -> str:
    i = bisect.bisect_right(starts, ip) - 1
    if i >= 0 and ranges[i][0] <= ip <= ranges[i][1]:
        return ranges[i][2]
    return ""


def network(name: str) -> str:
    if not name:
        return ""
    if HOSTING.search(name):
        return "hosting"
    if HOME.search(name):
        return "home"
    return ""


def reverse_dns(ip: str) -> str:
    try:
        return socket.gethostbyaddr(ip)[0]
    except OSError:
        return ""


def pages():
    """(portal_id, public IPv4 host, reported recently) for each server page with one."""
    db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    for sid, fetched, h in db.execute("SELECT id, fetched_at, html_gz FROM pages WHERE found = 1 ORDER BY id"):
        page = gzip.decompress(h).decode("utf-8", "replace")
        host = parse.connect_address(page)[0].strip()
        ip = parse.dotted_quad(host)
        if parse.address_kind(host) != "public" or not isinstance(ip, ipaddress.IPv4Address):
            continue
        host = str(ip)  # "08.08.8.8" -> "8.8.8.8"
        if parse.placeholder(host):
            continue
        when = datetime.strptime(fetched, "%Y-%m-%dT%H:%M:%SZ")
        r = parse.parse(sid, page, when)
        recent = bool(r["last_update_to"]) and \
            parse.months(when.strftime("%Y-%m")) - parse.months(r["last_update_to"]) <= RECENT_MONTHS
        yield sid, host, recent


def main() -> int:
    tables = {}
    for name, urls in SNAPSHOTS.items():
        ranges, newest = table(urls)
        if name == "latest":
            name = f"{newest[:4]}-{newest[4:6]}-{newest[6:]}"
        tables[name] = (ranges, [r[0] for r in ranges])
    found = list(pages())
    socket.setdefaulttimeout(5)
    recent_hosts = sorted({host for _, host, recent in found if recent})
    with concurrent.futures.ThreadPoolExecutor(16) as ex:
        names = dict(zip(recent_hosts, ex.map(reverse_dns, recent_hosts)))
    rows = []
    for sid, host, recent in found:
        ip = int(ipaddress.IPv4Address(host))
        rows.append({"portal_id": sid, "network": network(names[host]) if recent else "",
                     **{day: lookup(rng, starts, ip) for day, (rng, starts) in tables.items()}})
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} server pages -> {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
