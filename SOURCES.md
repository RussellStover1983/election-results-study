# Source log and manual overrides

This file is the human-written log. `output/source_log.csv` is the
machine-written log for each run.

## Build session, 2026-11-04 (cloud container)

This environment's network policy denied the following hosts (proxy 403):
history.house.gov, www.senate.gov, en.wikipedia.org, electionlab.mit.edu,
dataverse.harvard.edu, apnews.com / api.ap.org, docs.google.com (Downballot
sheets), cookpolitical.com and gallup.com. raw.githubusercontent.com and pypi
were reachable. Because of this:

| Dataset | Source actually used | Notes |
|---|---|---|
| House party divisions 1892–2024 | House Historian table parsed to CSV in `jcervas/democracys-data@35dba1b`, `labs/03-elections/midterm-loss/data/derived/house_midterms.csv` | That repo's build script scrapes history.house.gov. The columns are Democrats, Republicans and total; other = total − D − R. The official-page parser in `midterms/seats.py` is **untested** because the page was blocked. |
| Senate party divisions | Seat-by-seat count from `unitedstates/congress-legislators@15530b7` (2026-10-24) | Matches the senate.gov figures I know for the modern era. Pre-1914 counts are approximate. The senate.gov parser is **untested**. |
| House returns 1976–2022 | TidyTuesday 2023-11-07 `house.csv` @f422450, a verbatim copy of MEDSL's file | Dataverse was blocked. |
| Senate returns | none | Dataverse was blocked. Not needed for any metric. |
| House vote 2004–2024 | Clerk statistics parsed in jcervas `house-competition/data/derived/clerk_house.csv` | |
| District presidential vote | jcervas `races.csv` (Jacobson 1946–2014, Clerk/Downballot 2016–2024) and `pres_by_cd.csv` (Downballot 2008–2024) | |
| State and national presidential vote | jcervas `historical-campaigns/data/derived/pres_states_1864_2024.csv`, `pres_national.csv` | |
| AP 2026 calls | none, so 0 of 470 races are called | The AP API and page-scrape code paths are **untested** against live AP output. |

## Manual overrides

- `config/overrides.csv`: none.
- `data/2026/manual_calls.csv`: none.
- Hardcoded tables: `config/presidents.csv` and `config/gallup_approval.csv`.
  The Gallup values were entered from memory and are not verified; see the
  README.
