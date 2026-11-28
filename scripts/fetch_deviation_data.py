"""Fetch benchmark index daily K-lines & missing core stock daily K-lines for 卡异动 monitor.

- Benchmark indices saved to `data/index_kline.json`:
    sh000002 (上证A指 -> 沪市主板)
    sz399107 (深证A指 -> 深市主板)
    sz399102 (创业板综 -> 创业板)
    sh000688 (科创50   -> 科创板)
- Stock daily forward-adjusted closes saved to `data/raw_kline/{code}.json`.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data/super_board.sqlite"
KLINE_DIR = ROOT / "data/raw_kline"
INDEX_KLINE_PATH = ROOT / "data/index_kline.json"
MIN_DISPLAY_DATE = "2025-10-01"
BENCHMARK_INDICES = ["sh000002", "sz399107", "sz399102", "sh000688"]


def _qt_symbol(code: str) -> str:
    prefix = "sh" if code.startswith(("6", "90")) else "bj" if code.startswith(("8", "4", "92")) else "sz"
    return f"{prefix}{code}"


def fetch_tencent_kline(sym: str, start: str = "2025-07-01", end: str = "2026-12-31") -> list[list[Any]]:
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={sym},day,{start},{end},420,qfq"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=7.0) as resp:
                doc = json.loads(resp.read().decode("utf-8", errors="ignore"))
            node = (doc.get("data") or {}).get(sym) or {}
            rows = node.get("qfqday") or node.get("day") or []
            out: list[list[Any]] = []
            for r in rows:
                if isinstance(r, list) and len(r) >= 3:
                    dt = str(r[0])
                    close = round(float(r[2]), 4)
                    if len(dt) == 10 and close > 0:
                        out.append([dt, close])
            return out
        except Exception:
            if attempt < 2:
                time.sleep(0.3 * (attempt + 1))
    return []


def fetch_indices() -> dict[str, list[list[Any]]]:
    data: dict[str, list[list[Any]]] = {}
    for sym in BENCHMARK_INDICES:
        rows = fetch_tencent_kline(sym)
        if rows:
            data[sym] = rows
    INDEX_KLINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = INDEX_KLINE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    os.replace(tmp, INDEX_KLINE_PATH)
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch benchmark index & core stock K-lines for 卡异动")
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--refresh-stale", action="store_true", help="Also refresh existing files older than latest DB date")
    args = parser.parse_args()

    t0 = time.perf_counter()
    idx_data = fetch_indices()
    print(
        "Indices updated:",
        {k: (len(v), v[-1][0] if v else "") for k, v in idx_data.items()},
        flush=True,
    )

    conn = sqlite3.connect(DB_PATH)
    try:
        latest_dt = str(conn.execute("SELECT MAX(trade_date) FROM daily_limit_pool").fetchone()[0] or "2026-11-27")
        core_codes = [
            str(r[0])
            for r in conn.execute(
                """
                SELECT DISTINCT code FROM daily_limit_pool
                WHERE trade_date >= ? AND (board_height >= 2 OR is_fanbao = 1)
                ORDER BY code ASC
                """,
                (MIN_DISPLAY_DATE,),
            ).fetchall()
        ]
    finally:
        conn.close()

    KLINE_DIR.mkdir(parents=True, exist_ok=True)
    todo: list[str] = []
    for c in core_codes:
        p = KLINE_DIR / f"{c}.json"
        if not p.exists():
            todo.append(c)
        elif args.refresh_stale:
            try:
                days = json.loads(p.read_text(encoding="utf-8")).get("days") or []
                if not days or days[-1][0] < latest_dt:
                    todo.append(c)
            except Exception:
                todo.append(c)

    print(f"Core codes: {len(core_codes)}, missing/stale to fetch: {len(todo)}", flush=True)
    if not todo:
        return

    ok = 0
    fail = 0

    def _work(code: str) -> bool:
        rows = fetch_tencent_kline(_qt_symbol(code))
        if not rows:
            return False
        p = KLINE_DIR / f"{code}.json"
        tmp = p.with_suffix(".tmp")
        tmp.write_text(
            json.dumps({"code": code, "days": rows}, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        os.replace(tmp, p)
        return True

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(_work, c): c for c in todo}
        for i, fut in enumerate(as_completed(futs), 1):
            try:
                if fut.result():
                    ok += 1
                else:
                    fail += 1
            except Exception:
                fail += 1
            if i % 200 == 0 or i == len(todo):
                print(f"  [{i}/{len(todo)}] ok={ok} fail={fail} ({time.perf_counter()-t0:.1f}s)", flush=True)

    print(f"DONE K-line sync in {time.perf_counter()-t0:.1f}s: ok={ok}, fail={fail}", flush=True)


if __name__ == "__main__":
    main()
