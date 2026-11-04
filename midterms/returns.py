"""District-level returns and the national two-party House vote.

* MEDSL U.S. House 1976-2022 and U.S. Senate 1976-20xx (Harvard Dataverse);
  the House file falls back to the verbatim TidyTuesday republication.
* Clerk of the House "Statistics of the Congressional Election" 2004-2024,
  parsed per district (via the pinned jcervas mirror). Preferred for 2004+
  because it is the official count and extends to 2024; MEDSL fills 1976-2002.
"""
from __future__ import annotations

import json
from functools import lru_cache

import pandas as pd

from .fetch import FetchError, fetch, first_working, log
from .sources import CERVAS, DATAVERSE, MEDSL, MEDSL_HOUSE_MIRROR

DEM_LABELS = {"DEMOCRAT", "DEMOCRATIC", "DEMOCRATIC-FARMER-LABOR", "DEMOCRATIC-FARM-LABOR",
              "DEMOCRATIC-NONPARTISAN LEAGUE", "DEMOCRATIC-NPL", "DFL"}
REP_LABELS = {"REPUBLICAN", "INDEPENDENT-REPUBLICAN"}


def _dataverse_file(kind: str) -> str:
    spec = MEDSL[kind]
    meta = fetch(f"{DATAVERSE}/datasets/:persistentId/", params={"persistentId": spec["doi"]},
                 dataset=f"medsl_{kind}", source="Harvard Dataverse (MEDSL) metadata")
    files = json.loads(meta.read_text())["data"]["latestVersion"]["files"]
    cands = [f["dataFile"] for f in files
             if spec["name_contains"] in f["dataFile"]["filename"] and kind in f["dataFile"]["filename"]]
    if not cands:
        raise FetchError(f"no {kind} returns file in {spec['doi']}")
    best = max(cands, key=lambda f: f["filename"])  # newest end-year sorts last
    return f"{DATAVERSE}/access/datafile/{best['id']}?format=original"


def _read_medsl(path) -> pd.DataFrame:
    df = pd.read_csv(path, low_memory=False, sep=None, engine="python") if str(path).endswith(".tab") \
        else pd.read_csv(path, low_memory=False)
    need = {"year", "state_po", "district", "stage", "party", "candidatevotes"}
    if not need <= set(df.columns):
        raise ValueError(f"unexpected MEDSL columns: {sorted(df.columns)[:12]}")
    return df


@lru_cache(maxsize=2)
def medsl(kind: str) -> pd.DataFrame | None:
    attempts = []
    try:
        attempts.append(("MIT Election Data + Science Lab (Harvard Dataverse)", _dataverse_file(kind), _read_medsl))
    except Exception as exc:  # noqa: BLE001
        log(f"medsl_{kind}", "Harvard Dataverse (MEDSL)", MEDSL[kind]["doi"], "unavailable", detail=str(exc))
    if kind == "house":
        attempts.append(("MEDSL 1976-2022 House, TidyTuesday republication (2023-11-07)",
                         MEDSL_HOUSE_MIRROR, _read_medsl))
    try:
        df, src, _ = first_working(f"medsl_{kind}", attempts)
    except FetchError:
        return None
    df.attrs["source"] = src
    return df


@lru_cache(maxsize=1)
def clerk_house() -> pd.DataFrame:
    return pd.read_csv(fetch(CERVAS["clerk_house_votes"], dataset="clerk_house_votes",
                             source="Clerk of the House election statistics 2004-2024 (jcervas mirror)"))


def national_house_vote() -> pd.DataFrame:
    """Dem and Rep national House vote by year (general elections)."""
    rows = []
    m = medsl("house")
    if m is not None:
        g = m[(m.stage.astype(str).str.upper() == "GEN")]
        if "special" in g:
            g = g[~g.special.astype(str).str.upper().isin(["TRUE", "1"])]
        if "writein" in g:
            g = g[~g.writein.astype(str).str.upper().isin(["TRUE", "1"])]
        party = g.party.astype(str).str.upper().str.strip()
        g = g.assign(p=party.map(lambda x: "dem" if x in DEM_LABELS else "rep" if x in REP_LABELS else None))
        s = g.dropna(subset=["p"]).groupby(["year", "p"]).candidatevotes.sum().unstack()
        for y, r in s.iterrows():
            rows.append(dict(year=int(y), dem_votes=int(r.dem), rep_votes=int(r.rep),
                             source=m.attrs.get("source", "MEDSL")))
    c = clerk_house().groupby("year")[["dem_votes", "rep_votes"]].sum()
    clerk_rows = {int(y): dict(year=int(y), dem_votes=int(r.dem_votes), rep_votes=int(r.rep_votes),
                               source="Clerk of the House election statistics")
                  for y, r in c.iterrows()}
    out = {r["year"]: r for r in rows}
    for y, r in clerk_rows.items():
        if y in out:  # cross-check, then prefer the official Clerk count
            a = 100 * out[y]["dem_votes"] / (out[y]["dem_votes"] + out[y]["rep_votes"])
            b = 100 * r["dem_votes"] / (r["dem_votes"] + r["rep_votes"])
            if abs(a - b) > 0.5:
                log("national_house_vote", "cross-check", "-", "differs",
                    detail=f"{y}: MEDSL D share {a:.2f} vs Clerk {b:.2f}")
        out[y] = r
    df = pd.DataFrame(sorted(out.values(), key=lambda r: r["year"]))
    df["dem2"] = 100 * df.dem_votes / (df.dem_votes + df.rep_votes)
    return df
