"""Pure-stdlib SQLite builder & manual override merger for Super-Board (v2 full-dynamic)."""
from __future__ import annotations

import argparse
import json
import sqlite3
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
from driver_rules import candidates, is_core_stock, is_event_theme

SHARD_DIR = ROOT / "data/shards"
TAGGED_DIR = ROOT / "data/tagged"
AUDIT_OUT_DIR = ROOT / "data/audit_out"
HOT_NEWS_DIR = ROOT / "data/hot_news"
DRIVERS_DIR = ROOT / "data/drivers"
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

CREATE TABLE IF NOT EXISTS stock_tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL,
    tag TEXT NOT NULL,
    from_date TEXT NOT NULL,
    evidence TEXT NOT NULL,
    UNIQUE(code, tag),
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
    theme TEXT,
    codes TEXT,
    UNIQUE(trade_date, rank)
);

CREATE TABLE IF NOT EXISTS daily_stock_driver (
    trade_date TEXT NOT NULL,
    code TEXT NOT NULL,
    driver TEXT,
    driver2 TEXT,
    basis_type TEXT,
    basis TEXT,
    source TEXT NOT NULL,
    PRIMARY KEY (trade_date, code)
);

CREATE INDEX IF NOT EXISTS idx_stock_tags_tag ON stock_tags(tag);
CREATE INDEX IF NOT EXISTS idx_stock_tags_code ON stock_tags(code);
CREATE INDEX IF NOT EXISTS idx_ma_code ON ma_events(code);
CREATE INDEX IF NOT EXISTS idx_ma_target_l1 ON ma_events(target_l1);
CREATE INDEX IF NOT EXISTS idx_pool_code ON daily_limit_pool(code);
CREATE INDEX IF NOT EXISTS idx_hot_news_date ON daily_hot_news(trade_date);
CREATE INDEX IF NOT EXISTS idx_driver_date ON daily_stock_driver(trade_date);
"""


def ensure_db(db_path: Path = DB_PATH, drop_legacy: bool = False) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("DROP TABLE IF EXISTS exclusions")
    if drop_legacy:
        conn.execute("DROP TABLE IF EXISTS static_tags")
        conn.execute("DROP TABLE IF EXISTS dynamic_tags")
    ma_cols = {r[1] for r in conn.execute("PRAGMA table_info(ma_events)").fetchall()}
    if "status" in ma_cols:
        conn.execute("DROP TABLE ma_events")
    conn.executescript(SCHEMA_SQL)
    news_cols = {r[1] for r in conn.execute("PRAGMA table_info(daily_hot_news)").fetchall()}
    if "theme" not in news_cols:
        conn.execute("ALTER TABLE daily_hot_news ADD COLUMN theme TEXT")
    if "codes" not in news_cols:
        conn.execute("ALTER TABLE daily_hot_news ADD COLUMN codes TEXT")
    conn.commit()
    return conn


def load_overrides() -> dict[str, dict[str, Any]]:
    if not OVERRIDES_PATH.exists():
        return {}
    raw = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
    return {k: v for k, v in raw.items() if not str(k).startswith("__")}


def load_driver_overrides() -> dict[str, dict[str, str]]:
    if not OVERRIDES_PATH.exists():
        return {}
    raw = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
    drv_ov = raw.get("__drivers__")
    return dict(drv_ov) if isinstance(drv_ov, dict) else {}


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


def _write_stock_tags(conn: sqlite3.Connection, code: str, tags: list[dict[str, Any]]) -> None:
    conn.execute("DELETE FROM stock_tags WHERE code=?", (code,))
    seen: set[str] = set()
    for t in tags:
        tname = str(t["tag"]).strip()
        if not tname or tname in seen:
            continue
        seen.add(tname)
        conn.execute(
            "INSERT INTO stock_tags(code, tag, from_date, evidence) VALUES(?,?,?,?)",
            (code, tname, str(t["from_date"]).strip(), str(t["evidence"]).strip()),
        )


def upsert_records(
    records: dict[str, dict[str, Any]],
    ev_map: dict[str, dict[str, Any]],
    db_path: Path = DB_PATH,
    drop_legacy: bool = True,
) -> dict[str, Any]:
    taxonomy = load_taxonomy()
    conn = ensure_db(db_path, drop_legacy=drop_legacy)

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

        _write_stock_tags(conn, code, rec.get("tags", []))

        if "ma_events" in rec:
            conn.execute("DELETE FROM ma_events WHERE code=?", (code,))
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


def apply_overrides_to_db(db_path: Path = DB_PATH) -> dict[str, Any]:
    """Overlay manual_overrides.json directly onto super_board.sqlite (works without data/tagged/)."""
    taxonomy = load_taxonomy()
    overrides = load_overrides()
    conn = ensure_db(db_path)
    conn.row_factory = sqlite3.Row

    for code, patch in overrides.items():
        row = conn.execute("SELECT * FROM stocks WHERE code=?", (code,)).fetchone()
        if not row:
            if not (patch.get("name") and patch.get("province") and patch.get("controller_type")):
                continue
            rec = {
                "code": code,
                "name": patch["name"],
                "province": patch["province"],
                "city": patch.get("city"),
                "controller_type": patch["controller_type"],
                "controller_name": patch.get("controller_name"),
                "controller_province": patch.get("controller_province"),
                "overseas_pct": patch.get("overseas_pct"),
                "em_industry": patch.get("em_industry"),
                "latest_report_date": patch.get("latest_report_date"),
                "audit_notes": patch.get("audit_notes") or "",
                "tags": [],
                "ma_events": [],
            }
            merged = apply_override(rec, patch)
            errs = validate_record(merged, None, taxonomy)
            if errs:
                conn.close()
                raise RuntimeError(f"Manual override validation failed for new stock {code}: {errs}")
            ctrl_prov = merged.get("controller_province") or extract_controller_province(
                merged.get("controller_name"), merged["controller_type"], taxonomy
            )
            conn.execute(
                """
                INSERT INTO stocks(
                    code, name, province, city, controller_type, controller_name, controller_province,
                    overseas_pct, em_industry, latest_report_date, audit_notes, manual_verified, updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,1,CURRENT_TIMESTAMP)
                """,
                (
                    code,
                    clean_stock_name(merged["name"]),
                    merged["province"],
                    merged.get("city"),
                    merged["controller_type"],
                    merged.get("controller_name"),
                    ctrl_prov,
                    merged.get("overseas_pct"),
                    merged.get("em_industry"),
                    merged.get("latest_report_date"),
                    merged.get("audit_notes") or "",
                ),
            )
            _write_stock_tags(conn, code, merged.get("tags", []))
            conn.execute("DELETE FROM ma_events WHERE code=?", (code,))
            for m in merged.get("ma_events", []):
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
            continue
        rec = dict(row)
        cur_tags = [
            {"tag": r["tag"], "from_date": r["from_date"], "evidence": r["evidence"]}
            for r in conn.execute("SELECT tag, from_date, evidence FROM stock_tags WHERE code=? ORDER BY id ASC", (code,))
        ]
        cur_ma = [
            {
                "event_type": r["event_type"],
                "target_name": r["target_name"],
                "target_l1": r["target_l1"],
                "from_date": r["from_date"],
                "evidence": r["evidence"],
            }
            for r in conn.execute("SELECT * FROM ma_events WHERE code=? ORDER BY from_date DESC, id ASC", (code,))
        ]
        rec["tags"] = cur_tags
        rec["ma_events"] = cur_ma
        merged = apply_override(rec, patch)
        errs = validate_record(merged, None, taxonomy)
        if errs:
            conn.close()
            raise RuntimeError(f"Manual override validation failed for {code}: {errs}")

        ctrl_prov = merged.get("controller_province") or extract_controller_province(
            merged.get("controller_name"), merged["controller_type"], taxonomy
        )
        conn.execute(
            """
            UPDATE stocks
            SET name=?, province=?, city=?, controller_type=?, controller_name=?, controller_province=?,
                overseas_pct=?, em_industry=?, latest_report_date=?, audit_notes=?, manual_verified=1,
                updated_at=CURRENT_TIMESTAMP
            WHERE code=?
            """,
            (
                clean_stock_name(merged["name"]),
                merged["province"],
                merged.get("city"),
                merged["controller_type"],
                merged.get("controller_name"),
                ctrl_prov,
                merged.get("overseas_pct"),
                merged.get("em_industry"),
                merged.get("latest_report_date"),
                merged.get("audit_notes") or "",
                code,
            ),
        )
        _write_stock_tags(conn, code, merged.get("tags", []))
        if "ma_events" in patch:
            conn.execute("DELETE FROM ma_events WHERE code=?", (code,))
            for m in merged.get("ma_events", []):
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
    summary = compute_summary(conn)
    conn.close()
    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def import_audit_shards(prefix: str, db_path: Path = DB_PATH, drop_legacy: bool = True) -> dict[str, Any]:
    """Merge validated full-dynamic audit shards from data/audit_out into super_board.sqlite."""
    taxonomy = load_taxonomy()
    conn = ensure_db(db_path, drop_legacy=drop_legacy)
    conn.row_factory = sqlite3.Row

    files = sorted(AUDIT_OUT_DIR.glob(f"{prefix}_shard_*.json"))
    if not files:
        conn.close()
        raise RuntimeError(f"No audit shards found matching {AUDIT_OUT_DIR / (prefix + '_shard_*.json')}")

    updated = 0
    errors: list[str] = []
    batch: list[dict[str, Any]] = []
    for p in files:
        doc = json.loads(p.read_text(encoding="utf-8"))
        for rec in doc.get("stocks", []):
            check = dict(rec)
            check.setdefault("ma_events", [])
            errs = validate_record(check, None, taxonomy)
            if errs:
                errors.extend(f"{p.name}: {e}" for e in errs)
            else:
                batch.append(rec)
    if errors:
        conn.close()
        raise RuntimeError(f"Audit validation errors ({len(errors)}): {errors[:20]}")

    for rec in batch:
        code = str(rec["code"])
        existing = conn.execute("SELECT * FROM stocks WHERE code=?", (code,)).fetchone()
        if existing and int(existing["manual_verified"] or 0) == 1:
            continue
        if existing:
            conn.execute(
                """
                UPDATE stocks
                SET name=?, province=?, controller_type=?, audit_notes=?, updated_at=CURRENT_TIMESTAMP
                WHERE code=?
                """,
                (
                    clean_stock_name(rec["name"]),
                    rec["province"],
                    rec["controller_type"],
                    rec.get("audit_notes") or "",
                    code,
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO stocks(code, name, province, controller_type, audit_notes, manual_verified, updated_at)
                VALUES(?,?,?,?,?,0,CURRENT_TIMESTAMP)
                """,
                (
                    code,
                    clean_stock_name(rec["name"]),
                    rec["province"],
                    rec["controller_type"],
                    rec.get("audit_notes") or "",
                ),
            )
        _write_stock_tags(conn, code, rec.get("tags", []))
        updated += 1

    conn.commit()
    conn.close()
    summary = apply_overrides_to_db(db_path)
    summary["audit_updated"] = updated
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
                theme = str(it["theme"]).strip() if it.get("theme") else None
                codes_val = it.get("codes")
                codes_json = json.dumps([str(c) for c in codes_val], ensure_ascii=False) if isinstance(codes_val, list) else None
                conn.execute(
                    "INSERT INTO daily_hot_news(trade_date, rank, headline, detail, hit_count, theme, codes) VALUES(?,?,?,?,?,?,?)",
                    (td, int(it.get("rank") or idx), str(it["headline"]).strip(), str(it["detail"]).strip(), int(it.get("hit_count") or 0), theme, codes_json),
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


def import_drivers(drivers_dir: Path = DRIVERS_DIR, db_path: Path = DB_PATH) -> dict[str, Any]:
    """Import per-stock daily driver attributions in ascending date order with hysteresis & manual overrides."""
    conn = ensure_db(db_path)
    driver_overrides = load_driver_overrides()
    docs_by_date: dict[str, list[dict[str, Any]]] = {}
    if drivers_dir.exists():
        for p in sorted(drivers_dir.glob("*.json")):
            if p.name.startswith("_"):
                continue
            doc = json.loads(p.read_text(encoding="utf-8"))
            td = str(doc.get("trade_date") or "").strip()
            if td:
                docs_by_date[td] = list(doc.get("stocks") or [])

    total_rows = 0
    hysteresis_cnt = 0
    manual_cnt = 0
    for td in sorted(docs_by_date.keys()):
        conn.execute("DELETE FROM daily_stock_driver WHERE trade_date=?", (td,))
        prev_dates = [
            r[0]
            for r in conn.execute(
                "SELECT DISTINCT trade_date FROM daily_limit_pool WHERE trade_date < ? ORDER BY trade_date DESC LIMIT 5",
                (td,),
            ).fetchall()
        ]
        prev_drivers: dict[str, str] = {}
        for pd in reversed(prev_dates):
            for c_prev, d_prev in conn.execute(
                "SELECT code, driver FROM daily_stock_driver WHERE trade_date=? AND driver IS NOT NULL",
                (pd,),
            ).fetchall():
                prev_drivers[c_prev] = d_prev

        pool_info = {
            r[0]: (int(r[1] or 1), int(r[2] or 0), r[3] or "")
            for r in conn.execute(
                "SELECT code, board_height, is_fanbao, boards_desc FROM daily_limit_pool WHERE trade_date=?",
                (td,),
            ).fetchall()
        }
        news_themes = {
            str(r[0]).strip()
            for r in conn.execute(
                "SELECT theme FROM daily_hot_news WHERE trade_date=? AND theme IS NOT NULL",
                (td,),
            ).fetchall()
            if str(r[0] or "").strip()
        }

        # Count raw core drivers on td so hysteresis knows which prior themes are still alive today
        today_drv_cnt: dict[str, int] = {}
        for st in docs_by_date[td]:
            d0 = str(st.get("driver") or "").strip()
            if d0:
                today_drv_cnt[d0] = today_drv_cnt.get(d0, 0) + 1

        day_map: dict[str, tuple[str | None, str | None, str | None, str, str]] = {}
        for st in docs_by_date[td]:
            code = str(st.get("code") or "").strip()
            if not code:
                continue
            drv = str(st["driver"]).strip() if st.get("driver") else None
            drv2 = str(st["driver2"]).strip() if st.get("driver2") else None
            btype = str(st["basis_type"]).strip() if st.get("basis_type") else None
            basis = str(st.get("basis") or "").strip()
            src = str(st.get("source") or "llm").strip()

            bh, fb, bdesc = pool_info.get(code, (1, 0, ""))
            if is_core_stock(bh, fb, bdesc):
                prev_p = prev_drivers.get(code)
                if prev_p and drv != prev_p and btype != "announcement":
                    cands = candidates(conn, code, td)
                    prev_valid = prev_p in cands or is_event_theme(prev_p)
                    prev_still_alive = (
                        btype not in ("news", "announcement")
                        or drv2 == prev_p
                        or prev_p in news_themes
                        or today_drv_cnt.get(prev_p, 0) >= 2
                    )
                    if prev_valid and prev_still_alive:
                        if drv and drv != prev_p:
                            drv2 = drv
                        drv = prev_p
                        src = "hysteresis"
                        hysteresis_cnt += 1

            if drv2 == drv:
                drv2 = None
            day_map[code] = (drv, drv2, btype, basis, src)

        for ov_code, ov_drv in (driver_overrides.get(td) or {}).items():
            ov_code_s = str(ov_code).strip()
            ov_drv_s = str(ov_drv).strip()
            if ov_code_s and ov_drv_s:
                prev_entry = day_map.get(ov_code_s)
                old_drv2 = prev_entry[1] if prev_entry else None
                old_btype = prev_entry[2] if prev_entry else "manual"
                old_basis = prev_entry[3] if prev_entry else "人工指定"
                if old_drv2 == ov_drv_s:
                    old_drv2 = None
                day_map[ov_code_s] = (ov_drv_s, old_drv2, old_btype, old_basis, "manual")
                manual_cnt += 1

        for code, (drv, drv2, btype, basis, src) in sorted(day_map.items()):
            conn.execute(
                """
                INSERT INTO daily_stock_driver(trade_date, code, driver, driver2, basis_type, basis, source)
                VALUES(?,?,?,?,?,?,?)
                """,
                (td, code, drv, drv2, btype, basis, src),
            )
            total_rows += 1

    conn.commit()
    summary = compute_summary(conn)
    summary["driver_days_imported"] = len(docs_by_date)
    summary["driver_rows_imported"] = total_rows
    summary["hysteresis_applied"] = hysteresis_cnt
    summary["manual_driver_overrides"] = manual_cnt
    conn.close()
    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def compute_summary(conn: sqlite3.Connection) -> dict[str, Any]:
    total_stocks = conn.execute("SELECT COUNT(*) FROM stocks").fetchone()[0]
    pool_days = conn.execute("SELECT COUNT(DISTINCT trade_date), MAX(trade_date) FROM daily_limit_pool").fetchone()
    hot_news_days = conn.execute("SELECT COUNT(DISTINCT trade_date) FROM daily_hot_news").fetchone()[0]
    tag_counts = dict(conn.execute("SELECT tag, COUNT(*) FROM stock_tags GROUP BY tag ORDER BY COUNT(*) DESC").fetchall())
    total_tag_rows = conn.execute("SELECT COUNT(*) FROM stock_tags").fetchone()[0]
    ma_by_type = dict(conn.execute("SELECT event_type, COUNT(*) FROM ma_events GROUP BY event_type ORDER BY COUNT(*) DESC").fetchall())
    return {
        "schema_version": "v2_full_dynamic",
        "total_stocks": total_stocks,
        "total_tag_assignments": total_tag_rows,
        "avg_tags_per_stock": round(total_tag_rows / total_stocks, 2) if total_stocks else 0.0,
        "daily_pool_days": pool_days[0],
        "latest_pool_date": pool_days[1],
        "hot_news_days": hot_news_days,
        "tag_counts": tag_counts,
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

    p_aud = sub.add_parser("import-audit")
    p_aud.add_argument("--prefix", required=True)

    p_ov = sub.add_parser("override")
    p_ov.add_argument("--code", required=True)
    p_ov.add_argument("--json-file", type=Path, required=True)

    sub.add_parser("apply-overrides")

    p_news = sub.add_parser("import-news")
    p_news.add_argument("--news-dir", type=Path, default=HOT_NEWS_DIR)

    p_drv = sub.add_parser("import-drivers")
    p_drv.add_argument("--drivers-dir", type=Path, default=DRIVERS_DIR)

    sub.add_parser("summary")

    args = parser.parse_args()
    if args.cmd == "override":
        overrides = load_overrides()
        patch = json.loads(args.json_file.read_text(encoding="utf-8"))
        overrides[args.code] = patch
        OVERRIDES_PATH.write_text(json.dumps(overrides, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        summary = apply_overrides_to_db()
        print(json.dumps({"status": "ok", "overridden": args.code, "summary": summary}, ensure_ascii=False, indent=2))
    elif args.cmd == "apply-overrides":
        summary = apply_overrides_to_db()
        print(json.dumps({"status": "ok", "summary": summary}, ensure_ascii=False, indent=2))
    elif args.cmd == "import-audit":
        summary = import_audit_shards(args.prefix)
        print(json.dumps({"status": "ok", "summary": summary}, ensure_ascii=False, indent=2))
    elif args.cmd == "import-news":
        summary = upsert_hot_news(args.news_dir)
        print(json.dumps({"status": "ok", "summary": summary}, ensure_ascii=False, indent=2))
    elif args.cmd == "import-drivers":
        summary = import_drivers(args.drivers_dir)
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
