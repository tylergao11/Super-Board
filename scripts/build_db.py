"""Pure-stdlib SQLite builder & manual override merger for Super-Board."""
from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any

from common import (
    DB_PATH,
    ROOT,
    clean_stock_name,
    extract_controller_province,
    load_taxonomy,
    validate_record,
)

SHARD_DIR = ROOT / "data/shards"
TAGGED_DIR = ROOT / "data/tagged"
HOT_NEWS_DIR = ROOT / "data/hot_news"
OVERRIDES_PATH = ROOT / "manual_overrides.json"
SUMMARY_PATH = ROOT / "data/summary.json"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS stocks (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    province TEXT NOT NULL,
    city TEXT,
    controller_type TEXT NOT NULL,
    controller_name TEXT,
    controller_province TEXT,
    overseas_pct REAL,
    em_industry TEXT,
    latest_report_date TEXT,
    audit_notes TEXT,
    manual_verified INTEGER DEFAULT 0,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS static_tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL,
    l1 TEXT NOT NULL,
    revenue_pct REAL,
    evidence TEXT NOT NULL,
    UNIQUE(code, l1),
    FOREIGN KEY(code) REFERENCES stocks(code)
);

CREATE TABLE IF NOT EXISTS dynamic_tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL,
    group_name TEXT NOT NULL,
    from_date TEXT NOT NULL,
    to_date TEXT,
    evidence TEXT NOT NULL,
    FOREIGN KEY(code) REFERENCES stocks(code)
);

CREATE TABLE IF NOT EXISTS ma_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL,
    event_type TEXT NOT NULL,
    target_name TEXT NOT NULL,
    target_l1 TEXT,
    from_date TEXT NOT NULL,
    evidence TEXT NOT NULL,
    FOREIGN KEY(code) REFERENCES stocks(code)
);

CREATE TABLE IF NOT EXISTS daily_limit_pool (
    trade_date TEXT NOT NULL,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    board_height INTEGER NOT NULL,
    boards_desc TEXT,
    first_limit_time TEXT,
    amount_yi REAL,
    turnover_rate REAL,
    is_one_word INTEGER DEFAULT 0,
    is_fanbao INTEGER DEFAULT 0,
    kpl_topic TEXT,
    kpl_reason TEXT,
    PRIMARY KEY (trade_date, code)
);

CREATE TABLE IF NOT EXISTS daily_hot_news (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date TEXT NOT NULL,
    rank INTEGER NOT NULL,
    headline TEXT NOT NULL,
    detail TEXT NOT NULL,
    hit_count INTEGER DEFAULT 0,
    UNIQUE(trade_date, rank)
);

CREATE INDEX IF NOT EXISTS idx_static_l1 ON static_tags(l1);
CREATE INDEX IF NOT EXISTS idx_static_code ON static_tags(code);
CREATE INDEX IF NOT EXISTS idx_dyn_group ON dynamic_tags(group_name);
CREATE INDEX IF NOT EXISTS idx_dyn_code ON dynamic_tags(code);
CREATE INDEX IF NOT EXISTS idx_ma_code ON ma_events(code);
CREATE INDEX IF NOT EXISTS idx_ma_target_l1 ON ma_events(target_l1);
CREATE INDEX IF NOT EXISTS idx_pool_code ON daily_limit_pool(code);
CREATE INDEX IF NOT EXISTS idx_hot_news_date ON daily_hot_news(trade_date);
"""


def ensure_db(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("DROP TABLE IF EXISTS exclusions")
    static_cols = {r[1] for r in conn.execute("PRAGMA table_info(static_tags)").fetchall()}
    if "weight" in static_cols:
        conn.execute("DROP TABLE static_tags")
    ma_cols = {r[1] for r in conn.execute("PRAGMA table_info(ma_events)").fetchall()}
    if "status" in ma_cols:
        conn.execute("DROP TABLE ma_events")
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    return conn


def load_overrides() -> dict[str, dict[str, Any]]:
    if not OVERRIDES_PATH.exists():
        return {}
    return json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))


def apply_override(rec: dict[str, Any], ov: dict[str, Any] | None) -> dict[str, Any]:
    merged = dict(rec)
    if ov:
        for k, v in ov.items():
            if k != "note":
                merged[k] = v
        merged["manual_verified"] = 1
    else:
        merged["manual_verified"] = int(merged.get("manual_verified") or 0)
    merged["name"] = clean_stock_name(merged.get("name"))
    return merged


def load_tagged(prefix: str | None = None) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], list[str]]:
    taxonomy = load_taxonomy()
    overrides = load_overrides()

    shard_glob = f"{prefix}_shard_*.json" if prefix else "*_shard_*.json"
    ev_map: dict[str, dict[str, Any]] = {}
    for p in sorted(SHARD_DIR.glob(shard_glob)):
        doc = json.loads(p.read_text(encoding="utf-8"))
        for item in doc.get("stocks", []):
            ev_map[item["code"]] = item

    records: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for p in sorted(TAGGED_DIR.glob(shard_glob)):
        doc = json.loads(p.read_text(encoding="utf-8"))
        for rec in doc.get("stocks", []):
            code = str(rec.get("code") or "")
            ev = ev_map.get(code)
            merged = apply_override(rec, overrides.get(code))
            errs = validate_record(merged, ev, taxonomy)
            if errs:
                errors.extend(f"{p.name}: {e}" for e in errs)
            records[code] = merged

    if prefix and ev_map:
        missing = sorted(set(ev_map.keys()) - set(records.keys()))
        if missing:
            errors.append(f"missing {len(missing)} stocks for {prefix}: {missing[:15]}")
    return records, ev_map, errors


def upsert_records(
    records: dict[str, dict[str, Any]],
    ev_map: dict[str, dict[str, Any]],
    db_path: Path = DB_PATH,
) -> dict[str, Any]:
    taxonomy = load_taxonomy()
    conn = ensure_db(db_path)

    for code in sorted(records.keys()):
        rec = records[code]
        ev = ev_map.get(code, {})
        overseas = rec.get("overseas_pct")
        if overseas is None:
            overseas = ev.get("overseas_pct_hint")
        ctrl_name = rec.get("controller_name") or ev.get("controller_name")
        ctrl_prov = rec.get("controller_province") or ev.get("controller_province_hint") or extract_controller_province(
            ctrl_name, rec["controller_type"], taxonomy
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO stocks(
                code, name, province, city, controller_type, controller_name, controller_province,
                overseas_pct, em_industry, latest_report_date, audit_notes, manual_verified, updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
            """,
            (
                code,
                clean_stock_name(rec["name"]),
                rec["province"],
                rec.get("city") or ev.get("city_hint"),
                rec["controller_type"],
                ctrl_name,
                ctrl_prov,
                overseas,
                ev.get("em_industry") or rec.get("em_industry"),
                ev.get("latest_dt") or rec.get("latest_report_date"),
                rec.get("audit_notes") or "",
                int(rec.get("manual_verified") or 0),
            ),
        )

        for tbl in ("static_tags", "dynamic_tags", "ma_events"):
            conn.execute(f"DELETE FROM {tbl} WHERE code=?", (code,))

        for s in rec.get("static_tags", []):
            conn.execute(
                "INSERT INTO static_tags(code, l1, revenue_pct, evidence) VALUES(?,?,?,?)",
                (code, s["l1"], s.get("revenue_pct"), s["evidence"]),
            )
        for d in rec.get("dynamic_tags", []):
            conn.execute(
                "INSERT INTO dynamic_tags(code, group_name, from_date, to_date, evidence) VALUES(?,?,?,?,?)",
                (code, d["group_name"], d["from_date"], d.get("to_date"), d["evidence"]),
            )
        for m in rec.get("ma_events", []):
            conn.execute(
                """
                INSERT INTO ma_events(code, event_type, target_name, target_l1, from_date, evidence)
                VALUES(?,?,?,?,?,?)
                """,
                (
                    code,
                    m["event_type"],
                    m["target_name"],
                    m.get("target_l1") or None,
                    m["from_date"],
                    m["evidence"],
                ),
            )

    conn.commit()
    _sync_hot_news_conn(conn, HOT_NEWS_DIR)
    conn.commit()
    summary = compute_summary(conn)
    conn.close()
    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def _sync_hot_news_conn(conn: sqlite3.Connection, news_dir: Path) -> int:
    if not news_dir.exists():
        return 0
    days_imported = 0
    for p in sorted(news_dir.glob("*.json"), key=lambda path: (path.name.startswith("day_"), path.name)):
        doc = json.loads(p.read_text(encoding="utf-8"))
        days = doc.get("days") if isinstance(doc, dict) and "days" in doc else ([doc] if isinstance(doc, dict) and "trade_date" in doc else [])
        for day_obj in days:
            td = str(day_obj.get("trade_date") or "").strip()
            if not td:
                continue
            conn.execute("DELETE FROM daily_hot_news WHERE trade_date=?", (td,))
            for idx, it in enumerate(day_obj.get("items") or [], start=1):
                conn.execute(
                    "INSERT INTO daily_hot_news(trade_date, rank, headline, detail, hit_count) VALUES(?,?,?,?,?)",
                    (td, int(it.get("rank") or idx), str(it["headline"]).strip(), str(it["detail"]).strip(), int(it.get("hit_count") or 0)),
                )
            days_imported += 1
    return days_imported


def upsert_hot_news(news_dir: Path = HOT_NEWS_DIR, db_path: Path = DB_PATH) -> dict[str, Any]:
    conn = ensure_db(db_path)
    _sync_hot_news_conn(conn, news_dir)
    conn.commit()
    summary = compute_summary(conn)
    conn.close()
    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def compute_summary(conn: sqlite3.Connection) -> dict[str, Any]:
    total_stocks = conn.execute("SELECT COUNT(*) FROM stocks").fetchone()[0]
    pool_days = conn.execute("SELECT COUNT(DISTINCT trade_date), MAX(trade_date) FROM daily_limit_pool").fetchone()
    hot_news_days = conn.execute("SELECT COUNT(DISTINCT trade_date) FROM daily_hot_news").fetchone()[0]
    l1_counts = dict(conn.execute("SELECT l1, COUNT(*) FROM static_tags GROUP BY l1 ORDER BY COUNT(*) DESC").fetchall())
    dyn_groups = dict(conn.execute("SELECT group_name, COUNT(*) FROM dynamic_tags WHERE to_date IS NULL GROUP BY group_name ORDER BY COUNT(*) DESC").fetchall())
    ma_by_type = dict(conn.execute("SELECT event_type, COUNT(*) FROM ma_events GROUP BY event_type ORDER BY COUNT(*) DESC").fetchall())
    return {
        "total_stocks": total_stocks,
        "daily_pool_days": pool_days[0],
        "latest_pool_date": pool_days[1],
        "hot_news_days": hot_news_days,
        "static_l1_counts": l1_counts,
        "active_dynamic_groups": dyn_groups,
        "ongoing_ma_by_type": ma_by_type,
    }


def upsert_from_tagged(prefix: str | None = None) -> dict[str, Any]:
    records, ev_map, errors = load_tagged(prefix)
    if errors:
        raise RuntimeError(f"Validation errors: {errors[:20]}")
    return upsert_records(records, ev_map)


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd")
    p_comp = sub.add_parser("compile")
    p_comp.add_argument("--prefix", type=str, default=None)
    p_comp.add_argument("--all", action="store_true")

    p_ov = sub.add_parser("override")
    p_ov.add_argument("--code", required=True)
    p_ov.add_argument("--json-file", type=Path, required=True)

    p_news = sub.add_parser("import-news")
    p_news.add_argument("--news-dir", type=Path, default=HOT_NEWS_DIR)

    sub.add_parser("summary")

    args = parser.parse_args()
    if args.cmd == "override":
        overrides = load_overrides()
        patch = json.loads(args.json_file.read_text(encoding="utf-8"))
        overrides[args.code] = patch
        OVERRIDES_PATH.write_text(json.dumps(overrides, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        summary = upsert_from_tagged(None)
        print(json.dumps({"status": "ok", "overridden": args.code, "summary": summary}, ensure_ascii=False, indent=2))
    elif args.cmd == "import-news":
        summary = upsert_hot_news(args.news_dir)
        print(json.dumps({"status": "ok", "summary": summary}, ensure_ascii=False, indent=2))
    elif args.cmd == "summary":
        conn = ensure_db()
        print(json.dumps(compute_summary(conn), ensure_ascii=False, indent=2))
        conn.close()
    else:
        summary = upsert_from_tagged(None if getattr(args, "all", False) else getattr(args, "prefix", None))
        print(json.dumps({"status": "ok", "summary": summary}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
