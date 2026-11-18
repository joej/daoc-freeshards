import csv
import gzip
import io
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools" / "dol_portal"))

import crawl  # noqa: E402
import parse  # noqa: E402

RAW = ROOT / "raw/dol-portal/server-pages-2026-11-18.jsonl.gz"
CSV = ROOT / "data/dol-portal/server-pages-2026-11-18.csv"
INFO = ROOT / "data/dol-portal/ip-info.csv"
PUBLISHED = [RAW, CSV, INFO]


def public_ips(text: str) -> list[str]:
    """Every dotted quad that is a public or mistyped address, leading zeros included."""
    return [m.group(0) for m in re.finditer(r"(?<![\d.])\d{1,3}(?:\.\d{1,3}){3}(?![\d.])", text)
            if parse.dotted_quad(m.group(0)) == "bad" or parse.dotted_quad(m.group(0)).is_global]


def read(path: Path) -> str:
    return gzip.open(path, "rt", encoding="utf-8").read() if path.suffix == ".gz" else path.read_text("utf-8")


def test_published_files_carry_no_public_ips_or_emails():
    for path in PUBLISHED:
        body = read(path)
        assert not public_ips(body), (path.name, public_ips(body)[:5])
        assert not re.findall(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", body), path.name


def test_redact():
    page = ('<h1>X</h1><a href="daoc://8.8.8.8:10300">Connect</a> IP: <strong>8.8.8.8</strong> '
            'LAN 192.168.0.1, 08.08.8.8, 8.8.8.256, 10.0.0.01, mail me@example.org, play.example.org '
            'Server Description')
    out = crawl.redact(page)
    assert out == ('<h1>X</h1><a href="daoc://[ip-redacted]:10300">Connect</a> IP: <strong>[ip-redacted]</strong> '
                   'LAN 192.168.0.1, [ip-redacted], [bad-ip-redacted], 10.0.0.01, mail [email-redacted], '
                   'play.example.org Server Description')
    assert parse.connect_address(out) == ("[ip-redacted]", "10300")


def test_csv_rebuilds_from_raw_pages():
    """The committed CSV is exactly what parse.py makes from the committed pages: run it and commit if this fails."""
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=parse.FIELDS, lineterminator="\n")
    w.writeheader()
    w.writerows(parse.build(RAW))
    assert buf.getvalue() == CSV.read_text(encoding="utf-8")


def test_ago_range_rounds_down():
    fetched = datetime(2026, 11, 18)
    assert parse.ago_range("5 years ago", fetched) == ("2020-11", "2021-11")
    assert parse.ago_range("1 decade ago", fetched) == ("2006-11", "2016-11")
    assert parse.ago_range("an hour ago", fetched) == ("2026-11", "2026-11")
    assert parse.ago_range("Never", fetched) == ("", "")


def test_address_kinds():
    assert parse.address_kind("") == "none"
    assert parse.address_kind("192.168.0.1") == "private"
    assert parse.address_kind("127.0.0.1") == "loopback"
    assert parse.address_kind("play.example.org") == "hostname"
    assert parse.address_kind("8.8.8.8") == "public"
    assert parse.address_kind("[ip-redacted]") == "public"
    assert parse.address_kind("91.229.20.166 ") == "public"
    assert parse.address_kind("10.234.123.087") == "private"
    assert parse.address_kind("8.8.8.256") == "invalid"
    assert parse.address_kind("[bad-ip-redacted]") == "invalid"


def test_placeholders():
    for host in ("1.1.1.1", "55.55.55.55", "1.2.3.4", "123.123.123.123"):
        assert parse.placeholder(host), host
    assert not parse.placeholder("8.8.4.4")


def test_network_only_for_recent_reports():
    for r in csv.DictReader(CSV.open(encoding="utf-8")):
        if r["network"]:
            assert r["network"] in ("home", "hosting"), r["portal_id"]
            assert r["last_update_to"] >= "2024-11", r["portal_id"]


def test_country_only_for_servers_that_reported():
    rows = list(csv.DictReader(CSV.open(encoding="utf-8")))
    assert rows, "empty CSV"
    with_country = [r for r in rows if r["ip_country"]]
    assert with_country, "no countries at all: is ip-info.csv missing?"
    for r in with_country:
        assert r["last_update"] not in ("", "Never"), r["portal_id"]
        assert r["address_kind"] == "public", r["portal_id"]
        assert r["ip_country_from"], r["portal_id"]


def test_country_uses_the_snapshot_nearest_the_last_report():
    snaps = {"2010-06-01": "US", "2014-06-17": "US", "2018-06-01": "DE", "2022-06-01": "DE", "2026-11-18": "DE"}
    assert parse.country_for(snaps, "2010-01", "2011-01") == ("US", "2010-06-01")
    assert parse.country_for(snaps, "2025-11", "2026-11") == ("DE", "2026-11-18")
    # Not delegated on the nearest day: take the next nearest that has one.
    assert parse.country_for({**snaps, "2026-11-18": ""}, "2025-11", "2026-11") == ("DE", "2022-06-01")
