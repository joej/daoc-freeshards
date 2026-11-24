"""Load, check and export the DAoC freeshard data.

    python tools/freeshards.py check     # validate data/ (CI runs this)
    python tools/freeshards.py export    # write exports/ from data/

Needs PyYAML (pip install pyyaml).
"""
import csv
import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
EXPORTS = ROOT / "exports"

COMMUNITIES = {"en": "English and international", "fr": "French", "de": "German", "other": "Other languages"}
SURE = {"exact", "bound", "approx"}
LINK_KINDS = {"rename", "staff", "code"}
DATE = re.compile(r"^(19|20)\d\d(-(0[1-9]|1[0-2]))?$")
ID = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
URL = re.compile(r"^https?://\S+$")
DAY = re.compile(r"^(19|20)\d\d-(0[1-9]|1[0-2])(-(0[1-9]|[12]\d|3[01]))?$")

# Optional `tech:` block: what a shard runs and changed. Each entry is {value, how, source?, basis?}.
#   how: stated  (the shard said so; needs `source`)
#        checked (we verified it, e.g. in the shard's files or a listing; needs `source`)
#        inferred (worked out from other facts; needs `basis`)
#   source: the 1-based number of an entry in this shard's `sources`, or a list of them.
HOW = {"stated", "checked", "inferred"}
TECH = {
    "server_base": {"dol", "dol-fork", "opendaoc", "opendaoc-fork", "own", "unknown"},
    "customisation": {"vanilla", "light", "heavy"},
    "pathing": {"in-process", "separate", "none", "unknown"},
    "database": None, "hosting": None, "client": None,
    "client_side": None, "custom_content": None, "launcher": None, "patcher": None,
}


def month(d, end=False):
    """'2014' or '2014-05' -> months since year 0, for ordering. 'now' sorts last."""
    if d == "now":
        return 10**9
    y, *m = d.split("-")
    return int(y) * 12 + (int(m[0]) if m else (12 if end else 1))


def load(data=DATA):
    shards = []
    for path in sorted((data / "shards").glob("*.yaml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        doc["_file"] = path.name
        shards.append(doc)
    links = (yaml.safe_load((data / "links.yaml").read_text(encoding="utf-8")) or {}).get("links", [])
    return shards, links


def check(shards, links):
    """Return a list of problems; empty means the data is valid."""
    errors = []
    ids = set()
    for s in shards:
        where = s.get("_file", "?")
        sid = s.get("id")
        if not isinstance(sid, str) or not ID.match(sid):
            errors.append(f"{where}: id must be lowercase words joined by hyphens")
            continue
        if where != f"{sid}.yaml":
            errors.append(f"{where}: file name must be {sid}.yaml")
        if sid in ids:
            errors.append(f"{where}: duplicate id {sid}")
        ids.add(sid)
        if not s.get("name"):
            errors.append(f"{where}: name is missing")
        if s.get("community") not in COMMUNITIES:
            errors.append(f"{where}: community must be one of {', '.join(COMMUNITIES)}")
        runs = s.get("runs") or []
        if not runs:
            errors.append(f"{where}: at least one run is needed")
        prev_end = None
        for i, r in enumerate(runs, 1):
            start, end = r.get("start"), r.get("end")
            if not isinstance(start, str) or not DATE.match(start):
                errors.append(f"{where}: run {i}: start must be YYYY or YYYY-MM, quoted")
                continue
            if end is not None and end != "now" and (not isinstance(end, str) or not DATE.match(end)):
                errors.append(f"{where}: run {i}: end must be YYYY, YYYY-MM, \"now\" or left out")
                continue
            if r.get("start_sure") not in SURE:
                errors.append(f"{where}: run {i}: start_sure must be one of {', '.join(sorted(SURE))}")
            if end is not None and end != "now" and r.get("end_sure") not in SURE:
                errors.append(f"{where}: run {i}: end_sure must be one of {', '.join(sorted(SURE))}")
            if end is not None and month(end, True) < month(start):
                errors.append(f"{where}: run {i}: ends before it starts")
            if prev_end is not None and month(start) < prev_end:
                errors.append(f"{where}: run {i}: starts before the previous run ends")
            prev_end = month(end, True) if end else month(start)
        sources = s.get("sources") or []
        if not sources:
            errors.append(f"{where}: at least one source is needed")
        for j, src in enumerate(sources, 1):
            if not isinstance(src, dict) or not URL.match(str(src.get("url", ""))):
                errors.append(f"{where}: source {j}: url must be an http(s) link")
            elif not src.get("what"):
                errors.append(f"{where}: source {j}: say what the source shows in `what`")
        errors += check_tech(s, where, len(sources))
        errors += check_milestones(where, s.get("milestones"), len(sources))
    for k, lk in enumerate(links, 1):
        for end in ("from", "to"):
            if lk.get(end) not in ids:
                errors.append(f"links.yaml: link {k}: {end} {lk.get(end)!r} is not a shard id")
        if lk.get("kind") not in LINK_KINDS:
            errors.append(f"links.yaml: link {k}: kind must be one of {', '.join(sorted(LINK_KINDS))}")
        if not URL.match(str(lk.get("source", ""))):
            errors.append(f"links.yaml: link {k}: source must be an http(s) link")
        if not lk.get("evidence"):
            errors.append(f"links.yaml: link {k}: evidence is missing")
    return errors


def check_tech(s, where, n_sources):
    tech = s.get("tech")
    if tech is None:
        return []
    if not isinstance(tech, dict):
        return [f"{where}: tech must be a mapping of fields"]
    errors = []
    for field, entry in tech.items():
        w = f"{where}: tech.{field}"
        if field not in TECH:
            errors.append(f"{w}: unknown field (allowed: {', '.join(TECH)})")
            continue
        if not isinstance(entry, dict) or "value" not in entry:
            errors.append(f"{w}: needs `value` and `how`")
            continue
        value, allowed = entry["value"], TECH[field]
        values = value if isinstance(value, list) else [value]
        if not values or not all(isinstance(v, str) and v for v in values):
            errors.append(f"{w}: value must be text or a list of text")
        elif allowed is not None and (isinstance(value, list) or value not in allowed):
            errors.append(f"{w}: value must be one of {', '.join(sorted(allowed))}")
        how = entry.get("how")
        if how not in HOW:
            errors.append(f"{w}: how must be one of {', '.join(sorted(HOW))}")
        elif how in ("stated", "checked"):
            src = entry.get("source")
            srcs = src if isinstance(src, list) else [src]
            if not srcs or not all(isinstance(x, int) and 1 <= x <= n_sources for x in srcs):
                errors.append(f"{w}: how: {how} needs `source`, the number (or list of numbers) of entries in sources")
        elif not entry.get("basis"):
            errors.append(f"{w}: how: inferred needs `basis`, saying what it was worked out from")


def check_milestones(where, milestones, n_sources):
    """Optional dated events in a shard's life (open beta, launch, wipe...). Each needs a date, what happened, and
    `source`: the 1-based number of the entry in `sources` that states it."""
    if milestones is None:
        return []
    if not isinstance(milestones, list):
        return [f"{where}: milestones must be a list"]
    errors = []
    prev = ""
    for i, m in enumerate(milestones, 1):
        at = f"{where}: milestone {i}"
        if not isinstance(m, dict) or set(m) - {"date", "what", "source"}:
            errors.append(f"{at}: allowed keys are date, what, source")
            continue
        d = m.get("date")
        if not isinstance(d, str) or not DAY.match(d):
            errors.append(f"{at}: date must be \"YYYY-MM-DD\" or \"YYYY-MM\", in quotes")
            continue
        if not m.get("what") or not isinstance(m["what"], str):
            errors.append(f"{at}: say what happened in `what`")
        src = m.get("source")
        if isinstance(src, bool) or not isinstance(src, int) or not 1 <= src <= n_sources:
            errors.append(f"{at}: source must be the number (1 to {n_sources}) of the entry in sources that states it")
        if d < prev:
            errors.append(f"{at}: milestones must be in date order")
        prev = d
    return errors


def export(shards, links, out=EXPORTS):
    out.mkdir(exist_ok=True)
    clean = [{k: v for k, v in s.items() if not k.startswith("_")} for s in shards]
    (out / "freeshards.json").write_text(
        json.dumps({"shards": clean, "links": links}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    with open(out / "shards.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "name", "aka", "community", "first_start", "last_end", "runs", "note", "sources"])
        for s in clean:
            runs = s["runs"]
            w.writerow([s["id"], s["name"], "; ".join(s.get("aka") or []), s["community"], runs[0]["start"],
                        runs[-1].get("end", ""), len(runs), s.get("note", ""), len(s["sources"])])
    with open(out / "runs.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "run", "start", "start_sure", "end", "end_sure"])
        for s in clean:
            for i, r in enumerate(s["runs"], 1):
                w.writerow([s["id"], i, r["start"], r["start_sure"], r.get("end", ""), r.get("end_sure", "")])
    with open(out / "sources.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "url", "what"])
        for s in clean:
            for src in s["sources"]:
                w.writerow([s["id"], src["url"], src["what"]])
    with open(out / "tech.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "field", "value", "how", "source_url", "basis"])
        for s in clean:
            for field, e in (s.get("tech") or {}).items():
                v = e["value"]
                ns = e.get("source") or []
                src = " ".join(s["sources"][x - 1]["url"] for x in (ns if isinstance(ns, list) else [ns]))
                w.writerow([s["id"], field, "; ".join(v) if isinstance(v, list) else v, e["how"], src, e.get("basis", "")])
    with open(out / "milestones.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "date", "what", "source_url"])
        for s in clean:
            for m in s.get("milestones") or []:
                w.writerow([s["id"], m["date"], m["what"], s["sources"][m["source"] - 1]["url"]])
    with open(out / "links.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["from", "to", "kind", "evidence", "source"])
        for lk in links:
            w.writerow([lk["from"], lk["to"], lk["kind"], lk["evidence"], lk["source"]])


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "check"
    shards, links = load()
    errors = check(shards, links)
    for e in errors:
        print(e, file=sys.stderr)
    if errors:
        return 1
    if cmd == "export":
        export(shards, links)
        print(f"exported {len(shards)} shards and {len(links)} links to {EXPORTS.relative_to(ROOT)}/")
    else:
        print(f"ok: {len(shards)} shards, {len(links)} links")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
