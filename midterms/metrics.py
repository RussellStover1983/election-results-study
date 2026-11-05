"""Per-midterm metrics for the president's party, per chamber and combined."""
from __future__ import annotations

import math

import pandas as pd

from . import CONFIG, FIRST_MIDTERM, LEAN_START
from . import flips as fl
from . import legislators as leg

CHAMBERS = ("house", "senate")
BASELINES = ("prior_congress_start", "election_day")


def presidents() -> pd.DataFrame:
    return pd.read_csv(CONFIG / "presidents.csv")


def gallup() -> pd.DataFrame:
    return pd.read_csv(CONFIG / "gallup_approval.csv")[["election_year", "approval_pct", "source"]] \
        .rename(columns={"source": "approval_source"})


def control_threshold(total: int, chamber: str, for_pres_party: bool) -> int:
    """Fewest seats that give a party control of the chamber.

    Senate: half the seats suffice for the president's party, because the Vice
    President (always of the president's party at a midterm) breaks ties."""
    if chamber == "senate" and for_pres_party:
        return total // 2
    return total // 2 + 1


def controller(dem: int, rep: int, total: int, chamber: str, pres_party: str) -> str:
    if chamber == "senate" and dem == rep and dem * 2 >= total - 2:
        return pres_party  # VP tie-break
    if dem > rep:
        return "Democrat"
    if rep > dem:
        return "Republican"
    return "tie"


def seats_before_after(seats: pd.DataFrame, y: int, chamber: str, baseline: str) -> tuple[dict, dict, str]:
    s = seats.set_index(["election_year", "chamber"])
    after = s.loc[(y, chamber)]
    used = baseline
    if baseline == "election_day" and not pd.isna(s.loc[(y, chamber)].get("dem_eday")):
        r = s.loc[(y, chamber)]
        before = dict(dem=int(r.dem_eday), rep=int(r.rep_eday), total=int(s.loc[(y - 2, chamber)].total))
    else:
        if baseline == "election_day":
            used = "prior_congress_start (no Election Day snapshot)"
        r = s.loc[(y - 2, chamber)]
        before = dict(dem=int(r.dem), rep=int(r.rep), total=int(r.total))
    return before, dict(dem=int(after.dem), rep=int(after.rep), total=int(after.total)), used


def chamber_metrics(before: dict, after: dict, chamber: str, P: str) -> dict:
    key = "dem" if P == "Democrat" else "rep"
    okey = "rep" if key == "dem" else "dem"
    swing = after[key] - before[key]
    thr = control_threshold(before["total"], chamber, True)
    held = before[key] >= thr
    exposed = before[key] - (thr - 1) if held else None  # seats it could lose before losing control
    lost = max(0, -swing)
    ctrl_b = controller(before["dem"], before["rep"], before["total"], chamber, P)
    ctrl_a = controller(after["dem"], after["rep"], after["total"], chamber, P)
    return {
        "seats_before": before[key], "seats_after": after[key],
        "opp_seats_before": before[okey], "opp_seats_after": after[okey],
        "chamber_size": after["total"],
        "swing": swing, "swing_pct": 100 * swing / after["total"],
        "held_majority": held, "exposed_majority": exposed,
        "exposed_share_lost": (lost / exposed) if held else math.nan,
        "control_before": ctrl_b, "control_after": ctrl_a, "control_flipped": ctrl_b != ctrl_a,
    }


def lean_metrics(changes: pd.DataFrame) -> dict:
    lost = changes[changes.lost > 0]
    have = lost.dropna(subset=["lean_margin"])
    return {
        "flips_against": int(lost.lost.sum()),
        "flips_toward": int(changes.gained.sum()),
        "flips_unmatched_lost": int(changes.unmatched_lost.sum()),
        "lean_flips_n": int(have.lost.sum()),
        "lean_sum": float((have.lean_margin * have.lost).sum()) if len(have) else
        (0.0 if lost.empty else math.nan),
        "lean_mean": float((have.lean_margin * have.lost).sum() / have.lost.sum()) if len(have) else math.nan,
        "lean_pvi_style_mean": float((have.lean_pvi_style * have.lost).sum() / have.lost.sum())
        if len(have) else math.nan,
        "lean_source": ";".join(sorted(set(have.lean_source))) if len(have) else "",
    }


def build(seats: pd.DataFrame, house_vote: pd.DataFrame, baseline: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (one row per midterm 1894-2022, all flipped seats)."""
    pres = presidents().set_index("election_year")
    hv = house_vote.set_index("year").dem2
    rows, all_changes = [], []
    for y in range(FIRST_MIDTERM, 2023, 4):
        P = pres.loc[y, "party"]
        row = {"election_year": y, "congress": leg.congress_number(y), "president": pres.loc[y, "president"],
               "pres_party": P, "status": "final", "baseline": baseline}
        for ch in CHAMBERS:
            before, after, used = seats_before_after(seats, y, ch, baseline)
            for k, v in chamber_metrics(before, after, ch, P).items():
                row[f"{ch}_{k}"] = v
            row[f"{ch}_baseline_used"] = used
            row[f"{ch}_seat_source"] = seats.set_index(["election_year", "chamber"]).loc[(y, ch), "source"]
            if y >= LEAN_START:
                ch_changes = fl.seat_changes(y, ch, P)
                all_changes.append(ch_changes.assign(pres_party=P))
                for k, v in lean_metrics(ch_changes).items():
                    row[f"{ch}_{k}"] = v
        row.update(senate_up_metrics(y, P))
        row.update(house_held_metrics(row))
        row.update(vote_metrics(hv, y, P))
        rows.append(row)
    df = combine(pd.DataFrame(rows))
    changes = pd.concat(all_changes, ignore_index=True) if all_changes else pd.DataFrame()
    return add_context(df), changes


def senate_up_metrics(y: int, P: str, lost: int | None = None, gained: int | None = None,
                      up: pd.DataFrame | None = None) -> dict:
    """Senate seats actually on the ballot, and the share of the president's
    party's seats on the ballot that it lost (a fairer Senate measure than raw
    swing, because a party's exposure varies from 10 to 30+ seats a cycle)."""
    if up is None:
        b = leg.seat_holders(y, "senate", "election_day")
        up = b[b.end <= leg.congress_start(y).isoformat()]
    if lost is None:
        ch = fl.seat_changes(y, "senate", P)
        lost, gained = int(ch.lost.sum()), int(ch.gained.sum())
    n = int((up.party == P).sum())
    return {"senate_pres_seats_up": n, "senate_opp_seats_up": int(len(up) - n),
            "senate_pres_seats_up_lost": lost, "senate_opp_seats_up_won": gained,
            "senate_up_share_lost": (lost / n) if n else math.nan}


def house_held_metrics(row: dict) -> dict:
    """Share of the House seats the president's party held that it lost.

    Every House seat is on the ballot, so the denominator is seats held going
    in. Gross seat-by-seat losses (1954+) are used where available; earlier
    years fall back to the net loss, flagged in house_held_share_basis."""
    held = row.get("house_seats_before")
    gross = row.get("house_flips_against")
    if gross is not None and not (isinstance(gross, float) and math.isnan(gross)):
        lost, basis = gross, "gross seats lost"
    else:
        lost, basis = max(0, -row["house_swing"]) if not math.isnan(row["house_swing"]) else math.nan, \
            "net seats lost"
    return {"house_held_share_lost": lost / held if held and not math.isnan(lost) else math.nan,
            "house_held_share_basis": basis}


def vote_metrics(hv: pd.Series, y: int, P: str) -> dict:
    def share(yr):
        if yr not in hv.index:
            return math.nan
        return hv[yr] if P == "Democrat" else 100 - hv[yr]
    s, sp, sm = share(y), share(y - 2), share(y - 4)
    return {"house_vote_share": s, "house_vote_share_prior_pres": sp, "house_vote_share_prior_midterm": sm,
            "house_vote_swing_vs_prior_pres": s - sp, "house_vote_swing_vs_prior_midterm": s - sm}


def combine(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["combined_swing"] = df.house_swing + df.senate_swing
    size = df.house_chamber_size + df.senate_chamber_size
    df["combined_swing_pct"] = 100 * df.combined_swing / size  # seat-weighted (House-dominated)
    df["combined_swing_pct_chamber_avg"] = (df.house_swing_pct + df.senate_swing_pct) / 2

    def comb_exposed(r):
        lost = exp = 0
        for ch in CHAMBERS:
            if r[f"{ch}_held_majority"]:
                lost += max(0, -r[f"{ch}_swing"])
                exp += r[f"{ch}_exposed_majority"]
        return lost / exp if exp else math.nan
    df["combined_exposed_share_lost"] = df.apply(comb_exposed, axis=1)
    df["combined_control_flipped"] = df.house_control_flipped | df.senate_control_flipped
    if "house_lean_sum" in df:
        df["combined_flips_against"] = df.house_flips_against + df.senate_flips_against
        df["combined_lean_sum"] = df.house_lean_sum.fillna(0) + df.senate_lean_sum.fillna(0)
        n = df.house_lean_flips_n.fillna(0) + df.senate_lean_flips_n.fillna(0)
        df["combined_lean_mean"] = df.combined_lean_sum / n.where(n > 0)
        df.loc[df.house_lean_sum.isna() & df.senate_lean_sum.isna(), "combined_lean_sum"] = math.nan
    return df


def add_context(df: pd.DataFrame) -> pd.DataFrame:
    pres = presidents()[["election_year", "midterm_in_tenure", "midterm_in_career", "party_wh_midterm"]]
    df = df.merge(pres, on="election_year", how="left").merge(gallup(), on="election_year", how="left")
    df["term_context"] = df.midterm_in_tenure.map({1: "first", 2: "second", 3: "third"})
    return df


# -------------------------------------------------------------------- 2026 ---
def build_2026(seats: pd.DataFrame, house_vote: pd.DataFrame, calls: pd.DataFrame, status: dict,
               baseline: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Preliminary 2026 row from called races; uncalled races bound the result."""
    y, P = 2026, "Republican"
    pres = presidents().set_index("election_year")
    row = {"election_year": y, "congress": leg.congress_number(y), "president": pres.loc[y, "president"],
           "pres_party": P, "baseline": baseline,
           "races_called": status["called"], "races_uncalled": status["uncalled"],
           "calls_snapshot": status.get("snapshot"), "calls_latest_utc": status.get("latest_call_utc")}
    row["status"] = "preliminary" if status["uncalled"] else "final (all races called)"
    flip_rows = []
    for ch in CHAMBERS:
        c = calls[calls.chamber == ch]
        before_eday = leg.composition(y, ch, "election_day")
        total = 435 if ch == "house" else 100
        if baseline == "election_day":
            before = dict(dem=before_eday["dem"], rep=before_eday["rep"], total=total)
            used = baseline
        else:
            r = seats.set_index(["election_year", "chamber"]).loc[(2024, ch)]
            before = dict(dem=int(r.dem), rep=int(r.rep), total=int(r.total))
            used = baseline
        called = c[c.called]
        delta_p = int(((called.winner_party == P).astype(int) - (called.incumbent_party == P).astype(int)).sum())
        delta_o = int(((called.winner_party == fl.other_party(P)).astype(int)
                       - (called.incumbent_party == fl.other_party(P)).astype(int)).sum())
        unc = c[~c.called]
        after = dict(dem=before["dem"] + delta_o, rep=before["rep"] + delta_p, total=total)
        m = chamber_metrics(before, after, ch, P)
        m["control_after"] = m["control_after"] + (" (provisional)" if len(unc) else "")
        for k, v in m.items():
            row[f"{ch}_{k}"] = v
        row[f"{ch}_baseline_used"] = used
        row[f"{ch}_seat_source"] = "AP calls on top of congress-legislators Election Day holders"
        row[f"{ch}_uncalled"] = len(unc)
        row[f"{ch}_swing_min"] = m["swing"] - int((unc.incumbent_party == P).sum())
        row[f"{ch}_swing_max"] = m["swing"] + int((unc.incumbent_party != P).sum())
        ch_flips = called[(called.incumbent_party == P) & (called.winner_party != P)].assign(lost=1, gained=0)
        ch_gain = called[(called.incumbent_party != P) & (called.winner_party == P)]
        ch_flips = ch_flips.assign(election_year=y, unmatched_lost=0)
        lean = fl.attach_lean(ch_flips, y, ch, P, district_pres=_pres_2026_house() if ch == "house" else None)
        if ch == "house":
            redrawn = set(pd.read_csv(CONFIG / "redistricted_2026.csv").state)
            lean.loc[lean.state.isin(redrawn), ["lean_margin", "lean_pvi_style"]] = math.nan
        lean = lean.assign(gained=0)
        lm = lean_metrics(pd.concat([lean, ch_gain.assign(lost=0, gained=1, unmatched_lost=0)],
                                    ignore_index=True))
        for k, v in lm.items():
            row[f"{ch}_{k}"] = v
        flip_rows.append(lean.assign(chamber=ch, pres_party=P))
        if ch == "senate":
            up = c.rename(columns={"incumbent_party": "party"})
            unc_p = int(((~c.called) & (c.incumbent_party == P)).sum())
            row.update(senate_up_metrics(y, P, lost=len(ch_flips), gained=len(ch_gain), up=up))
            row["senate_up_share_lost_max"] = (len(ch_flips) + unc_p) / row["senate_pres_seats_up"]
        else:
            row["house_held_share_lost"] = len(ch_flips) / row["house_seats_before"] if len(called) else math.nan
            row["house_held_share_basis"] = "gross seats lost (called races only)"
            row["house_held_share_lost_max"] = (len(ch_flips) + int(((~c.called) & (c.incumbent_party == P)).sum())) \
                / row["house_seats_before"]
    keep = ("held_share_basis", "held_share_lost_max", "seats_up", "up_lost", "up_won", "share_lost_max", "seats_before", "opp_seats_before", "chamber_size", "baseline_used", "seat_source", "uncalled",
            "held_majority", "exposed_majority", "control_before", "swing_min", "swing_max")
    empty = [ch for ch in CHAMBERS if (calls[calls.chamber == ch].called).sum() == 0]
    for ch in empty:
        # nothing called in this chamber yet: blank its results rather than report 0
        for k in list(row):
            if k.startswith(f"{ch}_") and not k.endswith(keep):
                row[k] = math.nan
    if len(empty) == len(CHAMBERS):
        row["status"] = "pending (no races called)"
    hv = house_vote.set_index("year").dem2
    row.update(vote_metrics(hv, y, P))  # 2026 national vote not available until certified
    df = combine(pd.DataFrame([row]))
    if empty:  # a combined figure would silently be one chamber's
        df[[c for c in df.columns if c.startswith("combined_")]] = math.nan
    df = add_context(df)
    return df, pd.concat(flip_rows, ignore_index=True)


def _pres_2026_house() -> pd.DataFrame:
    """2024 presidential result by district on the 2024 lines, keyed for 2026.

    Valid only where a state's 2026 map equals its 2024 map; states listed in
    config/redistricted_2026.csv are blanked by the caller."""
    p = pd.read_csv(fl.fetch(fl.CERVAS["pres_by_cd"], dataset="pres_by_cd",
                             source="The Downballot presidential results by CD (jcervas mirror)"))
    p = p[(p.lines == "2024") & (p.pres_year == 2024)]
    return pd.DataFrame({"year": 2026, "stcd": p.stcd, "dpres": p.dpres})
