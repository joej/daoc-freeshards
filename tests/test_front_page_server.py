import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "dol_portal"))
import front_page_server as F  # noqa: E402

PAGE = ("<a style='x' href='server.php?s=7'>Other</a><br /><span>x</span></td><td style='y'>5</td></tr>"
        "<a style='x' href='server.php?s=11'>Uthgard [Open Beta]</a><br /><span>DAoC Classic</span></td>"
        "<td style='z'>1082</td></tr>"
        "<p style='font-size:1.6em;'>Record number of clients have connected (9)</p><p><a href='server.php?s=7'>Other"
        "</a><br /><span style='color:grey;'>1 day ago ago</p>"
        "<p style='font-size:1.6em;'>Record number of clients have connected (4160)</p><p><a href='server.php?s=11'>"
        "Uthgard</a><br /><span style='color:grey;'>8 hours ago ago</p>")


def test_parse_picks_the_right_server():
    assert F.parse(PAGE, "11") == ("Uthgard [Open Beta]", 1082, 4160, "8 hours ago ago")
    assert F.parse(PAGE, "7") == ("Other", 5, 9, "1 day ago ago")
    assert F.parse(PAGE, "99") == (None, None, None, None)


def test_committed_csv_is_well_formed():
    rows = list(csv.DictReader(open(ROOT / "data/dol-portal/uthgard-2-front-pages.csv")))
    assert rows and [r["captured_utc"] for r in rows] == sorted(r["captured_utc"] for r in rows)
    for r in rows:
        assert r["archive_url"].startswith("https://web.archive.org/web/" + r["captured_utc"][:4])
        assert (r["listed"] == "yes") == bool(r["server"])
        assert r["players_online"] == "" or int(r["players_online"]) >= 0
