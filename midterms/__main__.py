"""Run the full pipeline:  python -m midterms [--refresh-2026] [--baseline ...]"""
from __future__ import annotations

import argparse
import sys

import pandas as pd

from . import CONFIG, OUTPUT, ap2026, fetch, metrics, outputs, returns, seats, validate


def apply_overrides(s: pd.DataFrame) -> pd.DataFrame:
    ov = pd.read_csv(CONFIG / "overrides.csv")
    for o in ov.itertuples():
        m = (s.election_year == o.election_year) & (s.chamber == o.chamber)
        fetch.log("overrides", "manual override", "config/overrides.csv", "applied",
                  detail=f"{o.election_year} {o.chamber} {o.field}: {s.loc[m, o.field].tolist()} -> {o.value} "
                         f"({o.reason})")
        s.loc[m, o.field] = type(s.loc[m, o.field].iloc[0])(o.value)
    return s


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--baseline", choices=metrics.BASELINES, default="election_day",
                    help="what 'seats before' means (see README)")
    ap.add_argument("--refresh-2026", action="store_true", help="pull new AP calls and snapshot them")
    ap.add_argument("--no-validation-gate", action="store_true",
                    help="write outputs even if the known-figure checks fail")
    ap.add_argument("--out", default=str(OUTPUT))
    a = ap.parse_args(argv)
    out = OUTPUT.__class__(a.out)

    s = apply_overrides(seats.build())
    out.mkdir(parents=True, exist_ok=True)
    s.to_csv(out / "seats_by_congress.csv", index=False)

    v = validate.run(s)
    v.to_csv(out / "validation.csv", index=False)
    print("\nValidation against known figures:")
    print(v.pivot_table(index=["election_year", "chamber", "party", "expected"], columns="baseline",
                        values="computed").to_string())
    failed = v[(v.baseline == a.baseline) & ~v.ok]
    if len(failed) and not a.no_validation_gate:
        fetch.flush_log()
        print(f"\nSTOP: {len(failed)} check(s) do not reconcile under baseline '{a.baseline}'. "
              "No metric outputs written. See output/validation.csv.", file=sys.stderr)
        return 2

    if a.refresh_2026:
        print("2026:", ap2026.refresh())
    ap2026.write_template()
    calls, status = ap2026.current_calls()
    hv = returns.national_house_vote()
    hv.to_csv(out / "national_house_vote.csv", index=False)
    returns.medsl("senate")  # downloaded for reference/cross-checks when reachable

    df, changes = metrics.build(s, hv, a.baseline)
    r26, ch26 = metrics.build_2026(s, hv, calls, status, a.baseline)
    df = pd.concat([df, r26], ignore_index=True)
    changes = pd.concat([changes, ch26], ignore_index=True)
    outputs.write_all(df, changes, out)
    fetch.flush_log()
    print(f"\n2026: {status['called']} races called, {status['uncalled']} uncalled "
          f"(snapshot: {status['snapshot']}). Outputs in {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
