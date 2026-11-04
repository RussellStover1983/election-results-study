"""Check computed seat changes against known figures before trusting anything."""
from __future__ import annotations

import pandas as pd

from . import CONFIG
from .metrics import BASELINES, seats_before_after


def run(seats: pd.DataFrame) -> pd.DataFrame:
    exp = pd.read_csv(CONFIG / "validation.csv")
    rows = []
    for e in exp.itertuples():
        key = "dem" if e.party == "Democrat" else "rep"
        for b in BASELINES:
            before, after, used = seats_before_after(seats, e.election_year, e.chamber, b)
            got = after[key] - before[key]
            rows.append(dict(election_year=e.election_year, chamber=e.chamber, party=e.party,
                             baseline=b, baseline_used=used, seats_before=before[key], seats_after=after[key],
                             computed=got, expected=e.expected_change, ok=got == e.expected_change))
    return pd.DataFrame(rows)
