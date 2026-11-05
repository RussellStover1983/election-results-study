"""Tidy CSV, per-metric ranking tables and charts."""
from __future__ import annotations

import math

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
from plotly.subplots import make_subplots  # noqa: E402

from . import OUTPUT  # noqa: E402

# reference categorical palette (light mode), slots 1-3
HOUSE_C, SENATE_C, ACCENT_C = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"

# metric -> (label, sort ascending means "worse first"?)
RANKED = {
    "house_swing": ("House net seat swing (seats)", True),
    "house_swing_pct": ("House net seat swing (% of chamber)", True),
    "senate_swing": ("Senate net seat swing (seats)", True),
    "senate_swing_pct": ("Senate net seat swing (% of chamber)", True),
    "combined_swing": ("Combined net seat swing (seats)", True),
    "combined_swing_pct": ("Combined net seat swing (% of all seats)", True),
    "house_held_share_lost": ("House share of the president's party's seats that it lost", False),
    "senate_up_share_lost": ("Senate share of the president's party's seats on the ballot that it lost", False),
    "house_exposed_share_lost": ("House share of exposed majority lost", False),
    "senate_exposed_share_lost": ("Senate share of exposed majority lost", False),
    "combined_exposed_share_lost": ("Combined share of exposed majority lost", False),
    "house_lean_sum": ("House lean-weighted flips: total (pts)", False),
    "house_lean_mean": ("House lean-weighted flips: mean lean of flipped seats (pts)", False),
    "senate_lean_sum": ("Senate lean-weighted flips: total (pts)", False),
    "senate_lean_mean": ("Senate lean-weighted flips: mean lean (pts)", False),
    "combined_lean_sum": ("Combined lean-weighted flips: total (pts)", False),
    "combined_lean_mean": ("Combined lean-weighted flips: mean lean (pts)", False),
    "house_vote_swing_vs_prior_pres": ("National House vote swing vs prior presidential year (pts)", True),
    "house_vote_swing_vs_prior_midterm": ("National House vote swing vs prior midterm (pts)", True),
}


def year_label(r) -> str:
    if r.election_year == 2026 and not str(r.status).startswith("final"):
        return "2026‡"
    return str(int(r.election_year))


def rankings(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    out = {}
    for m, (label, asc) in RANKED.items():
        if m not in df:
            continue
        t = df[["election_year", "president", "pres_party", "status", m]].dropna(subset=[m])
        t = t.sort_values(m, ascending=asc, kind="mergesort").reset_index(drop=True)
        t.insert(0, "rank", range(1, len(t) + 1))
        t["highlight"] = t.election_year == 2026
        out[m] = t
    return out


def write_rankings(df: pd.DataFrame, path_dir) -> None:
    path_dir.mkdir(parents=True, exist_ok=True)
    ranks = rankings(df)
    r26 = df[df.election_year == 2026]
    lines = ["# Midterm collapse rankings", "",
             "Most severe first. **Bold rows = 2026.** ‡ = preliminary (uncalled races remain); "
             "see `midterms.csv` columns `races_called`, `races_uncalled`, `*_swing_min/max`.", ""]
    if len(r26):
        r = r26.iloc[0]
        lines += [f"2026 status: **{r.status}** — {int(r.races_called)} races called, "
                  f"{int(r.races_uncalled)} uncalled (calls snapshot: {r.calls_snapshot or 'none'}).", ""]
    for m, t in ranks.items():
        label = RANKED[m][0]
        t.to_csv(path_dir / f"{m}.csv", index=False)
        lines += [f"## {label}", "", "| Rank | Year | President | Party | Value |", "|---:|---|---|---|---:|"]
        for r in t.itertuples():
            v = getattr(r, m)
            val = f"{v:.0%}" if m in ("senate_up_share_lost", "house_held_share_lost") else f"{v:.2f}" if "share" in m else f"{v:+.1f}" if abs(v - round(v)) > 1e-9 else f"{int(v):+d}"
            cells = [str(r.rank), year_label(r), r.president, r.pres_party[0], val]
            if r.highlight:
                cells = [f"**{c}**" for c in cells]
            lines.append("| " + " | ".join(cells) + " |")
        if len(r26) and 2026 not in set(t.election_year):
            lines.append(f"| **—** | **2026‡** | **{r26.iloc[0].president}** | **R** | **no result yet ({r26.iloc[0].status})** |")
        lines.append("")
    (path_dir.parent / "rankings.md").write_text("\n".join(lines))


# ------------------------------------------------------------------- charts ---
def _style(ax):
    ax.set_facecolor(SURFACE)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=INK2, labelsize=9)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def chart_swing(df: pd.DataFrame, cdir) -> None:
    d = df.sort_values("election_year")
    fig, axes = plt.subplots(2, 1, figsize=(12, 7), sharex=True, facecolor=SURFACE)
    for ax, ch, c, name in [(axes[0], "house", HOUSE_C, "House"), (axes[1], "senate", SENATE_C, "Senate")]:
        _style(ax)
        prelim = ~d.status.str.startswith("final")
        ax.bar(d.election_year[~prelim], d[f"{ch}_swing"][~prelim], width=2.6, color=c)
        if prelim.any():
            ax.bar(d.election_year[prelim], d[f"{ch}_swing"][prelim], width=2.6, color="none",
                   edgecolor=c, hatch="///", linewidth=1)
        ax.axhline(0, color=INK2, linewidth=0.8)
        ax.set_ylabel(f"{name}: seats", color=INK2)
        worst = d.nsmallest(3, f"{ch}_swing")
        for r in worst.itertuples():
            v = getattr(r, f"{ch}_swing")
            ax.annotate(f"{year_label(r)}  {int(v):+d}", (r.election_year, v), textcoords="offset points",
                        xytext=(0, -12), ha="center", fontsize=8, color=INK)
    axes[0].set_title("Net seat change for the president's party at each midterm, 1894–2026",
                      loc="left", color=INK, fontsize=12)
    axes[1].set_xticks(range(1894, 2027, 8))
    fig.text(0.01, 0.005, "Hatched = preliminary (uncalled races). Sources: README.", color=INK2, fontsize=8)
    fig.tight_layout()
    fig.savefig(cdir / "seat_swing_over_time.png", dpi=200)
    plt.close(fig)

    f = make_subplots(rows=2, cols=1, shared_xaxes=True, subplot_titles=("House", "Senate"))
    for i, (ch, c) in enumerate([("house", HOUSE_C), ("senate", SENATE_C)], start=1):
        f.add_bar(x=d.election_year, y=d[f"{ch}_swing"], marker_color=c, name=ch.title(),
                  customdata=d[["president", f"{ch}_swing_pct", "status"]],
                  hovertemplate="%{x} · %{customdata[0]}<br>%{y:+d} seats (%{customdata[1]:+.1f}% of chamber)"
                                "<br>%{customdata[2]}<extra></extra>", row=i, col=1)
    f.update_layout(title="Net seat change for the president's party at each midterm, 1894–2026",
                    template="simple_white", height=650)
    f.write_html(cdir / "seat_swing_over_time.html", include_plotlyjs="cdn")


def chart_exposed(df: pd.DataFrame, cdir) -> None:
    d = df.sort_values("election_year")
    fig, axes = plt.subplots(1, 2, figsize=(13, 7), facecolor=SURFACE)
    for ax, ch, c, name in [(axes[0], "house", HOUSE_C, "House"), (axes[1], "senate", SENATE_C, "Senate")]:
        _style(ax)
        s = d.dropna(subset=[f"{ch}_exposed_share_lost"]).reset_index(drop=True)
        ax.barh(range(len(s)), s[f"{ch}_exposed_share_lost"], color=c, height=0.7)
        ax.set_yticks(range(len(s)), [year_label(r) for r in s.itertuples()])
        ax.invert_yaxis()
        ax.axvline(1.0, color=INK, linewidth=1, linestyle="--")
        ax.text(1.02, len(s) - 0.4, "≥1: control lost", fontsize=8, color=INK, va="top")
        ax.set_title(f"{name}", loc="left", color=INK)
        ax.tick_params(axis="y", labelsize=7)
        ax.grid(axis="x", color=GRID)
        ax.grid(axis="y", visible=False)
    fig.suptitle("Share of the president's party's exposed majority lost at the midterm "
                 "(midterms where it held the chamber)", x=0.01, ha="left", color=INK, fontsize=12)
    fig.tight_layout()
    fig.savefig(cdir / "exposed_majority_lost.png", dpi=200)
    plt.close(fig)

    f = make_subplots(rows=1, cols=2, subplot_titles=("House", "Senate"), shared_yaxes=False)
    for i, (ch, c) in enumerate([("house", HOUSE_C), ("senate", SENATE_C)], start=1):
        s = d.dropna(subset=[f"{ch}_exposed_share_lost"])
        f.add_bar(y=[year_label(r) for r in s.itertuples()], x=s[f"{ch}_exposed_share_lost"], orientation="h",
                  marker_color=c, name=ch.title(),
                  customdata=s[["president", f"{ch}_swing", f"{ch}_exposed_majority", f"{ch}_control_flipped"]],
                  hovertemplate="%{y} · %{customdata[0]}<br>lost %{x:.2f} of exposed majority"
                                "<br>swing %{customdata[1]:+d}; cushion %{customdata[2]}"
                                "<br>control flipped: %{customdata[3]}<extra></extra>", row=1, col=i)
        f.add_vline(x=1.0, line_dash="dash", row=1, col=i)
    f.update_layout(title="Share of exposed majority lost", template="simple_white", height=800)
    f.write_html(cdir / "exposed_majority_lost.html", include_plotlyjs="cdn")


def chart_scatter(df: pd.DataFrame, cdir) -> None:
    d = df.dropna(subset=["house_lean_sum"]).copy()
    d["lbl"] = [year_label(r) for r in d.itertuples()]
    fig, ax = plt.subplots(figsize=(10, 7), facecolor=SURFACE)
    _style(ax)
    ax.grid(axis="x", color=GRID)
    is26 = d.election_year == 2026
    ax.scatter(d.house_swing[~is26], d.house_lean_sum[~is26], s=60, color=HOUSE_C,
               edgecolor=SURFACE, linewidth=2, zorder=3)
    if is26.any():
        ax.scatter(d.house_swing[is26], d.house_lean_sum[is26], s=90, color=ACCENT_C,
                   edgecolor=INK, linewidth=1, zorder=4, marker="D")
    for r in d.itertuples():
        ax.annotate(r.lbl, (r.house_swing, r.house_lean_sum), textcoords="offset points", xytext=(6, 4),
                    fontsize=8, color=INK)
    ax.axvline(0, color=INK2, linewidth=0.8)
    ax.axhline(0, color=INK2, linewidth=0.8)
    ax.set_xlabel("House net seat swing for the president's party (seats)", color=INK2)
    ax.set_ylabel("Sum of the president's party's prior presidential margin\n"
                  "in House seats it lost (points)", color=INK2)
    ax.set_title("Raw seat swing vs. lean-weighted flips, House midterms 1954–2026", loc="left", color=INK)
    fig.tight_layout()
    fig.savefig(cdir / "swing_vs_lean_weighted_flips.png", dpi=200)
    plt.close(fig)

    f = go.Figure(go.Scatter(
        x=d.house_swing, y=d.house_lean_sum, mode="markers+text", text=d.lbl, textposition="top right",
        marker=dict(size=11, color=[ACCENT_C if y == 2026 else HOUSE_C for y in d.election_year],
                    line=dict(color=SURFACE, width=2)),
        customdata=d[["president", "house_flips_against", "house_lean_mean"]],
        hovertemplate="%{text} · %{customdata[0]}<br>swing %{x:+d} seats<br>%{customdata[1]} seats lost; "
                      "lean sum %{y:.0f} pts, mean %{customdata[2]:.1f}<extra></extra>"))
    f.update_layout(title="Raw seat swing vs. lean-weighted flips (House)", template="simple_white",
                    xaxis_title="House net seat swing (seats)", yaxis_title="Lean-weighted flips (pts)",
                    height=650)
    f.write_html(cdir / "swing_vs_lean_weighted_flips.html", include_plotlyjs="cdn")


def write_all(df: pd.DataFrame, changes: pd.DataFrame, out=OUTPUT) -> None:
    out.mkdir(parents=True, exist_ok=True)
    df.to_csv(out / "midterms.csv", index=False, float_format="%.4g")
    if len(changes):
        changes.to_csv(out / "flipped_seats.csv", index=False, float_format="%.4g")
    write_rankings(df, out / "rankings")
    cdir = out / "charts"
    cdir.mkdir(exist_ok=True)
    chart_swing(df, cdir)
    chart_exposed(df, cdir)
    chart_scatter(df, cdir)


def _isnan(x) -> bool:
    return isinstance(x, float) and math.isnan(x)
