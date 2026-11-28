"""Resumable day-bundled intraday minute chart backfiller for Super-Board.

Stores one compact JSON bundle per trading day under `data/intraday_days/{YYYY-MM-DD}.json`
containing all core ladder stocks (2板+, 反包, and yesterday's >=3板 broken boards), plus
optional first boards via `--include-first-boards`.

Usage:
  python scripts/fetch_intraday.py                    # Backfill all core stocks since 2025-10-01
  python scripts/fetch_intraday.py --date 2026-11-27  # Fetch/refresh a single trading day
  python scripts/fetch_intraday.py --days 5           # Fetch/refresh latest 5 trading days
"""
from __future__ import annotations

import argparse
import http.client
import json
import os
import re
import sqlite3
import sys
import threading
import time
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data/super_board.sqlite"
INTRADAY_DAYS_DIR = ROOT / "data/intraday_days"
RAW_INTRADAY_DIR = ROOT / "data/raw_intraday"
SHARES_CACHE_PATH = ROOT / "data/shares_cache.json"
MIN_DISPLAY_DATE = "2025-10-01"

_CODE_RE = re.compile(r"^\d{6}$")
_TLS = threading.local()
_SHARES_LOCK = threading.Lock()


def _qt_symbol(code: str) -> str:
    prefix = "sh" if code.startswith(("6", "90")) else "bj" if code.startswith(("8", "4", "92")) else "sz"
    return f"{prefix}{code}"


def load_shares_cache() -> dict[str, dict[str, float]]:
    if SHARES_CACHE_PATH.exists():
        try:
            doc = json.loads(SHARES_CACHE_PATH.read_text(encoding="utf-8"))
            if isinstance(doc, dict):
                return doc
        except Exception:
            pass
    return {}


def save_shares_cache(cache: dict[str, dict[str, float]]) -> None:
    SHARES_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = SHARES_CACHE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(cache, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    os.replace(tmp, SHARES_CACHE_PATH)


def batch_fetch_shares(codes: list[str], cache: dict[str, dict[str, float]]) -> int:
    missing = [c for c in dict.fromkeys(codes) if _CODE_RE.match(c) and c not in cache]
    if not missing:
        return 0
    added = 0
    for i in range(0, len(missing), 60):
        chunk = missing[i : i + 60]
        syms = ",".join(_qt_symbol(c) for c in chunk)
        url = f"https://qt.gtimg.cn/q={syms}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=6.0) as resp:
                text = resp.read().decode("gbk", errors="ignore")
        except Exception:
            continue
        for line in text.splitlines():
            if '="' not in line:
                continue
            head, rest = line.split('="', 1)
            body = rest.split('"', 1)[0]
            m = re.search(r"(\d{6})$", head.strip())
            if not m:
                continue
            code = m.group(1)
            parts = body.split("~")
            if len(parts) <= 45:
                continue
            try:
                px = float(parts[3] or 0) or float(parts[4] or 0)
                float_mv = float(parts[44] or 0)
                total_mv = float(parts[45] or 0)
            except ValueError:
                continue
            if px <= 0 or (total_mv <= 0 and float_mv <= 0):
                continue
            if total_mv <= 0:
                total_mv = float_mv
            if float_mv <= 0:
                float_mv = total_mv
            cache[code] = {
                "total_shares": round(total_mv / px, 6),
                "float_shares": round(float_mv / px, 6),
            }
            added += 1
    if added:
        save_shares_cache(cache)
    return added


def kpl_post_trend(code: str, date: str) -> dict[str, Any] | None:
    body = urlencode(
        {
            "a": "GetStockTrend",
            "c": "StockL2History",
            "StockID": code,
            "Day": date,
            "apiv": "w38",
            "PhoneOSNew": "2",
            "VerSion": "5.17.0.9",
        }
    ).encode("utf-8")
    headers = {
        "User-Agent": "lhb/5.17.9 (com.kaipanla.www; build:0; iOS 16.6.0) Alamofire/4.9.1",
        "Content-Type": "application/x-www-form-urlencoded",
        "Connection": "keep-alive",
    }
    for attempt in range(3):
        conn: http.client.HTTPSConnection | None = getattr(_TLS, "kpl_conn", None)
        if conn is None:
            conn = http.client.HTTPSConnection("apphis.longhuvip.com", timeout=6.5)
            _TLS.kpl_conn = conn
        try:
            conn.request("POST", "/w1/api/index.php", body=body, headers=headers)
            resp = conn.getresponse()
            raw = resp.read()
            if resp.status != 200:
                return None
            return json.loads(raw.decode("utf-8", errors="ignore"))
        except Exception:
            try:
                conn.close()
            except Exception:
                pass
            _TLS.kpl_conn = None
            if attempt < 2:
                time.sleep(0.25 * (attempt + 1))
    return None


def build_one_payload(
    code: str,
    date: str,
    pool_metrics: tuple[float | None, float | None],
    shares: dict[str, float] | None,
) -> dict[str, Any] | None:
    raw_json = kpl_post_trend(code, date)
    if not raw_json:
        return None
    trend = raw_json.get("trend") or []
    if not isinstance(trend, list) or len(trend) < 2:
        return None

    points: list[list[Any]] = []
    for row in trend:
        if not isinstance(row, list) or len(row) < 4:
            continue
        try:
            px = round(float(row[1]), 3)
            avg = round(float(row[2]), 3)
            vol = int(float(row[3] or 0))
            d_flag = int(row[4]) if len(row) > 4 and row[4] is not None else 0
            points.append([px, avg, vol, d_flag])
        except Exception:
            continue

    if len(points) < 2:
        return None

    preclose = float(raw_json.get("preclose_px") or 0)
    if preclose <= 0:
        preclose = float(raw_json.get("begin_px") or points[0][0] or 0)
    close_px = points[-1][0]
    px_vals = [p[0] for p in points]
    high_px = max(px_vals)
    low_px = min(px_vals)
    pct = round((close_px - preclose) / preclose * 100.0, 2) if preclose > 0 else 0.0

    pool_amt, pool_tr = pool_metrics
    total_turnover = float(raw_json.get("total_turnover") or 0)
    amount_yi = (
        round(pool_amt, 2)
        if pool_amt is not None
        else (round(total_turnover / 1e8, 2) if total_turnover > 0 else None)
    )

    total_mv = round(shares["total_shares"] * close_px, 1) if shares and shares.get("total_shares") else None
    float_mv = round(shares["float_shares"] * close_px, 1) if shares and shares.get("float_shares") else None

    turnover = round(pool_tr, 2) if pool_tr is not None else None
    if turnover is None and float_mv and float_mv > 0 and amount_yi is not None:
        turnover = round(amount_yi / float_mv * 100.0, 2)

    return {
        "code": code,
        "date": date,
        "preclose": round(preclose, 3),
        "price": round(close_px, 2),
        "pct": pct,
        "high": round(high_px, 2),
        "low": round(low_px, 2),
        "amount_yi": amount_yi,
        "turnover": turnover,
        "total_mv": total_mv,
        "float_mv": float_mv,
        "points": points,
    }


def collect_targets(
    min_date: str,
    target_date: str | None = None,
    limit_days: int | None = None,
    include_first_boards: bool = False,
) -> tuple[list[str], dict[str, list[str]], dict[tuple[str, str], tuple[float | None, float | None]]]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        all_dates = [
            str(r[0])
            for r in conn.execute(
                "SELECT DISTINCT trade_date FROM daily_limit_pool WHERE trade_date >= ? ORDER BY trade_date DESC",
                (min_date,),
            ).fetchall()
        ]
        # Also include 1 prior trading day before min_date for broken-board detection
        prev_row = conn.execute(
            "SELECT MAX(trade_date) FROM daily_limit_pool WHERE trade_date < ?",
            (min_date,),
        ).fetchone()
        prev_anchor = str(prev_row[0]) if prev_row and prev_row[0] else ""

        if target_date:
            dates = [target_date] if target_date in all_dates else []
        elif limit_days:
            dates = all_dates[:limit_days]
        else:
            dates = all_dates

        if not dates:
            return [], {}, {}

        # Chronological prev-date map
        ordered_asc = ([prev_anchor] if prev_anchor else []) + list(reversed(all_dates))
        prev_map = {ordered_asc[i]: ordered_asc[i - 1] for i in range(1, len(ordered_asc))}

        needed_dates = set(dates) | {prev_map[d] for d in dates if d in prev_map}
        placeholders = ",".join("?" for _ in needed_dates)
        rows = conn.execute(
            f"""
            SELECT trade_date, code, board_height, is_fanbao, amount_yi, turnover_rate
            FROM daily_limit_pool
            WHERE trade_date IN ({placeholders})
            """,
            tuple(needed_dates),
        ).fetchall()

        pool_all_by_day: dict[str, set[str]] = defaultdict(set)
        high3_by_day: dict[str, list[str]] = defaultdict(list)
        core_by_day: dict[str, list[str]] = defaultdict(list)
        metrics_map: dict[tuple[str, str], tuple[float | None, float | None]] = {}

        for r in rows:
            dt = str(r["trade_date"])
            code = str(r["code"])
            h = int(r["board_height"] or 1)
            fb = bool(r["is_fanbao"])
            pool_all_by_day[dt].add(code)
            amt = float(r["amount_yi"]) if r["amount_yi"] is not None else None
            tr = float(r["turnover_rate"]) if r["turnover_rate"] is not None else None
            metrics_map[(dt, code)] = (amt, tr)
            if h >= 3:
                high3_by_day[dt].append(code)
            if include_first_boards or h >= 2 or fb:
                core_by_day[dt].append(code)

        targets_by_day: dict[str, list[str]] = {}
        for dt in dates:
            seen: set[str] = set()
            lst: list[str] = []
            for c in core_by_day.get(dt, []):
                if c not in seen:
                    seen.add(c)
                    lst.append(c)
            pdt = prev_map.get(dt)
            if pdt:
                today_pool = pool_all_by_day.get(dt, set())
                for c in high3_by_day.get(pdt, []):
                    if c not in today_pool and c not in seen:
                        seen.add(c)
                        lst.append(c)
            targets_by_day[dt] = lst
        return dates, targets_by_day, metrics_map
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill day-bundled intraday minute charts")
    parser.add_argument("--date", default="", help="Single YYYY-MM-DD date to fetch")
    parser.add_argument("--days", type=int, default=0, help="Only fetch latest N trading days")
    parser.add_argument("--min-date", default=MIN_DISPLAY_DATE)
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--include-first-boards", action="store_true", help="Also fetch all 首板 stocks")
    args = parser.parse_args()

    INTRADAY_DAYS_DIR.mkdir(parents=True, exist_ok=True)
    dates, targets_by_day, metrics_map = collect_targets(
        min_date=args.min_date,
        target_date=args.date.strip() or None,
        limit_days=args.days if args.days > 0 else None,
        include_first_boards=args.include_first_boards,
    )
    if not dates:
        print("No target dates found.")
        return

    all_codes = [c for dt in dates for c in targets_by_day.get(dt, [])]
    shares_cache = load_shares_cache()
    t_sh = time.perf_counter()
    added_shares = batch_fetch_shares(all_codes, shares_cache)
    print(
        f"Targets: {len(dates)} days, {len(all_codes)} pairs ({len(set(all_codes))} unique stocks). "
        f"Batch shares +{added_shares} in {(time.perf_counter() - t_sh):.2f}s (total cached {len(shares_cache)}).",
        flush=True,
    )

    t0 = time.perf_counter()
    total_fetched = 0
    total_reused = 0
    total_failed = 0

    with ThreadPoolExecutor(max_workers=args.workers, thread_name_prefix="kpl-bf") as pool:
        for idx, dt in enumerate(dates, 1):
            codes = targets_by_day.get(dt, [])
            bundle_path = INTRADAY_DAYS_DIR / f"{dt}.json"
            bundle: dict[str, Any] = {}
            if bundle_path.exists():
                try:
                    loaded = json.loads(bundle_path.read_text(encoding="utf-8"))
                    if isinstance(loaded, dict):
                        bundle = loaded
                except Exception:
                    bundle = {}

            # Migrate any existing individual files from data/raw_intraday/{dt}/*.json
            raw_dir = RAW_INTRADAY_DIR / dt
            migrated = False
            if raw_dir.exists():
                for fp in raw_dir.glob("*.json"):
                    c = fp.stem
                    if c not in bundle:
                        try:
                            doc = json.loads(fp.read_text(encoding="utf-8"))
                            if isinstance(doc, dict) and doc.get("points"):
                                bundle[c] = doc
                                migrated = True
                        except Exception:
                            pass

            missing = [c for c in codes if c not in bundle]
            reused = len(codes) - len(missing)
            total_reused += reused

            if not missing and not migrated and bundle_path.exists():
                continue

            fetched_today = 0
            failed_today = 0
            if missing:
                fut_map = {
                    pool.submit(
                        build_one_payload,
                        c,
                        dt,
                        metrics_map.get((dt, c), (None, None)),
                        shares_cache.get(c),
                    ): c
                    for c in missing
                }
                for fut in as_completed(fut_map):
                    c = fut_map[fut]
                    try:
                        res = fut.result()
                    except Exception:
                        res = None
                    if res:
                        bundle[c] = res
                        fetched_today += 1
                    else:
                        failed_today += 1

            total_fetched += fetched_today
            total_failed += failed_today

            # Atomic write so live serve.py never reads partial JSON
            tmp_path = bundle_path.with_suffix(".tmp")
            tmp_path.write_text(
                json.dumps(bundle, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )
            os.replace(tmp_path, bundle_path)

            if idx <= 5 or idx % 20 == 0 or idx == len(dates):
                elapsed = time.perf_counter() - t0
                rate = total_fetched / elapsed if elapsed > 0 else 0.0
                print(
                    f"[{idx:3d}/{len(dates)}] {dt}: +{fetched_today} ok, {reused} cached, {failed_today} miss | "
                    f"cum fetched={total_fetched} reused={total_reused} fail={total_failed} ({rate:.1f}/s, {elapsed:.0f}s)",
                    flush=True,
                )

    elapsed = time.perf_counter() - t0
    print(
        f"DONE in {elapsed:.1f}s: fetched={total_fetched}, reused={total_reused}, failed={total_failed}",
        flush=True,
    )


if __name__ == "__main__":
    main()
