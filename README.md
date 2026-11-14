# DAoC freeshards: dated, sourced, open

Dark Age of Camelot private servers ("freeshards") from 2004 to today, in English, French, German,
Russian, Spanish and Italian. Each shard has the dates we could prove, and every date has a source.
Fork it, fix it, add the shard you ran or played on.

The data is drawn as a timeline at [eveofdarkness.org/freeshards](https://eveofdarkness.org/freeshards/).

## What's here

| Path | What it is |
|---|---|
| `data/shards/<id>.yaml` | One file per shard: names, language community, runs (dates), a short note, sources |
| `data/links.yaml` | Documented connections between shards: renamed, same staff, same code |
| `data/leads.yaml` | Shards we know of but can't date well enough yet |
| `data/dol-portal/listing-2014-06-17.csv` | The Dawn of Light server portal's full listing on 17 June 2014: 899 servers |
| `data/dol-portal/front-pages.csv` | Servers online and their player counts on the portal's front page, 10 captures, 2011–2022 |
| `exports/` | The same data as `freeshards.json` and CSV tables (`shards`, `runs`, `sources`, `links`), generated |

## A shard file

```yaml
id: amtenael                 # file name without .yaml; lowercase, hyphens
name: Amtenaël
aka: [Amtenael, Amtenaël - Résurrection]
community: fr                # en (English and international), fr, de, other
runs:                        # one per period it was up; a shard that closed and came back has several
- start: "2004-08"           # "YYYY" or "YYYY-MM", in quotes
  end: "2012-01"             # same, or "now", or leave it out if unknown
  start_sure: exact          # exact: a source states it
  end_sure: exact            # bound: only first or last seen (an archive capture, a listing)
                             # approx: worked out from something like "2 months ago"
note: first French freeshard; reopened four times
sources:
- url: https://web.archive.org/web/2004.../http://www.amtenael.fr/
  what: earliest archived copy of the site
```

## Rules for evidence

- **Every run needs a source.** Archived pages (the Wayback Machine) are best: they don't change.
- **Say what the source shows** in `what`, in a few words.
- **Player counts are claims** unless something measured them. The DOL portal counted the players
  on servers that reported to it; a shard's own site or a toplist reports what the shard said.
- **A link needs evidence.** `rename`: the same portal entry or the same shard under a new name.
  `code`: one shard's code went into another. `staff`: the same people ran both.
- **First-hand accounts count.** If you ran or played on a shard, open an issue and say so; we'll
  cite the issue.

The timeline draws a bar thick when a shard has two or more sources and one of them was made at the
time by the shard itself or measured by the DOL portal, and thin otherwise.

## Contributing

1. Fork, then add or edit a file in `data/shards/` (or `data/links.yaml`).
2. Check and regenerate the exports:
   ```sh
   pip install pyyaml pytest
   python tools/freeshards.py check
   python tools/freeshards.py export
   pytest
   ```
3. Open a pull request. CI runs the same checks.

No sources yet? Open an issue with what you remember: the name, the language, rough years, a URL.

## Where the data comes from

- **The Dawn of Light server portal** (dolserver.net/daocportal), the registry most DOL-based
  shards listed on until it shut in 2022–23: its June 2014 listing, front pages from 2011 to 2022
  and server pages, read through the Wayback Machine.
- **Toplists:** XtremeTop100's DAoC category (from 2004), the French rpg-paradize and vtop100
  lists, and German lists from 2005.
- **Shards' own sites and forums,** first and last archived copies.
- **Phoenix's closing announcement** (2021) and other public posts cited per shard.

Not here: Mythic's and Broadsword's official servers.

## Licence

The data in `data/` and `exports/` is licensed [CC BY 4.0](data/LICENSE): use it for anything, and
credit "DAoC freeshards, eveofdarkness.org". The scripts and tests are [MIT](LICENSE).
