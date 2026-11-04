"""2026 race calls from the Associated Press, stored as timestamped snapshots.

Order of sources on each run with --refresh-2026:
  1. AP Elections API v3, if AP_API_KEY is set in the environment.
  2. AP's public results pages (best effort: looks for the race/candidate JSON
     those pages embed; AP may change this without notice).
Each successful pull is written to data/2026/snapshots/calls_<UTC>.csv and
never overwritten. Analysis reads the newest snapshot, then applies
data/2026/manual_calls.csv on top (rows there win, and are logged as manual
overrides). Races with no call are treated as uncalled, and every 2026 metric
is then labeled preliminary.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re

import pandas as pd

from . import DIR_2026
from . import legislators as leg
from .fetch import FetchError, fetch, log
from .sources import AP_API, AP_RESULTS_PAGES

SNAP_DIR = DIR_2026 / "snapshots"
MANUAL_CALLS = DIR_2026 / "manual_calls.csv"
CALL_COLS = ["chamber", "state", "seat", "winner_party", "called", "called_at_utc", "source", "note"]
AP_PARTY = {"Dem": "Democrat", "GOP": "Republican", "Rep": "Republican"}


# --------------------------------------------------------------- the field ---
def races_up() -> pd.DataFrame:
    """Every seat on the 2026 ballot, with the party holding it on Election Day."""
    y = 2026
    h = leg.seat_holders(y, "house", "election_day").assign(chamber="house")
    s = leg.seat_holders(y, "senate", "election_day").assign(chamber="senate")
    up_by = leg.congress_start(y).isoformat()
    s = s[s.end <= up_by]  # class II terms end 2027-01-03; appointees' terms end at the special
    s = s.assign(special=s.seat != 2)
    h = h.assign(special=False)
    cols = ["chamber", "state", "seat", "special", "party", "name"]
    return pd.concat([h[cols], s[cols]], ignore_index=True).rename(
        columns={"party": "incumbent_party", "name": "incumbent"})


def write_template() -> None:
    DIR_2026.mkdir(parents=True, exist_ok=True)
    t = races_up().assign(winner_party="", called="", called_at_utc="", source="", note="")
    t.to_csv(DIR_2026 / "manual_calls_TEMPLATE.csv", index=False)


# ------------------------------------------------------------------ AP API ---
def _parse_ap_races(payload: dict, src: str) -> pd.DataFrame:
    rows = []
    for race in payload.get("races", []):
        office = race.get("officeID")
        if office not in ("H", "S"):
            continue
        ru = (race.get("reportingUnits") or [{}])[0]
        state = race.get("statePostal") or ru.get("statePostal")
        winner = next((c for c in ru.get("candidates", []) if c.get("winner") == "X"), None)
        runoff = any(c.get("winner") == "R" for c in ru.get("candidates", []))
        seat = int(race["seatNum"]) if office == "H" and str(race.get("seatNum", "")).isdigit() else 0
        if office == "H" and seat == 0:
            seat = 0  # at-large
        rows.append(dict(
            chamber="house" if office == "H" else "senate", state=state, seat=seat,
            special="special" in str(race.get("raceType", "")).lower(),
            winner_party=AP_PARTY.get(winner.get("party"), "Other") if winner else "",
            called=bool(winner), called_at_utc=ru.get("lastUpdated", ""),
            source=src, note="runoff" if runoff else ""))
    return pd.DataFrame(rows)


def pull_ap_api(key: str) -> pd.DataFrame:
    path = fetch(AP_API, dataset="ap_2026", source="AP Elections API v3", refresh=True,
                 params={"officeID": "H,S", "level": "state", "format": "json", "resultsType": "l"},
                 secret_params={"apiKey": key})
    return _parse_ap_races(json.loads(path.read_text()), "AP Elections API")


def _walk(obj):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v)


def scrape_ap_pages() -> pd.DataFrame:
    frames = []
    for office, url in AP_RESULTS_PAGES.items():
        html = fetch(url, dataset="ap_2026", source=f"AP results page ({office})", refresh=True).read_text()
        blobs = re.findall(r"<script[^>]*type=\"application/json\"[^>]*>(.*?)</script>", html, re.S)
        races = []
        for b in blobs:
            try:
                races += [d for d in _walk(json.loads(b)) if "officeID" in d and "reportingUnits" in d]
            except json.JSONDecodeError:
                continue
        if not races:
            raise FetchError(f"no race JSON found on {url}")
        frames.append(_parse_ap_races({"races": races}, "AP results page (scraped)"))
    return pd.concat(frames, ignore_index=True)


def refresh() -> str:
    """Pull new calls and save a snapshot. Returns a one-line status."""
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    key = os.environ.get("AP_API_KEY")
    try:
        df = pull_ap_api(key) if key else scrape_ap_pages()
    except Exception as exc:  # noqa: BLE001
        log("ap_2026", "AP", "-", "failed", detail=str(exc))
        return f"AP pull failed ({'API' if key else 'page scrape'}): {exc}"
    if df.empty:
        return "AP pull returned no House/Senate races"
    ts = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    df["snapshot_utc"] = ts
    out = SNAP_DIR / f"calls_{ts}.csv"
    df.to_csv(out, index=False)
    return f"saved {out.name}: {int(df.called.sum())} of {len(df)} races called"


# ---------------------------------------------------------------- read back ---
def current_calls() -> tuple[pd.DataFrame, dict]:
    """Every race up in 2026 with its call (if any) and where the call came from."""
    field = races_up()
    snaps = sorted(SNAP_DIR.glob("calls_*.csv"))
    calls = pd.read_csv(snaps[-1]) if snaps else pd.DataFrame(columns=CALL_COLS + ["special"])
    status = {"snapshot": snaps[-1].name if snaps else None, "manual_rows": 0}
    if MANUAL_CALLS.exists():
        man = pd.read_csv(MANUAL_CALLS, dtype=str).fillna("")
        man = man[man.winner_party.str.len() > 0]
        if len(man):
            man = man.assign(seat=man.seat.astype(int), called=True,
                             source=man.source.where(man.source != "", "manual"),
                             special=man.get("special", "False").astype(str).str.lower() == "true")
            for r in man.itertuples():
                log("ap_2026", "manual override", str(MANUAL_CALLS.name), "applied",
                    detail=f"{r.chamber} {r.state}-{r.seat}: {r.winner_party} ({r.source})")
            key = ["chamber", "state", "seat"]
            calls = pd.concat([calls[~calls.set_index(key).index.isin(man.set_index(key).index)],
                               man[[c for c in calls.columns if c in man.columns]]], ignore_index=True)
            status["manual_rows"] = len(man)
    calls = calls[calls.called.astype(str).str.lower().isin(["true", "1"])] if len(calls) else calls
    if len(calls):
        calls = calls.assign(seat=calls.seat.astype(int))
    merged = field.merge(calls[["chamber", "state", "seat", "winner_party", "called_at_utc", "source"]]
                         if len(calls) else pd.DataFrame(columns=["chamber", "state", "seat", "winner_party",
                                                                  "called_at_utc", "source"]),
                         on=["chamber", "state", "seat"], how="left")
    merged["called"] = merged.winner_party.notna() & (merged.winner_party.astype(str) != "")
    status["called"] = int(merged.called.sum())
    status["uncalled"] = int((~merged.called).sum())
    status["latest_call_utc"] = str(merged.called_at_utc.dropna().max()) if status["called"] else None
    return merged, status
