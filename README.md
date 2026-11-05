# Midterm collapse study

This project ranks every U.S. midterm from 1894 through 2026 by how badly the
president's party did in Congress. It covers the House, the Senate, and both
chambers combined. You can add 2026 results as races are called and re-run.

```
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m midterms                      # validates first, stops on a mismatch
.venv/bin/python -m midterms --baseline prior_congress_start
.venv/bin/python -m midterms --refresh-2026       # pull new AP calls, then rebuild
```

## Outputs (`output/`)

| File | Contents |
|---|---|
| `midterms.csv` | One row per midterm with every metric. This is the tidy table. |
| `rankings/<metric>.csv`, `rankings.md` | One ranking per metric, most severe first. 2026 is in bold; ‡ marks it as preliminary. |
| `charts/*.png`, `charts/*.html` | Seat swing over time, share of exposed majority lost, and raw swing vs. lean-weighted flips. |
| `flipped_seats.csv` | Every seat that changed party, 1954+, with the lean value used for it. |
| `seats_by_congress.csv` | Party composition of each chamber for every Congress elected 1892–2024, under both baselines, with the source used for each row. |
| `national_house_vote.csv` | National Democratic and Republican House vote, 1976–2024. |
| `validation.csv` | Known figures compared with computed ones, under each baseline. |
| `source_log.csv` | Every download attempt in the last run: cache hit, download, blocked, parsed, cross-check difference, or manual override. |

## Metrics

All metrics are from the president's party's point of view. "Before" and
"after" are defined in **Seat-count conventions** below.

1. **Net seat swing** is seats after minus seats before. It is reported in
   seats and as a percent of chamber size. The chamber size comes from the
   Historian's total membership: 356 or 357 in the 1890s, 386, 391 or 394 in
   1902–1910, 435 from 1912, and 436 or 437 in 1958–60. Combined swing is
   House plus Senate. `combined_swing_pct` is weighted by seats, so the House
   dominates it. `combined_swing_pct_chamber_avg` weights the two chambers
   equally.
2. **Share of exposed majority lost.** The exposed majority is
   `seats_before − (control_threshold − 1)`, which is the number of seats the
   party could lose before losing control. The metric is seats lost divided by
   that number. A value of 1.0 or more means control was lost, unless third
   parties held the balance.
   - Threshold in the House: `floor(N/2)+1`.
   - Threshold in the Senate: `N/2`, because the Vice President, who is always
     of the president's party at a midterm, breaks ties.
   - The metric is blank when the president's party was already in the
     minority.
   - `*_control_flipped` compares which party held more seats before and after.
     A Senate tie goes to the Vice President's party.
   - **Senate share of seats on the ballot lost** (`senate_up_share_lost`):
     the president's party's Senate seats lost, divided by the number of its
     seats that were on the ballot (regular plus special elections). The party's
     exposure varies a lot between cycles, from 10 seats in 2018 to 32 in 1938,
     so this is a fairer Senate comparison than raw swing.
     `senate_opp_seats_up_won` records any offsetting gains. For a preliminary
     2026, `senate_up_share_lost_max` assumes the party also loses every
     uncalled seat it holds. Before 1914 the "ballot" was the state legislature.
   - **House share of held seats lost** (`house_held_share_lost`): House
     seats the president's party lost, divided by the seats it held going in.
     Every House seat is on the ballot, so the denominator is all the party's
     seats. From 1954 this uses gross seat-by-seat losses; earlier years use
     the net loss (`house_held_share_basis` says which).
3. **Partisan-lean-weighted flips (1954+; 1952 was not a midterm).** For each
   seat that flipped against the president's party, the lean is that party's
   two-party margin, in points, in the previous presidential election in that
   district or state.
   - The ranked metrics are `*_lean_sum` (total lean) and `*_lean_mean` (mean
     lean). A higher value means the party lost friendlier territory.
   - Cook PVI is not licensed for redistribution and could not be downloaded.
     If you put Cook values in `data/manual/cook_pvi.csv` (columns
     `chamber,election_year,state,district,pvi`, with pvi written like `R+5`),
     they replace the raw margin seat by seat. The `lean_source` column records
     which was used.
   - `*_lean_pvi_style_mean` is the district share minus the national share,
     which is Cook's idea computed from a single election.
   - **Senate flip droughts** (`senate_flip_years_since_seat_mean` and
     `_max`, `senate_flip_years_since_state_mean` and `_max`,
     `senate_flips_ending_30yr_state_drought`): for each Senate seat the
     president's party lost, how many years it had been since the winning
     party last held that seat, and since it last held either seat in the
     state. This measures how deep into hostile territory the losses went,
     which a single election's lean misses. For example, Kansas in 2026 was the
     first Democratic Senate win in the state in 87 years. Appointed senators
     count as holding a seat, and independents count toward their caucus.
     NaN means the winning party never held the seat in the data.
4. **National House vote swing** is the president's party's share of the
   two-party national House vote, compared with the prior presidential year and
   with the prior midterm. It is available from 1978 (vs. the presidential
   year) and 1980 (vs. the prior midterm) through 2022. The 2026 value is blank
   until vote totals exist.
5. **Term context.** `midterm_in_tenure` counts the midterms in this
   president's continuous tenure, so Trump's 2026 midterm counts as his first.
   `midterm_in_career` counts all of his midterms (2026 is his second).
   `party_wh_midterm` counts consecutive midterms with his party in the White
   House, which shows the "six-year itch". `approval_pct` comes from
   `config/gallup_approval.csv`.

## Seat-count conventions (read this before quoting a number)

"Seats before" can mean two things, and the commonly quoted figures mix them:

- `prior_congress_start`: the composition when the previous Congress opened.
  This is the House Historian's table as published.
- `election_day` (the default): who held each seat on Election Day. It includes
  special elections and party switches since the last general election. A
  vacant seat counts for its last holder's party. This is available from 1946
  for the House and for every year in the Senate. Before 1946 the House falls
  back to `prior_congress_start`.

"After" is always the new Congress as elected. A senator who switches party
after the election, such as Shelby on 9 Nov 1994, is not counted as an
election result.

Independents count toward the party they caucused with. This affects Sanders
(House 1991–2007, Senate since 2007), Jeffords, Lieberman, King, Goode, and
others. The 1920s–30s third parties (Progressive, Farmer-Labor, American
Labor) caucused only loosely and are counted as "other".

## Data sources

The official hosts were unreachable from the environment this was built in.
When an official source cannot be reached or parsed, the pipeline falls
through to the next source and records the source used for each row. See
`SOURCES.md` for details and `output/source_log.csv` for each run.

| Data | Tried in order |
|---|---|
| House seats by party | House Historian Party Divisions page → Wikipedia → pinned mirror of the Historian table (jcervas/democracys-data) |
| Senate seats by party | senate.gov Party Division page (used only as a cross-check) → seat-by-seat count from `unitedstates/congress-legislators` (pinned commit) |
| Seat holders and flips | `unitedstates/congress-legislators` |
| House district returns, 1976–2022 | MEDSL on Harvard Dataverse → TidyTuesday's verbatim republication |
| House vote, 2004–2024 | Clerk of the House election statistics, parsed per district (jcervas mirror) |
| Senate returns, 1976+ | MEDSL on Dataverse. Optional, used only as a cross-check. |
| Presidential vote by district | Jacobson's House file for 1946–2014 (reconstructed district presidential vote). The Downballot / Daily Kos Elections for 2016–2024 and for 2026 (2024 lines). |
| Presidential vote by state | State results 1864–2024 (jcervas mirror) |
| 2026 | AP Elections API (when `AP_API_KEY` is set) → AP results pages → `data/2026/manual_calls.csv` |

Every download is cached in `data/cache/`, which git ignores, and is never
fetched again. Only the 2026 AP pull refreshes. Set `MIDTERMS_OFFLINE=1` to
forbid network access entirely.

## Re-running as 2026 races are called

1. Set `AP_API_KEY`, or rely on scraping AP's results pages, and run
   `python -m midterms --refresh-2026`. Each successful pull is saved as
   `data/2026/snapshots/calls_<UTC timestamp>.csv` and is never overwritten.
   The analysis uses the newest snapshot.
2. To enter calls by hand, or to correct one, copy
   `data/2026/manual_calls_TEMPLATE.csv` to `data/2026/manual_calls.csv`. The
   template lists all 470 seats on the ballot: 435 House, 33 Class II Senate,
   and the OH and FL specials. Fill in `winner_party` (`Democrat`,
   `Republican`, or `Other`) and `source`. Manual rows override AP and are
   logged as overrides.
3. 2026 is labeled `preliminary` while any race is uncalled.
   `*_swing_min` and `*_swing_max` give the range still possible, and control
   is marked `(provisional)`. When nothing has been called, 2026 is listed as
   `pending` and not ranked.
4. For 2026, the House lean of flipped seats uses 2024 presidential results on
   the 2024 lines. It is left blank in states that redrew for 2026, which are
   listed in `config/redistricted_2026.csv`.

## Caveats

- **Senate before 1914.** Senators were chosen by state legislatures, so
  "midterm" Senate changes up to 1912 reflect legislative sessions that met
  over many months. Some seats sat vacant during deadlocks. Pre-1914 Senate
  counts come from congress-legislators, are less precise than later years,
  and were not checked against senate.gov.
- **Third parties, 1890s–1930s.** Populists, Silver Republicans, Progressives
  and Farmer-Laborites are counted as "other". In 1930 the House was so close
  that deaths before it convened gave Democrats control, but the as-elected
  count shows Republicans narrowly ahead.
- **Reconstructed district presidential data.** No government source reports
  presidential results by congressional district. Jacobson's file and The
  Downballot rebuilt them from precinct or county returns. Coverage is about
  half the districts in 1962 and 1966. Pre-1970 at-large members in states
  with several seats have no district result.
- **Redistricting years** (1962, 1972, 1982, 1992, 2002, 2022, and the 2006
  Georgia and 2004 Texas mid-decade maps) are matched by district number. A
  "flip" can therefore be a renumbering. Seats that existed only before or
  only after are counted in `*_flips_unmatched_lost` and left out of the lean
  sums.
- **Lean depends on the previous presidential landslide.** The 1958 and 1974
  totals are large because Eisenhower and Nixon carried nearly every district
  two years earlier. The PVI-style column adjusts for this.
- **Gallup approval values were typed in from memory** of Gallup's published
  midterm tables, because gallup.com was unreachable. Each row is marked
  `verified_against_source=no`. Check them before citing. The 2026 value is
  blank.
- **National House vote** includes uncontested races only where states report
  them, so states that print no votes for unopposed candidates, such as
  Florida, are undercounted. MEDSL and the Clerk agree within 0.5 points in
  every overlapping year (2004–2022).
