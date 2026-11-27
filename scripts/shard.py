r"""Build zero-truncation byte-budgeted evidence shards purely from C:\Ai\Super-Board\data."""
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
    extract_city,
    extract_controller_province,
    extract_overseas_pct,
    infer_controller_type,
    load_taxonomy,
    normalize_province,
)

F10_DIR = ROOT / "data/raw_f10"
ANN_DIR = ROOT / "data/raw_ann"
SHARD_DIR = ROOT / "data/shards"


def _load_recent_pool(codes: list[str]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {c: [] for c in codes}
    if not DB_PATH.exists():
        return out
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    for c in codes:
        rows = conn.execute(
            """
            SELECT trade_date, board_height, kpl_topic, kpl_reason, name
            FROM daily_limit_pool
            WHERE code = ?
            ORDER BY trade_date DESC LIMIT 50
            """,
            (c,),
        ).fetchall()
        picked = []
        seen_topics: set[str] = set()
        for dt, bh, topic, reason, sname in rows:
            t = (topic or "").strip()
            if t not in seen_topics or len(picked) < 5 or dt >= "2025-11-26":
                if t not in seen_topics or len(picked) < 5:
                    seen_topics.add(t)
                    picked.append({"date": dt, "height": bh, "topic": t, "reason": reason or "", "name": sname or ""})
        out[c] = picked
    conn.close()
    return out


def build_stock_evidence(code: str, pool_rows: list[dict[str, Any]], taxonomy: dict[str, Any]) -> dict[str, Any]:
    f10_p = F10_DIR / f"{code}.json"
    ann_p = ANN_DIR / f"{code}.json"
    f10 = json.loads(f10_p.read_text(encoding="utf-8")) if f10_p.exists() else {"f10_status": "missing"}
    ann = json.loads(ann_p.read_text(encoding="utf-8")) if ann_p.exists() else {"ann_status": "missing", "notices": []}

    prov = normalize_province(f10.get("province_raw"), f10.get("reg_address"), taxonomy)
    city = extract_city(f10.get("reg_address"), prov)
    ctrl_name = f10.get("controller_name")
    ctrl_type = infer_controller_type(ctrl_name)
    ctrl_prov = extract_controller_province(ctrl_name, ctrl_type, taxonomy)

    latest_mix = f10.get("latest_mix") or {}
    annual_mix = f10.get("annual_mix") or {}
    overseas_pct = extract_overseas_pct(latest_mix.get("region"))
    if overseas_pct is None and annual_mix:
        overseas_pct = extract_overseas_pct(annual_mix.get("region"))

    NOISE_NOTICE_KWS = (
        "三方监管", "四方监管", "监管协议", "专户", "可转债", "债券", "赎回",
        "转股", "付息", "信用评级", "限售股", "解禁", "上市流通", "发行情况报告书",
        "募集说明书", "上市公告书", "网下配售", "询价转让",
    )
    notices = []
    for n in ann.get("notices", []):
        title = str(n.get("title") or "")
        if any(k in title for k in NOISE_NOTICE_KWS):
            continue
        txt = (n.get("full_text") or n.get("snippet") or "").strip()
        notices.append({"date": n.get("date"), "title": title, "text": txt})
        if len(notices) >= 5:
            break

    pool_name = next((r.get("name") for r in pool_rows if r.get("name")), None)
    return {
        "code": code,
        "name": clean_stock_name(f10.get("name") or pool_name or code),
        "f10_status": f10.get("f10_status", "missing"),
        "province_hint": prov,
        "city_hint": city,
        "controller_name": ctrl_name,
        "controller_type_hint": ctrl_type,
        "controller_province_hint": ctrl_prov,
        "overseas_pct_hint": overseas_pct,
        "em_industry": f10.get("em_industry"),
        "latest_dt": f10.get("latest_dt"),
        "latest_mix": latest_mix,
        "annual_dt": f10.get("annual_dt"),
        "annual_mix": annual_mix,
        "business_scope": f10.get("business_scope") or "",
        "business_review": f10.get("business_review") or "",
        "core_conception": f10.get("core_conception") or [],
        "key_notices": notices,
        "recent_limit_ups": pool_rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--codes", nargs="*", default=None)
    parser.add_argument("--codes-file", type=Path, default=None)
    parser.add_argument("--date", type=str, default=None)
    parser.add_argument("--month", type=str, default=None)
    parser.add_argument("--prefix", type=str, required=True)
    parser.add_argument("--shard-size", type=int, default=10)
    parser.add_argument("--max-shard-bytes", type=int, default=320000)
    args = parser.parse_args()

    SHARD_DIR.mkdir(parents=True, exist_ok=True)
    taxonomy = load_taxonomy()

    if args.codes_file:
        target_codes = [str(c) for c in json.loads(args.codes_file.read_text(encoding="utf-8"))]
    elif args.date or args.month:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        if args.date:
            rows = conn.execute("SELECT DISTINCT code FROM daily_limit_pool WHERE trade_date=? ORDER BY code", (args.date,)).fetchall()
        else:
            rows = conn.execute("SELECT DISTINCT code FROM daily_limit_pool WHERE trade_date LIKE ? AND board_height >= 2 ORDER BY code", (f"{args.month}-%",)).fetchall()
        conn.close()
        target_codes = [r[0] for r in rows]
    else:
        target_codes = list(args.codes or [])

    pool_map = _load_recent_pool(target_codes)

    def write_shard(sid: str, items: list[dict[str, Any]]) -> int:
        payload = {"shard_id": sid, "prefix": args.prefix, "count": len(items), "stocks": items}
        (SHARD_DIR / f"{sid}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return len(json.dumps(items, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))

    manifest: dict[str, Any] = {"prefix": args.prefix, "total_stocks": len(target_codes), "shards": []}
    cur: list[dict[str, Any]] = []
    cur_bytes = 2
    idx = 1
    for code in target_codes:
        item = build_stock_evidence(code, pool_map.get(code, []), taxonomy)
        ib = len(json.dumps(item, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) + 1
        if cur and (len(cur) >= args.shard_size or (args.max_shard_bytes > 0 and cur_bytes + ib > args.max_shard_bytes)):
            sid = f"{args.prefix}_shard_{idx:03d}"
            b = write_shard(sid, cur)
            manifest["shards"].append({"shard_id": sid, "count": len(cur), "compact_bytes": b})
            idx += 1
            cur = []
            cur_bytes = 2
        cur.append(item)
        cur_bytes += ib
    if cur:
        sid = f"{args.prefix}_shard_{idx:03d}"
        b = write_shard(sid, cur)
        manifest["shards"].append({"shard_id": sid, "count": len(cur), "compact_bytes": b})

    (SHARD_DIR / f"{args.prefix}_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"prefix": args.prefix, "shards": len(manifest["shards"]), "stocks": len(target_codes), "max_compact_bytes": max((s["compact_bytes"] for s in manifest["shards"]), default=0)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
