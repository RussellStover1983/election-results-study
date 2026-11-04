"""Cached HTTP downloads and an append-only source log.

Every URL is fetched at most once: the body is stored under data/cache/ and
later runs read it from disk. Pass refresh=True (used only for live 2026
results) to force a new request. Every attempt, cached or not, successful or
not, is written to output/source_log.csv so each run documents where its data
came from.
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urlparse

import requests

from . import CACHE, OUTPUT

USER_AGENT = "election-results-study/0.1 (academic research script; python-requests)"
TIMEOUT = 60
LOG_PATH = OUTPUT / "source_log.csv"
_LOG_FIELDS = ["timestamp_utc", "dataset", "source", "url", "outcome", "cache_file", "detail"]
_run_log: list[dict] = []


class FetchError(RuntimeError):
    pass


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(dataset: str, source: str, url: str, outcome: str, cache_file: str = "", detail: str = "") -> None:
    row = dict(timestamp_utc=_now(), dataset=dataset, source=source, url=url,
               outcome=outcome, cache_file=cache_file, detail=detail[:300])
    _run_log.append(row)


def flush_log() -> None:
    """Rewrite the run's source log (one file per run, overwritten each run)."""
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=_LOG_FIELDS)
        w.writeheader()
        w.writerows(_run_log)


def cache_path(url: str, params: dict | None = None) -> Path:
    key = url + ("?" + json.dumps(params, sort_keys=True) if params else "")
    # never let an API key end up in a filename or the meta file
    digest = hashlib.sha1(key.encode()).hexdigest()[:16]
    host = urlparse(url).netloc.replace(":", "_") or "local"
    tail = Path(urlparse(url).path).name or "index"
    tail = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in tail)[:60]
    return CACHE / host / f"{digest}_{tail}"


def fetch(url: str, *, dataset: str, source: str, params: dict | None = None,
          refresh: bool = False, secret_params: dict | None = None,
          headers: dict | None = None) -> Path:
    """Return a local path holding the body of `url`, downloading only if needed.

    secret_params (e.g. an API key) are sent but excluded from the cache key,
    the meta file and the log.
    """
    path = cache_path(url, params)
    meta = path.with_suffix(path.suffix + ".meta.json")
    if path.exists() and not refresh:
        log(dataset, source, url, "cache-hit", str(path.relative_to(CACHE.parent.parent)))
        return path
    if os.environ.get("MIDTERMS_OFFLINE") == "1":
        log(dataset, source, url, "skipped-offline")
        raise FetchError(f"offline mode and no cache for {url}")
    try:
        r = requests.get(url, params={**(params or {}), **(secret_params or {})},
                         headers={"User-Agent": USER_AGENT, **(headers or {})}, timeout=TIMEOUT)
    except requests.RequestException as exc:  # network policy denials land here
        log(dataset, source, url, "error", detail=f"{type(exc).__name__}: {exc}")
        raise FetchError(str(exc)) from exc
    if r.status_code != 200:
        log(dataset, source, url, f"http-{r.status_code}")
        raise FetchError(f"HTTP {r.status_code} for {url}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(r.content)
    meta.write_text(json.dumps({"url": url, "params": params, "fetched_utc": _now(),
                                "bytes": len(r.content),
                                "sha256": hashlib.sha256(r.content).hexdigest()}, indent=1))
    log(dataset, source, url, "downloaded", str(path.relative_to(CACHE.parent.parent)))
    return path


def first_working(dataset: str, attempts: list[tuple[str, str, callable]], **kw):
    """Try (source_name, url, parser) in order; return (parsed, source_name, url).

    A parser that raises (layout changed, page blocked, empty result) moves the
    chain on to the next source. Raises FetchError if every source fails.
    """
    errors = []
    for name, url, parser in attempts:
        try:
            path = fetch(url, dataset=dataset, source=name, **kw)
            out = parser(path)
            log(dataset, name, url, "parsed")
            return out, name, url
        except Exception as exc:  # noqa: BLE001 - any failure means "try next source"
            if not isinstance(exc, FetchError):
                log(dataset, name, url, "parse-failed", detail=f"{type(exc).__name__}: {exc}")
            errors.append(f"{name}: {exc}")
    raise FetchError(f"all sources failed for {dataset}: " + " | ".join(errors))
