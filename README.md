# DAoC freeshards: dated, sourced, open

Dark Age of Camelot private servers ("freeshards") from 2004 to today, in English, French, German,
Russian, Spanish and Italian. Each shard has the dates we could prove, and every date has a source.
Fork it, fix it, add the shard you ran or played on.

The data is drawn as a timeline at [eveofdarkness.org/freeshards](https://eveofdarkness.org/freeshards/), built from
`exports/freeshards.json` and `data/dol-portal/`; the page says which commit it was built from.

## What's here

| Path | What it is |
|---|---|
| `data/shards/<id>.yaml` | One file per shard: names, language community, runs (dates), a short note, sources |
| `data/links.yaml` | Documented connections between shards: renamed, same staff, same code |
| `data/leads.yaml` | Shards we know of but can't date well enough yet |
| `data/dol-portal/listing-2014-06-17.csv` | The Dawn of Light server portal's full listing on 17 June 2014: 899 servers |
| `data/dol-portal/front-pages.csv` | Servers online and their player counts on the portal's front page, 10 captures, 2011–2022 |
| `data/dol-portal/uthgard-2-front-pages.csv` | Uthgard (portal server 11) on every front-page capture from 31 May 2016 to 25 May 2018: 38 captures, with the capture time in UTC, the name as shown ("Uthgard [Open Beta]" until launch), players online, and the newest "Record number of clients" news item for Uthgard with its age as the page shows it (the portal prints it as "… ago ago"). Built by `tools/dol_portal/front_page_server.py`; no captures exist between 21 Nov 2016 and 31 Jan 2017, or after 25 May 2018 until 2020 |
| `data/dol-portal/server-pages-2026-11-18.csv` | Every server page still on the live portal, read 17–18 Nov 2026: 1,018 servers |
| `data/dol-portal/ip-info.csv` | For each server page with a public address: its registered country in 2010, 2014, 2018, 2022 and now, and whether a recent one is a home or hosting connection |
| `raw/dol-portal/` | The portal's server pages as fetched, one per line (gzipped JSON), so the CSV can be checked and rebuilt |
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
3. Commit `exports/` with your change and open a pull request. CI runs the same checks and fails if `exports/`
   is out of date.

No sources yet? Open an issue with what you remember: the name, the language, rough years, a URL.

## Where the data comes from

- **The Dawn of Light server portal**, the registry most DOL-based shards listed on: its June 2014
  listing, front pages from 2011 to 2022 and server pages, read through the Wayback Machine at
  dolserver.net/daocportal. Those copies stop in 2022, but the portal didn't: dolserver.net now redirects to
  [dolserver.sourceforge.net/serverlisting](https://dolserver.sourceforge.net/serverlisting/), and servers
  still report to it, because the update address built into DOL and OpenDAoC
  (portal.dolserver.net/serverlist.php) redirects there too. All its server pages were read in November 2026;
  see below.
- **Toplists:** XtremeTop100's DAoC category (from 2004), the French rpg-paradize and vtop100
  lists, and German lists from 2005.
- **Shards' own sites and forums,** first and last archived copies.
- **Phoenix's closing announcement** (2021) and other public posts cited per shard.

Not here: Mythic's and Broadsword's official servers.

## The live DOL portal, November 2026

`tools/dol_portal/crawl.py` fetched every server page, `server.php?s=1` to `s=1205`, one request every 20 seconds
with a user agent that names this repository. 1,018 pages were found; the other IDs answer "Server not found!"
(fetching 50 of them again gave the same answer every time). 1205 is past the last entry.

`data/dol-portal/server-pages-2026-11-18.csv` has one row per page:

- **Dates are relative** on the portal ("5 years ago"). Each is kept as written, plus the range of months it
  allows, counted back from the fetch time (`*_from`, `*_to`). The portal rounds down, so "5 years ago" is 5 to
  just under 6 years, and "1 decade ago" anything from 10 to 20 years. For those, the 2014 listing dates better.
- **`last_update`** is the last time the server reported to the portal. "Never" means the entry was registered
  but no server ever reported: 565 of the 1,018.
- **`peak_players`** is shown only for some servers; **`record_max`** is the highest "Record number of clients"
  in the page's news. Both were measured by the portal.
- **`address`** is the Connect address on the page. Public IP addresses are redacted (`[ip-redacted]`, port
  kept): many servers ran from someone's home connection, and old addresses now belong to other people.
  Addresses with a number over 255, usually a real one mistyped, are redacted too (`[bad-ip-redacted]`,
  `address_kind` invalid). Hostnames, private-network addresses and filler ones are kept.
- **`ip_country`** is the country the internet registries (ARIN, RIPE NCC, APNIC, LACNIC, AFRINIC) had that
  address delegated to: the organisation's country, not where the machine or the players were. A hosting
  company's address shows the hosting company's country. Addresses change hands, so it is read from the registry
  snapshot (2010, 2014, 2018, 2022 or the current one; `ip_country_from`) nearest the server's last report. It is
  left empty for entries that never reported and for filler addresses such as 1.2.3.4.
- **`network`** is `home` or `hosting`, read from the address's reverse DNS name on 18 Nov 2026, for servers
  that reported in the last two years; empty when older or when the name doesn't say.
- **`managers`**, **`news`** and **`description`** are as posted on the portal by the servers' staff.

The pages in `raw/dol-portal/` are the portal's public pages, unchanged except for blanking a meaningless guest
session id (`sid=`) and redacting public IP addresses and email addresses. Their text belongs to the portal and to the server staff who wrote it; the licence below
covers our data, not their words. To rebuild the CSV from them (standard library only, no network):

```sh
python tools/dol_portal/parse.py
```

`tools/dol_portal/ip_info.py` rebuilds `ip-info.csv` from the unredacted pages, which are not published; it
downloads the registries' files (about 70 MB). A test fails if a public IP or email address reaches the
published files.

## Licence

The data in `data/` and `exports/` is licensed [CC BY 4.0](data/LICENSE): use it for anything, and
credit "DAoC freeshards, eveofdarkness.org". The scripts and tests are [MIT](LICENSE).
