"""Midterm collapse study: rank U.S. midterms by the presidential party's losses."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config"
DATA = ROOT / "data"
CACHE = DATA / "cache"
MANUAL = DATA / "manual"
DIR_2026 = DATA / "2026"
OUTPUT = ROOT / "output"

FIRST_MIDTERM = 1894
LEAN_START = 1952  # partisan-lean-weighted flips are computed from here on
