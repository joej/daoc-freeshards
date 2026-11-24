"""The checker must accept the real data and reject each kind of broken entry."""
import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import freeshards  # noqa: E402

GOOD = {
    "_file": "example.yaml", "id": "example", "name": "Example", "community": "fr",
    "runs": [{"start": "2005-03", "end": "2007", "start_sure": "exact", "end_sure": "bound"}],
    "sources": [{"url": "https://example.org/", "what": "the shard's own site"}],
}


def errors_for(**changes):
    s = copy.deepcopy(GOOD)
    s.update(changes)
    return freeshards.check([s], [])


def test_real_data_is_valid():
    shards, links = freeshards.load()
    assert shards, "no shard files found"
    assert freeshards.check(shards, links) == []


def test_good_example_passes():
    assert errors_for() == []


@pytest.mark.parametrize("changes, expected", [
    ({"sources": []}, "at least one source"),
    ({"sources": [{"url": "not a link", "what": "x"}]}, "url must be"),
    ({"sources": [{"url": "https://example.org/"}]}, "say what the source shows"),
    ({"runs": []}, "at least one run"),
    ({"runs": [{"start": "05/2005", "start_sure": "exact"}]}, "start must be"),
    ({"runs": [{"start": "2005-13", "start_sure": "exact"}]}, "start must be"),
    ({"runs": [{"start": "2008", "end": "2006", "start_sure": "exact", "end_sure": "exact"}]}, "ends before it starts"),
    ({"runs": [{"start": "2005", "start_sure": "maybe"}]}, "start_sure must be"),
    ({"runs": [{"start": "2005", "end": "2009", "start_sure": "exact", "end_sure": "exact"},
               {"start": "2007", "start_sure": "exact"}]}, "before the previous run ends"),
    ({"community": "klingon"}, "community must be"),
    ({"id": "Bad Id"}, "id must be"),
    ({"_file": "other.yaml"}, "file name must be"),
    ({"name": ""}, "name is missing"),
])
def test_broken_entries_are_caught(changes, expected):
    errs = errors_for(**changes)
    assert any(expected in e for e in errs), errs


def test_links_must_point_at_shards():
    errs = freeshards.check([copy.deepcopy(GOOD)], [
        {"from": "example", "to": "nowhere", "kind": "staff", "evidence": "x", "source": "https://example.org/"}])
    assert any("'nowhere' is not a shard id" in e for e in errs)


def test_link_needs_kind_source_and_evidence():
    errs = freeshards.check([copy.deepcopy(GOOD)], [{"from": "example", "to": "example", "kind": "guess"}])
    assert any("kind must be" in e for e in errs)
    assert any("source must be" in e for e in errs)
    assert any("evidence is missing" in e for e in errs)


def test_exports_are_up_to_date(tmp_path):
    shards, links = freeshards.load()
    freeshards.export(shards, links, tmp_path)
    for f in tmp_path.iterdir():
        committed = freeshards.EXPORTS / f.name
        assert committed.exists(), f"exports/{f.name} is missing: run python tools/freeshards.py export"
        assert committed.read_text(encoding="utf-8") == f.read_text(encoding="utf-8"), \
            f"exports/{f.name} is stale: run python tools/freeshards.py export"


@pytest.mark.parametrize("milestones, expected", [
    ("2017-01-06", "milestones must be a list"),
    ([{"date": "2017-01-06", "what": "launch", "source": 1, "url": "x"}], "allowed keys"),
    ([{"date": "6 Jan 2017", "what": "launch", "source": 1}], "date must be"),
    ([{"date": "2017-13-01", "what": "launch", "source": 1}], "date must be"),
    ([{"date": "2017-01-06", "source": 1}], "say what happened"),
    ([{"date": "2017-01-06", "what": "launch"}], "source must be"),
    ([{"date": "2017-01-06", "what": "launch", "source": 2}], "source must be"),
    ([{"date": "2017-01-06", "what": "launch", "source": True}], "source must be"),
    ([{"date": "2017-01-06", "what": "launch", "source": 1},
      {"date": "2016-05", "what": "open beta", "source": 1}], "date order"),
])
def test_bad_milestones_are_rejected(milestones, expected):
    errs = errors_for(milestones=milestones)
    assert any(expected in e for e in errs), errs


def test_good_milestones_pass():
    assert errors_for(milestones=[{"date": "2016-05", "what": "open beta", "source": 1},
                                  {"date": "2017-01-06", "what": "launch", "source": 1}]) == []


FIG = {"posted_utc": "2017-01-21T01:08Z", "observed_from": "2017-01-21T01:00Z", "observed_to": "2017-01-21T01:00Z",
       "observed_basis": "a local time in the post", "shard": "example", "kind": "online", "value": "2580",
       "qualifier": "stated", "what": "/who total", "who": "player",
       "source_url": "https://example.org/t=1", "source_label": "a forum, login required"}


def fig_errors(**changes):
    r = dict(FIG)
    r.update(changes)
    return freeshards.check_figures([r], {"example"}, "figures/test.csv")


def test_real_figures_are_valid():
    shards, _ = freeshards.load()
    ids = {s["id"] for s in shards}
    files = freeshards.load_figures()
    assert files, "no figures files found"
    for where, rows in files:
        assert freeshards.check_figures(rows, ids, where) == []


def test_good_figure_passes():
    assert fig_errors() == []


@pytest.mark.parametrize("changes, expected", [
    ({"posted_utc": "21 Jan 2017"}, "posted_utc must be"),
    ({"observed_to": "2017-01-22T00:00Z", "observed_from": ""}, "after the post"),
    ({"observed_from": "2017-01-21T01:05Z", "observed_to": "2017-01-21T01:00Z"}, "observed_from is after"),
    ({"observed_basis": ""}, "observed_basis"),
    ({"shard": "nowhere"}, "not a shard id"),
    ({"kind": "guess"}, "kind must be"),
    ({"value": "~3000"}, "whole number"),
    ({"qualifier": "maybe"}, "qualifier must be"),
    ({"who": "anonymous"}, "who must be"),
    ({"what": ""}, "say what the post says"),
    ({"source_url": "uthgard forum"}, "source_url must be"),
    ({"source_label": ""}, "source_url must be"),
])
def test_broken_figures_are_caught(changes, expected):
    errs = fig_errors(**changes)
    assert any(expected in e for e in errs), errs


def test_figures_columns_are_checked():
    r = dict(FIG)
    del r["who"]
    assert "columns must be" in freeshards.check_figures([r], {"example"}, "f")[0]
