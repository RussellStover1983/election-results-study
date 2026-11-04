"""Seat-level holders of every House and Senate seat, from congress-legislators.

Two snapshots per election year y:

* "election_day": who held each seat on the morning of Election Day
  (includes special-election winners and party switches up to that date).
* "new_congress": who held each seat at the opening of the Congress elected in
  y, with the party they were elected under. Holdover senators keep the party
  they had on Election Day, so a post-election switch (Shelby, 9 Nov 1994) is
  not counted as an election result.

Known data limitation: before roughly the 1940s the dataset records House
terms at Congress granularity (a mid-Congress replacement gets the same start
date as the member replaced), so House snapshots from this module are used
only from 1946 on. Senate records carry per-seat class, which lets us pick one
holder per seat in every era.
"""
from __future__ import annotations

import datetime as dt
import pickle
from collections import defaultdict
from functools import lru_cache

import pandas as pd
import yaml

from . import CACHE
from .fetch import fetch
from .sources import LEGISLATORS, LEGISLATORS_SHA

STATES = set("AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN "
             "MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA "
             "WA WV WI WY".split())
HOUSE_RELIABLE_FROM = 1946


def election_day(y: int) -> dt.date:
    d = dt.date(y, 11, 2)  # first Tuesday after the first Monday
    while d.weekday() != 1:
        d += dt.timedelta(1)
    return d


def congress_start(y: int) -> dt.date:
    """Constitutional start of the Congress elected in November of y."""
    return dt.date(y + 1, 3, 4) if y + 1 < 1935 else dt.date(y + 1, 1, 3)


def congress_number(y: int) -> int:
    return (y - 1788) // 2 + 1 + 0  # 1788 elected the 1st; 1894 -> 54th


@lru_cache(maxsize=1)
def terms() -> pd.DataFrame:
    pkl = CACHE / "derived" / f"legislators_{LEGISLATORS_SHA[:10]}.pkl"
    if pkl.exists():
        return pickle.loads(pkl.read_bytes())
    loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
    rows = []
    for which, url in LEGISLATORS.items():
        path = fetch(url, dataset="legislators", source=f"congress-legislators {which}")
        for person in yaml.load(path.read_text(), Loader=loader):
            name = person.get("name", {})
            nm = name.get("official_full") or f"{name.get('first','')} {name.get('last','')}".strip()
            for t in person["terms"]:
                rows.append(dict(
                    bioguide=person["id"].get("bioguide"), name=nm, type=t["type"],
                    state=t["state"], district=t.get("district"), sclass=t.get("class"),
                    start=t["start"], end=t["end"], party=t.get("party"),
                    caucus=t.get("caucus"), how=t.get("how"),
                    affiliations=tuple((a["start"], a["end"], a["party"])
                                       for a in t.get("party_affiliations", [])),
                ))
    df = pd.DataFrame(rows)
    df = df[df.state.isin(STATES)].reset_index(drop=True)
    pkl.parent.mkdir(parents=True, exist_ok=True)
    pkl.write_bytes(pickle.dumps(df))
    return df


def _party_on(row, day: str) -> str:
    p = row.party
    for s, e, ap in row.affiliations:
        if s <= day < e:
            p = ap
    return p or "Unknown"


def caucus_party(row, raw: str) -> str:
    """Independents count toward the party they caucused with (when recorded)."""
    if raw == "Independent" and isinstance(row.caucus, str) and row.caucus:
        return row.caucus
    return raw


def seat_holders(y: int, chamber: str, when: str) -> pd.DataFrame:
    """One row per member holding a seat at the snapshot.

    Columns: state, seat (district number or Senate class), name, party_raw,
    party (caucus-adjusted), start, end.
    """
    t = terms()
    t = t[t.type == ("rep" if chamber == "house" else "sen")]
    eday = election_day(y)
    if when == "election_day":
        lo = hi = (eday - dt.timedelta(days=1)).isoformat()
        cand = t[(t.start <= lo) & (t.end > lo)]
    elif when == "new_congress":
        a = congress_start(y)
        # pre-1935 terms are dated from the first session (often December)
        b = a + dt.timedelta(days=300 if a.year < 1935 else 45)
        lo, hi = a.isoformat(), b.isoformat()
        cand = t[(t.start < hi) & (t.end > lo)]
    else:
        raise ValueError(when)
    seat_col = "district" if chamber == "house" else "sclass"
    groups = defaultdict(list)
    for row in cand.itertuples():
        groups[(row.state, row[cand.columns.get_loc(seat_col) + 1])].append(row)
    if when == "election_day":
        # a seat vacant on Election Day is attributed to the party of its last
        # holder in the current Congress (the usual "seats before" convention);
        # single-member seats only
        cur = congress_start(y - 2).isoformat()
        prior = t[(t.end <= lo) & (t.end > cur)].sort_values("end")
        for row in prior.itertuples():
            seat = row[prior.columns.get_loc(seat_col) + 1]
            if seat is None or pd.isna(seat) or (chamber == "house" and seat == 0):
                continue
            key = (row.state, seat)
            if key not in groups or groups[key][0].end <= lo:
                groups[key] = [row]  # latest-ending prior holder wins
    out = []
    eday_s = eday.isoformat()
    for (state, seat), rows in groups.items():
        rows.sort(key=lambda r: r.start)
        if chamber == "senate" or (seat not in (0, None) and not pd.isna(seat)):
            rows = rows[:1]  # single-member seat: earliest holder in the window
        else:
            # at-large seats can be multi-member; keep each person's first term
            # that starts at the earliest date in the window
            first = rows[0].start
            rows = [r for r in rows if r.start == first]
        for r in rows:
            if when == "new_congress" and r.start > eday_s:
                day = r.start  # newly elected: party at start of the new term
            else:
                day = min(eday_s, r.end)  # holdover/election day: party on Election Day
                day = max(day, r.start)
            raw = _party_on(r, day)
            out.append(dict(state=state, seat=0 if seat is None or pd.isna(seat) else int(seat),
                            name=r.name, party_raw=raw, party=caucus_party(r, raw),
                            start=r.start, end=r.end, bioguide=r.bioguide))
    return pd.DataFrame(out)


def composition(y: int, chamber: str, when: str) -> dict:
    h = seat_holders(y, chamber, when)
    d = int((h.party == "Democrat").sum())
    r = int((h.party == "Republican").sum())
    return dict(dem=d, rep=r, other=int(len(h) - d - r), filled=int(len(h)))
