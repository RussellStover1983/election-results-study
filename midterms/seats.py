"""Chamber composition by party for every Congress elected 1892-2024.

House totals come from the House Historian's Party Divisions table (primary
source; falls back to a pinned mirror of that table, then to Wikipedia, then
to counting members in congress-legislators). Senate composition is counted
seat by seat from congress-legislators (which records Senate class and caucus
for independents); senate.gov and Wikipedia are tried first only as a
cross-check and recorded in the source log.

Two baselines are produced per chamber and year so the metrics can be
computed either way (see README, "Seat-count conventions"):
  prior_congress_start: seats at the opening of the previous Congress
  election_day:          seats held on Election Day (1946+ for the House)
"""
from __future__ import annotations

import re

import pandas as pd
from bs4 import BeautifulSoup

from . import legislators as leg
from .fetch import FetchError, first_working, log
from .sources import CERVAS, OFFICIAL

YEARS = range(1892, 2025, 2)


# ---------------------------------------------------------------- parsers ---
def _num(x) -> int | None:
    s = re.sub(r"\[.*?\]|\(.*?\)", "", str(x))
    s = re.sub(r"[^0-9]", "", s)
    return int(s) if s else None


def parse_clerk_html(path) -> pd.DataFrame:
    """history.house.gov Party Divisions table: header rows name the parties."""
    soup = BeautifulSoup(path.read_bytes(), "lxml")
    out, idx = [], None
    for tr in soup.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
        if not cells:
            continue
        if cells[0].lower().startswith("congress"):
            idx = {k: next((i for i, c in enumerate(cells) if c.lower().startswith(k)), None)
                   for k in ("democrat", "republican", "other")}
            continue
        m = re.match(r"^(\d+)\w*\s*\((\d{4})", cells[0])
        if not m or idx is None or idx["democrat"] is None or idx["republican"] is None:
            continue
        total = _num(cells[1])
        if total and total > 999:  # footnote digits glued to the number
            total = int(str(total)[:3])
        d, r = _num(cells[idx["democrat"]]), _num(cells[idx["republican"]])
        if None in (total, d, r):
            continue
        out.append(dict(congress=int(m.group(1)), election_year=int(m.group(2)) - 1,
                        total=total, dem=d, rep=r))
    df = pd.DataFrame(out)
    _sanity_house(df)
    return df


def parse_house_mirror(path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df = df.rename(columns={"seats": "total"})[["congress", "election_year", "total", "dem", "rep"]]
    _sanity_house(df)
    return df


def parse_wiki_house(path) -> pd.DataFrame:
    """Wikipedia 'Party divisions of United States Congresses' (best effort)."""
    tables = pd.read_html(path, flavor="lxml")
    for t in tables:
        cols = [" ".join(map(str, c)) if isinstance(c, tuple) else str(c) for c in t.columns]
        t.columns = cols
        cong = next((c for c in cols if c.lower().startswith("congress")), None)
        hd = [c for c in cols if "house" in c.lower() and "dem" in c.lower()]
        hr = [c for c in cols if "house" in c.lower() and "rep" in c.lower()]
        ht = [c for c in cols if "house" in c.lower() and "total" in c.lower()]
        if cong and hd and hr and ht:
            df = pd.DataFrame({"congress": t[cong].map(_num), "total": t[ht[0]].map(_num),
                               "dem": t[hd[0]].map(_num), "rep": t[hr[0]].map(_num)}).dropna()
            df = df.astype(int)
            df["election_year"] = 1786 + 2 * df.congress
            _sanity_house(df)
            return df
    raise ValueError("no House party-division table found")


def _sanity_house(df: pd.DataFrame) -> None:
    if df.empty:
        raise ValueError("empty table")
    chk = df.set_index("election_year")
    # anchors: chamber sizes the table must reproduce if it parsed correctly
    for y, n in {1894: 357, 1912: 435, 1958: 436, 1994: 435}.items():
        if y in chk.index and not (n - 2 <= chk.loc[y, "total"] <= n + 2):
            raise ValueError(f"total for {y} = {chk.loc[y, 'total']}, expected ~{n}")


def parse_senate_gov(path) -> pd.DataFrame:
    """senate.gov 'Party Division' page: one paragraph block per Congress."""
    text = BeautifulSoup(path.read_bytes(), "lxml").get_text("\n")
    rows = []
    for blk in re.split(r"\n(?=\d+(?:st|nd|rd|th) Congress)", text):
        m = re.match(r"(\d+)(?:st|nd|rd|th) Congress \((\d{4})", blk)
        if not m:
            continue
        seats = {p.lower(): int(n) for p, n in
                 re.findall(r"(Democrats?|Republicans?)[^\n(]*\((\d+) seats\)", blk)}
        tot = re.search(r"Total Seats:\s*(\d+)", blk)
        d = next((v for k, v in seats.items() if k.startswith("democrat")), None)
        r = next((v for k, v in seats.items() if k.startswith("republican")), None)
        if d is not None and r is not None and tot:
            rows.append(dict(congress=int(m.group(1)), election_year=int(m.group(2)) - 1,
                             dem=d, rep=r, total=int(tot.group(1))))
    if len(rows) < 30:
        raise ValueError(f"only {len(rows)} Congress blocks parsed")
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- builders ---
def house_table() -> pd.DataFrame:
    df, src, url = first_working("house_party_divisions", [
        ("House Historian, Party Divisions (official)", OFFICIAL["house_party_divisions"], parse_clerk_html),
        ("Wikipedia, Party divisions of U.S. Congresses", OFFICIAL["wiki_party_divisions"], parse_wiki_house),
        ("House Historian table via pinned mirror (jcervas/democracys-data)",
         CERVAS["house_party_divisions"], parse_house_mirror),
    ])
    df = df[df.election_year.isin(YEARS)].copy()
    df["source"] = src
    rows = []
    for r in df.itertuples():
        y = r.election_year
        dem, rep, other = r.dem, r.rep, r.total - r.dem - r.rep
        note = ""
        if y >= leg.HOUSE_RELIABLE_FROM:
            # the Historian lists independents under "Other"; move those who
            # caucused with a party (Sanders 1991-2007, Goode 2000-02, ...)
            h = leg.seat_holders(y, "house", "new_congress")
            ind = h[(h.party_raw == "Independent") & h.party.isin(["Democrat", "Republican"])]
            for p in ind.itertuples():
                if p.party == "Democrat":
                    dem += 1
                else:
                    rep += 1
                other -= 1
                note += f"{p.name} (I) counted as {p.party}; "
        rows.append(dict(election_year=y, chamber="house", total=r.total, dem=dem, rep=rep,
                         other=other, source=src, caucus_note=note.strip()))
    out = pd.DataFrame(rows)
    missing = sorted(set(YEARS) - set(out.election_year))
    if missing:
        raise FetchError(f"House party divisions missing years {missing}")
    return out


def senate_table() -> pd.DataFrame:
    official = None
    try:
        official, src, _ = first_working("senate_party_divisions", [
            ("Senate Historical Office, Party Division (official)",
             OFFICIAL["senate_party_divisions"], parse_senate_gov)])
    except FetchError:
        log("senate_party_divisions", "-", "-", "fallback",
            detail="official Senate page unavailable; counting seats in congress-legislators")
    rows = []
    for y in YEARS:
        c = leg.composition(y, "senate", "new_congress")
        total = 2 * _n_states(y)
        rows.append(dict(election_year=y, chamber="senate", total=total, dem=c["dem"], rep=c["rep"],
                         other=c["filled"] - c["dem"] - c["rep"], vacant=total - c["filled"],
                         source="congress-legislators (seat-level count, caucus-adjusted)",
                         caucus_note=""))
    out = pd.DataFrame(rows)
    if official is not None:
        chk = out.merge(official, on="election_year", suffixes=("", "_senategov"))
        bad = chk[(chk.dem != chk.dem_senategov) | (chk.rep != chk.rep_senategov)]
        for b in bad.itertuples():
            log("senate_party_divisions", "cross-check", OFFICIAL["senate_party_divisions"], "differs",
                detail=f"{b.election_year}: legislators D{b.dem}/R{b.rep} vs senate.gov "
                       f"D{b.dem_senategov}/R{b.rep_senategov}")
    return out


ADMISSIONS = ["1896-01-04", "1907-11-16", "1912-01-06", "1912-02-14", "1959-01-03", "1959-08-21"]  # UT OK NM AZ AK HI


def _n_states(y: int) -> int:
    """States in the Union at the opening of the Congress elected in y."""
    start = leg.congress_start(y).isoformat()
    return 44 + sum(a <= start for a in ADMISSIONS)


def election_day_table() -> pd.DataFrame:
    """Composition on Election Day (House 1946+, Senate all years)."""
    rows = []
    for y in YEARS:
        for ch in ("house", "senate"):
            if ch == "house" and y < leg.HOUSE_RELIABLE_FROM:
                continue
            c = leg.composition(y, ch, "election_day")
            rows.append(dict(election_year=y, chamber=ch, dem_eday=c["dem"], rep_eday=c["rep"],
                             other_eday=c["filled"] - c["dem"] - c["rep"], filled_eday=c["filled"]))
    return pd.DataFrame(rows)


def build() -> pd.DataFrame:
    """Long table: one row per (election_year, chamber) with both baselines."""
    comp = pd.concat([house_table(), senate_table()], ignore_index=True)
    return comp.merge(election_day_table(), on=["election_year", "chamber"], how="left")
