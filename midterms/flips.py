"""Seat-by-seat flips and the partisan lean of flipped seats (1952 onward).

A seat "flips against the president's party" when the president's party held
it on Election Day (vacancies attributed to the last holder) and a different
party holds it at the opening of the new Congress.

Lean of a flipped seat = the president's party's two-party margin, in points,
in the most recent presidential election in that district (House) or state
(Senate). Positive = territory the president's own party had carried.
Cook PVI is used instead when supplied in data/manual/cook_pvi.csv (Cook's
data are licensed and were not downloadable here); otherwise the raw margin.
A PVI-style value (pres-party two-party share minus the national share) is
reported alongside for every seat.
"""
from __future__ import annotations

import re
from collections import Counter
from functools import lru_cache

import pandas as pd

from . import MANUAL
from . import legislators as leg
from .fetch import fetch
from .sources import CERVAS

# Jacobson/Cervas files number states alphabetically by full name, which
# differs from postal-code order; this is the full-name order.
_FULL_ORDER = ("AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE "
               "NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY").split()
STATE_NUM = {s: i + 1 for i, s in enumerate(_FULL_ORDER)}


def other_party(p: str) -> str:
    return "Republican" if p == "Democrat" else "Democrat"


# ------------------------------------------------------------ presidential ---
@lru_cache(maxsize=1)
def pres_national() -> pd.DataFrame:
    df = pd.read_csv(fetch(CERVAS["pres_national"], dataset="pres_national",
                           source="national presidential vote (jcervas mirror)"))
    df["p"] = df.party.str.extract(r"^(Democratic|Republican)$")[0]
    piv = df.dropna(subset=["p"]).pivot_table(index="year", columns="p", values="pop_votes", aggfunc="sum")
    piv["dem2"] = 100 * piv.Democratic / (piv.Democratic + piv.Republican)
    return piv[["dem2"]].reset_index()


@lru_cache(maxsize=1)
def pres_states() -> pd.DataFrame:
    df = pd.read_csv(fetch(CERVAS["pres_states"], dataset="pres_states",
                           source="state presidential results 1864-2024 (jcervas mirror)"))
    df = df.rename(columns={"state_abbrev": "state"})
    df["dem2"] = 100 * df.democrat / (df.democrat + df.republican)
    return df[["year", "state", "dem2"]]


@lru_cache(maxsize=1)
def house_dpres() -> pd.DataFrame:
    df = pd.read_csv(fetch(CERVAS["house_races_dpres"], dataset="house_district_pres",
                           source="Jacobson 1946-2014 + Clerk/Downballot 2016-2024 (jcervas mirror)"))
    return df[["year", "stcd", "dpres", "source"]].rename(columns={"source": "dpres_source"})


@lru_cache(maxsize=1)
def cook_pvi() -> pd.DataFrame | None:
    path = MANUAL / "cook_pvi.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path)

    def parse(v):  # "R+5" -> +5 toward R; "D+3" -> -3; "EVEN" -> 0
        v = str(v).strip().upper()
        if v in ("EVEN", "E", "0"):
            return 0.0
        m = re.match(r"([RD])\s*\+\s*([\d.]+)", v)
        return (1 if m.group(1) == "R" else -1) * float(m.group(2)) if m else float("nan")
    df["pvi_r"] = df.pvi.map(parse)
    return df


def _margin_for(dem2: float, party: str) -> float:
    """Two-party margin for `party` in points given the Dem two-party share."""
    return (2 * dem2 - 100) if party == "Democrat" else (100 - 2 * dem2)


# ------------------------------------------------------------------ flips ---
def seat_changes(y: int, chamber: str, pres_party: str) -> pd.DataFrame:
    """Every seat whose party changed, with lean. Count-based per seat key so
    multi-member at-large delegations are handled."""
    before = leg.seat_holders(y, chamber, "election_day")
    after = leg.seat_holders(y, chamber, "new_congress")
    rows = []
    keys = set(zip(before.state, before.seat)) | set(zip(after.state, after.seat))
    bgrp = before.groupby(["state", "seat"])
    agrp = after.groupby(["state", "seat"])
    for key in sorted(keys):
        b = Counter(bgrp.get_group(key).party) if key in bgrp.groups else Counter()
        a = Counter(agrp.get_group(key).party) if key in agrp.groups else Counter()
        matched = bool(b) and bool(a)
        lost = max(0, b[pres_party] - a[pres_party])
        gained = max(0, a[pres_party] - b[pres_party])
        if not (lost or gained):
            continue
        winner = ";".join(sorted(set(agrp.get_group(key).party))) if key in agrp.groups else ""
        loser = ";".join(sorted(set(bgrp.get_group(key).name))) if key in bgrp.groups else ""
        rows.append(dict(election_year=y, chamber=chamber, state=key[0], seat=key[1],
                         matched=matched, lost=lost if matched else 0, gained=gained if matched else 0,
                         unmatched_lost=0 if matched else lost, unmatched_gained=0 if matched else gained,
                         new_holder_party=winner, prior_holders=loser))
    n_seats = after.groupby("state").size()
    for r in rows:
        r["state_seats"] = int(n_seats.get(r["state"], 0))
    df = pd.DataFrame(rows, columns=["state_seats", "election_year", "chamber", "state", "seat", "matched", "lost",
                                     "gained", "unmatched_lost", "unmatched_gained",
                                     "new_holder_party", "prior_holders"])
    return attach_lean(df, y, chamber, pres_party)


def attach_lean(df: pd.DataFrame, y: int, chamber: str, pres_party: str,
                district_pres: pd.DataFrame | None = None) -> pd.DataFrame:
    df = df.copy()
    nat = pres_national().set_index("year").dem2.get(y - 2)
    if chamber == "house":
        dp = district_pres if district_pres is not None else house_dpres()
        dp = dp[dp.year == y].set_index("stcd").dpres
        stcd = df.state.map(STATE_NUM) * 100 + df.seat.where(df.seat > 0, 1)
        dem2 = stcd.map(dp)
        # an at-large seat in a state with several House seats (pre-1970
        # general-ticket members) has no single district result
        if "state_seats" in df:
            dem2 = dem2.where((df.seat > 0) | (df.state_seats == 1))
    else:
        ps = pres_states()
        ps = ps[ps.year == y - 2].set_index("state").dem2
        dem2 = df.state.map(ps)
    df["pres_dem2"] = dem2
    df["lean_margin"] = [_margin_for(v, pres_party) if pd.notna(v) else float("nan") for v in dem2]
    pres2 = (nat if pres_party == "Democrat" else 100 - nat) if nat is not None else float("nan")
    df["lean_pvi_style"] = [(v if pres_party == "Democrat" else 100 - v) - pres2 if pd.notna(v)
                            else float("nan") for v in dem2]
    df["lean_source"] = "raw presidential margin"
    cp = cook_pvi()
    if cp is not None:
        c = cp[(cp.chamber == chamber) & (cp.election_year == y)]
        cmap = {(r.state, int(r.district) if chamber == "house" else 0): r.pvi_r for r in c.itertuples()}
        for i, r in df.iterrows():
            k = (r.state, int(r.seat) if chamber == "house" else 0)
            if k in cmap and pd.notna(cmap[k]):
                pvi_toward_pres = cmap[k] if pres_party == "Republican" else -cmap[k]
                df.at[i, "lean_margin"] = pvi_toward_pres
                df.at[i, "lean_source"] = "Cook PVI"
    return df
