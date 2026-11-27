"""Evaluate exported web/data/days/*.json (core-only: 连板+反包) against display-theme & driver rules."""
from __future__ import annotations

import json
import sqlite3
from collections import Counter, deque
from pathlib import Path

from driver_rules import main_business

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data/super_board.sqlite"
DAYS_DIR = ROOT / "web/data/days"
DATES_JSON = ROOT / "web/data/dates.json"


def main() -> None:
    if DATES_JSON.exists():
        date_list = {d["date"] for d in json.loads(DATES_JSON.read_text(encoding="utf-8")).get("dates", [])}
        files = sorted(p for p in DAYS_DIR.glob("*.json") if p.stem in date_list)
    else:
        files = sorted(DAYS_DIR.glob("*.json"))

    total_core_stock_days = 0
    empty_primary = 0
    rule_violations = 0
    cont_total = 0
    cont_flips = 0
    fanbao_cont_total = 0
    fanbao_flips = 0
    display_src_counts: Counter[str] = Counter()

    # Keep rolling 5-day primary_theme history (covers yesterday streaks + fanbao pre-break)
    window_history: deque[dict[str, str]] = deque(maxlen=5)
    prev_day_map: dict[str, str] = {}

    for day_idx, p in enumerate(files):
        doc = json.loads(p.read_text(encoding="utf-8"))
        top10 = {c["theme"] for c in doc.get("catalysts", []) if c.get("theme")}
        stocks = doc.get("stocks", {})

        # Build recent 5-day primary map (latest wins)
        recent5: dict[str, str] = {}
        for day_map in window_history:
            recent5.update(day_map)

        cur_day_map: dict[str, str] = {}
        for code, st in stocks.items():
            total_core_stock_days += 1
            slot1 = st.get("primary_theme") or ""
            dsrc = st.get("display_source") or "missing"
            display_src_counts[dsrc] += 1
            cur_day_map[code] = slot1

            if not slot1:
                empty_primary += 1
            else:
                in_top10 = slot1 in top10
                eq_prev5 = (recent5.get(code) == slot1) or (day_idx < 5 and dsrc == "prev")
                eq_main = slot1 == main_business(st.get("industry"), st.get("themes"))
                if not (in_top10 or eq_prev5 or eq_main):
                    rule_violations += 1

            h = int(st.get("height") or 1)
            if h >= 2 and code in prev_day_map and prev_day_map[code]:
                cont_total += 1
                if slot1 != prev_day_map[code]:
                    cont_flips += 1
            elif h == 1 and code in recent5 and recent5[code]:
                fanbao_cont_total += 1
                if slot1 != recent5[code]:
                    fanbao_flips += 1

        window_history.append(cur_day_map)
        prev_day_map = cur_day_map

    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    evaluated_dates = [p.stem for p in files]
    driver_src_counts: Counter[str] = Counter()
    if evaluated_dates:
        ph = ",".join("?" * len(evaluated_dates))
        for src, cnt in conn.execute(
            f"SELECT source, COUNT(*) FROM daily_stock_driver WHERE trade_date IN ({ph}) GROUP BY source",
            evaluated_dates,
        ).fetchall():
            driver_src_counts[str(src)] = int(cnt)
    conn.close()

    def _pct_map(cnt: Counter[str]) -> dict[str, str]:
        tot = sum(cnt.values()) or 1
        return {k: f"{v} ({v * 100.0 / tot:.1f}%)" for k, v in sorted(cnt.items(), key=lambda kv: -kv[1])}

    report = {
        "days_evaluated": len(files),
        "date_range": [files[0].stem, files[-1].stem] if files else [],
        "total_core_stock_days": total_core_stock_days,
        "empty_primary": empty_primary,
        "rule_violations": rule_violations,
        "streak_continuations": cont_total,
        "streak_flips": cont_flips,
        "streak_flip_rate_pct": round(cont_flips * 100.0 / cont_total, 2) if cont_total else 0.0,
        "fanbao_continuations": fanbao_cont_total,
        "fanbao_flips": fanbao_flips,
        "fanbao_flip_rate_pct": round(fanbao_flips * 100.0 / fanbao_cont_total, 2) if fanbao_cont_total else 0.0,
        "display_source_breakdown": _pct_map(display_src_counts),
        "driver_source_breakdown": _pct_map(driver_src_counts),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
