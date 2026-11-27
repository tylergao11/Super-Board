"""Lightweight stdlib HTTP server & JSON serializer for Super-Board Mobile Web UI."""
from __future__ import annotations

import argparse
import json
import mimetypes
import re
import socket
import sqlite3
import urllib.request
from collections import defaultdict
from datetime import date as dt_date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from driver_rules import VOCAB_SET, fanbao_board_count, is_core_stock, is_fanbao_stock, main_business, rule_driver

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data/super_board.sqlite"
WEB_DIR = ROOT / "web"
ULTRA_BOARD_RAW = Path(r"C:\Ai\Ultra-Board\data\kaipanla\raw")
MOOD_CACHE_PATH = ROOT / "data/market_mood_cache.json"
KLINE_DIR = ROOT / "data/raw_kline"
_MOOD_CACHE: dict[str, dict[str, Any]] | None = None
_DAY_DISPLAY_CACHE: dict[str, dict[str, list[str]]] = {}
_KLINE_CACHE: dict[str, tuple[list[str], list[float], dict[str, int]]] = {}
_N_DAY_RE = re.compile(r"(\d+)天(\d+)板")

THEME_ACCENTS: dict[str, str] = {
    "商业航天": "coral",
    "AI应用": "amber",
    "机器人": "cyan",
    "算力": "blue",
    "芯片": "indigo",
    "海洋经济": "teal",
    "消费": "rose",
    "并购": "violet",
    "通信": "violet",
    "华为链": "sky",
    "国产替代/信创": "sky",
    "军工": "emerald",
    "化工": "ochre",
    "医药": "mint",
    "电力": "lime",
    "有色": "amber",
    "锂电": "teal",
    "光伏": "ochre",
    "汽车": "cyan",
    "工业设备": "slate",
    "消费电子": "indigo",
    "传媒": "rose",
    "低空经济": "coral",
    "氢能源": "emerald",
    "可控核聚变": "violet",
    "海峡两岸": "coral",
}

NEWS_EVENT_SHORT_TITLES: list[tuple[str, str, str]] = [
    ("“金”字", "金字辈", "amber"),
    ("金字辈", "金字辈", "amber"),
    ("字辈", "字辈暗线", "amber"),
    ("羊年", "羊年暗线", "amber"),
    ("生肖", "生肖暗线", "amber"),
    ("并购", "并购", "violet"),
    ("股权转让", "并购", "violet"),
    ("要约", "并购", "violet"),
    ("SpaceX", "商业航天", "coral"),
    ("卫星", "商业航天", "coral"),
    ("航天", "商业航天", "coral"),
    ("神舟", "商业航天", "coral"),
    ("舰载机", "商业航天", "coral"),
    ("航展", "军工", "emerald"),
    ("宇树", "机器人", "cyan"),
    ("具身", "机器人", "cyan"),
    ("机器人", "机器人", "cyan"),
    ("PCB", "通信", "violet"),
    ("覆铜板", "通信", "violet"),
    ("电子铜箔", "通信", "violet"),
    ("大模型", "AI应用", "amber"),
    ("云计算", "AI应用", "amber"),
    ("HBM", "芯片", "indigo"),
    ("封装", "芯片", "indigo"),
    ("存储", "芯片", "indigo"),
    ("光刻", "芯片", "indigo"),
    ("芯片", "芯片", "indigo"),
    ("算力", "算力", "blue"),
    ("华为", "华为链", "sky"),
    ("海洋", "海洋经济", "teal"),
    ("冰雪", "消费", "rose"),
    ("灵顺寺", "消费", "rose"),
    ("零售", "消费", "rose"),
    ("平准", "平准稳市", "coral"),
    ("稳市", "平准稳市", "coral"),
    ("回购", "回购催化", "amber"),
    ("关税", "贸易催化", "ochre"),
    ("301", "贸易催化", "ochre"),
    ("摘帽", "摘帽复牌", "mint"),
    ("ST", "摘帽复牌", "mint"),
]

PROVINCE_SHORT = {
    "北京市": "北京",
    "天津市": "天津",
    "上海市": "上海",
    "重庆市": "重庆",
    "内蒙古自治区": "内蒙古",
    "广西壮族自治区": "广西",
    "西藏自治区": "西藏",
    "宁夏回族自治区": "宁夏",
    "新疆维吾尔自治区": "新疆",
}


def _short_prov(prov: str | None) -> str:
    if not prov:
        return ""
    if prov in PROVINCE_SHORT:
        return PROVINCE_SHORT[prov]
    return prov.replace("省", "").replace("市", "")


def _clean_text(text: str | None) -> str:
    if not text:
        return ""
    s = re.sub(r"\s+", " ", str(text)).strip()
    return s


def _accent_for(theme: str) -> str:
    return THEME_ACCENTS.get(theme, "slate")


def _load_kline(code: str) -> tuple[list[str], list[float], dict[str, int]] | None:
    if code in _KLINE_CACHE:
        return _KLINE_CACHE[code]
    p = KLINE_DIR / f"{code}.json"
    if not p.exists():
        return None
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
        days = doc.get("days") or []
        dates = [str(d[0]) for d in days]
        closes = [float(d[1]) for d in days]
        idx_map = {dt: i for i, dt in enumerate(dates)}
        val = (dates, closes, idx_map)
        _KLINE_CACHE[code] = val
        return val
    except Exception:
        return None


def _compute_fanbao_gain_pct(
    conn: sqlite3.Connection, code: str, date: str, boards_desc: str | None
) -> float | None:
    """Compute cumulative % gain from pre-first-board close to trade_date close for a fanbao stock."""
    kl = _load_kline(code)
    if not kl:
        return None
    dates, closes, idx_map = kl
    cur_idx = idx_map.get(date)
    if cur_idx is None or cur_idx <= 0:
        return None

    m = _N_DAY_RE.search(str(boards_desc or ""))
    base_idx: int | None = None
    if m:
        n_days = int(m.group(1))
        if cur_idx - n_days >= 0:
            base_idx = cur_idx - n_days
    if base_idx is None:
        # Walk backwards across recent limit-up dates (gap <= 3 trading days) to find wave's first board
        lu_dates = [
            r[0]
            for r in conn.execute(
                "SELECT trade_date FROM daily_limit_pool WHERE code = ? AND trade_date < ? ORDER BY trade_date DESC LIMIT 12",
                (code, date),
            ).fetchall()
        ]
        wave_start_idx = cur_idx
        for ld in lu_dates:
            li = idx_map.get(ld)
            if li is not None and wave_start_idx - li <= 3:
                wave_start_idx = li
            else:
                break
        if wave_start_idx - 1 >= 0:
            base_idx = wave_start_idx - 1

    if base_idx is None or closes[base_idx] <= 0:
        return None
    return round((closes[cur_idx] / closes[base_idx] - 1.0) * 100.0, 1)


def _load_mood_cache() -> dict[str, dict[str, Any]]:
    global _MOOD_CACHE
    if _MOOD_CACHE is not None:
        return _MOOD_CACHE
    if MOOD_CACHE_PATH.exists():
        try:
            _MOOD_CACHE = json.loads(MOOD_CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            _MOOD_CACHE = {}
    else:
        _MOOD_CACHE = {}
    return _MOOD_CACHE


def _save_mood_cache() -> None:
    if _MOOD_CACHE is None:
        return
    try:
        MOOD_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        MOOD_CACHE_PATH.write_text(
            json.dumps(_MOOD_CACHE, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except Exception:
        pass


def _get_day_mood(date: str, zt_count: int, fetch_remote: bool = True) -> dict[str, Any]:
    cache = _load_mood_cache()
    entry = dict(cache.get(date) or {})
    changed = False

    # Read-only lookup of local sentiment.json (never writes to Ultra-Board)
    if "sign" not in entry:
        for base in (ROOT / "data/market_raw", ULTRA_BOARD_RAW):
            sp = base / date / "sentiment.json"
            if sp.exists():
                try:
                    info = json.loads(sp.read_text(encoding="utf-8")).get("info") or {}
                    entry["sign"] = str(info.get("sign") or "")
                    entry["dt_count"] = int(info.get("SJDT") or info.get("DT") or 0)
                    entry["up_count"] = int(info.get("SZJS") or 0)
                    entry["down_count"] = int(info.get("XDJS") or 0)
                    changed = True
                    break
                except Exception:
                    pass

    # Fetch exact zhaban count from EastMoney ZBPool once and cache locally
    if "zb_count" not in entry and fetch_remote and date and len(date) == 10:
        dt_compact = date.replace("-", "")
        url = (
            "https://push2ex.eastmoney.com/getTopicZBPool"
            "?ut=7eea3edcaed734bea9cbfc24409ed989&dpt=wz.ztzt"
            f"&Pageindex=0&pagesize=1&sort=fbt%3Aasc&date={dt_compact}"
        )
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=3.5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                tc = (data.get("data") or {}).get("tc")
                if tc is not None and int(tc) > 0:
                    entry["zb_count"] = int(tc)
                    changed = True
        except Exception:
            pass

    if changed:
        cache[date] = entry
        _save_mood_cache()

    zb = entry.get("zb_count")
    zb_rate = None
    if zb is not None and int(zb) > 0 and (zt_count + zb) > 0:
        zb_rate = round(zb * 100.0 / (zt_count + zb), 1)

    return {
        "zb_count": zb,
        "zhaban_rate": zb_rate,
        "dt_count": entry.get("dt_count"),
        "up_count": entry.get("up_count"),
        "down_count": entry.get("down_count"),
        "sign": entry.get("sign") or "",
    }


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def get_available_dates(limit: int = 250) -> list[dict[str, Any]]:
    conn = _conn()
    try:
        news_counts = {
            r["trade_date"]: r["cnt"]
            for r in conn.execute(
                "SELECT trade_date, COUNT(*) AS cnt FROM daily_hot_news GROUP BY trade_date"
            ).fetchall()
        }
        rows = conn.execute(
            """
            SELECT
                d.trade_date,
                COUNT(*) AS total,
                SUM(CASE WHEN d.board_height >= 2 THEN 1 ELSE 0 END) AS multi,
                SUM(CASE WHEN d.is_one_word = 1 THEN 1 ELSE 0 END) AS one_word,
                MAX(d.board_height) AS max_height,
                SUM(CASE WHEN EXISTS(SELECT 1 FROM stocks s WHERE s.code = d.code) THEN 1 ELSE 0 END) AS tagged
            FROM daily_limit_pool d
            GROUP BY d.trade_date
            ORDER BY d.trade_date DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        out = []
        for r in rows:
            td = r["trade_date"]
            tot = int(r["total"] or 0)
            mood = _get_day_mood(td, tot, fetch_remote=False)
            out.append(
                {
                    "date": td,
                    "total": tot,
                    "multi": int(r["multi"] or 0),
                    "one_word": int(r["one_word"] or 0),
                    "max_height": int(r["max_height"] or 1),
                    "zhaban_rate": mood["zhaban_rate"],
                    "tagged": int(r["tagged"] or 0),
                    "news_count": int(news_counts.get(td, 0)),
                }
            )
        return out
    finally:
        conn.close()


def get_day_payload(date: str | None = None, _depth: int = 0) -> dict[str, Any]:
    conn = _conn()
    try:
        if not date:
            row = conn.execute(
                """
                SELECT trade_date FROM daily_hot_news
                ORDER BY trade_date DESC LIMIT 1
                """
            ).fetchone()
            if not row:
                row = conn.execute(
                    "SELECT MAX(trade_date) AS trade_date FROM daily_limit_pool"
                ).fetchone()
            date = row["trade_date"] if row else ""

        prev_dates = [
            r["trade_date"]
            for r in conn.execute(
                "SELECT DISTINCT trade_date FROM daily_limit_pool WHERE trade_date < ? ORDER BY trade_date DESC LIMIT 5",
                (date,),
            ).fetchall()
        ]
        prev_date = prev_dates[0] if prev_dates else None

        pool_rows = conn.execute(
            """
            SELECT trade_date, code, name, board_height, boards_desc,
                   first_limit_time, amount_yi, turnover_rate, is_one_word, is_fanbao
            FROM daily_limit_pool
            WHERE trade_date = ?
            ORDER BY board_height DESC, is_one_word DESC, first_limit_time ASC, amount_yi DESC, code ASC
            """,
            (date,),
        ).fetchall()

        total_zt = len(pool_rows)
        core_rows = [
            r
            for r in pool_rows
            if is_core_stock(r["board_height"], r["is_fanbao"], r["boards_desc"])
        ]
        codes = [r["code"] for r in core_rows]
        if not codes:
            mood = _get_day_mood(date, total_zt, fetch_remote=True)
            return {
                "date": date,
                "summary": {
                    "total": total_zt,
                    "core": 0,
                    "multi": 0,
                    "fanbao": 0,
                    "first": 0,
                    "one_word": 0,
                    "max_height": 1 if total_zt else 0,
                    "zb_count": mood["zb_count"],
                    "zhaban_rate": mood["zhaban_rate"],
                    "dt_count": mood["dt_count"],
                    "sign": mood["sign"],
                },
                "catalysts": [],
                "ladder": [],
                "fanbao_boards": [],
                "first_boards": [],
                "stocks": {},
                "themes": {},
            }

        placeholders = ",".join("?" * len(codes))
        stock_meta = {
            r["code"]: dict(r)
            for r in conn.execute(
                f"SELECT * FROM stocks WHERE code IN ({placeholders})", codes
            ).fetchall()
        }

        cutoff_dt = ""
        if date and len(date) >= 10:
            try:
                from datetime import timedelta as _td
                cutoff_dt = (dt_date.fromisoformat(date[:10]) - _td(days=365)).isoformat()
            except Exception:
                cutoff_dt = ""

        tags_by_code: dict[str, list[dict[str, Any]]] = defaultdict(list)
        if cutoff_dt:
            tag_rows = conn.execute(
                f"""
                SELECT code, tag, from_date, evidence
                FROM stock_tags
                WHERE code IN ({placeholders}) AND from_date >= ?
                ORDER BY id ASC
                """,
                [*codes, cutoff_dt],
            ).fetchall()
        else:
            tag_rows = conn.execute(
                f"""
                SELECT code, tag, from_date, evidence
                FROM stock_tags
                WHERE code IN ({placeholders})
                ORDER BY id ASC
                """,
                codes,
            ).fetchall()
        for r in tag_rows:
            tags_by_code[r["code"]].append(dict(r))

        ma_by_code: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for r in conn.execute(
            f"""
            SELECT code, event_type, target_name, target_l1, from_date, evidence
            FROM ma_events
            WHERE code IN ({placeholders})
            ORDER BY from_date DESC, id ASC
            """,
            codes,
        ).fetchall():
            ma_by_code[r["code"]].append(dict(r))

        news_rows = [
            dict(r)
            for r in conn.execute(
                """
                SELECT rank, headline, detail, hit_count, theme, codes
                FROM daily_hot_news
                WHERE trade_date = ?
                ORDER BY rank ASC
                """,
                (date,),
            ).fetchall()
        ]

        driver_rows = {
            r["code"]: dict(r)
            for r in conn.execute(
                """
                SELECT code, driver, driver2, basis_type, basis, source
                FROM daily_stock_driver
                WHERE trade_date = ?
                """,
                (date,),
            ).fetchall()
        }

        prev_driver_map: dict[str, str] = {}
        for pd in reversed(prev_dates):
            for r in conn.execute(
                "SELECT code, driver FROM daily_stock_driver WHERE trade_date = ? AND driver IS NOT NULL",
                (pd,),
            ).fetchall():
                prev_driver_map[r["code"]] = r["driver"]

        # Pass 1: build unified full-dynamic pure themes per core stock (连板+反包) + driver-weighted sector stats
        raw_stocks: dict[str, dict[str, Any]] = {}
        theme_members: dict[str, list[str]] = defaultdict(list)
        theme_drivers: dict[str, list[str]] = defaultdict(list)
        theme_multi: dict[str, int] = defaultdict(int)
        theme_core_multi: dict[str, float] = defaultdict(float)
        theme_core_total: dict[str, float] = defaultdict(float)
        theme_one_word: dict[str, int] = defaultdict(int)
        theme_max_h: dict[str, int] = defaultdict(int)
        ev_text_by_code: dict[str, dict[str, str]] = defaultdict(dict)
        tag_pop: dict[str, int] = defaultdict(int)

        for r in core_rows:
            code = r["code"]
            meta = stock_meta.get(code)
            t_list = tags_by_code.get(code, [])
            ma_list = ma_by_code.get(code, [])

            themes: list[str] = []
            seen_t: set[str] = set()
            evidences: list[dict[str, Any]] = []

            for t_row in t_list:
                t = _clean_text(t_row["tag"])
                if t and t not in seen_t:
                    seen_t.add(t)
                    themes.append(t)
                    ev_txt = _clean_text(t_row["evidence"])
                    ev_text_by_code[code][t] = ev_txt
                    evidences.append(
                        {
                            "theme": t,
                            "pct": None,
                            "text": ev_txt,
                        }
                    )

            if ma_list and "并购" not in seen_t:
                seen_t.add("并购")
                themes.append("并购")
                ma_summary = "；".join(
                    f"{m['event_type']}：{m['target_name']}" for m in ma_list[:2]
                )
                ev_text_by_code[code]["并购"] = ma_summary
                evidences.append(
                    {
                        "theme": "并购",
                        "pct": None,
                        "text": ma_summary,
                    }
                )

            h = int(r["board_height"] or 1)
            is_ow = bool(r["is_one_word"])
            for t in themes:
                theme_members[t].append(code)
                tag_pop[t] += 1

            prov = _short_prov(meta["province"]) if meta else ""
            ctrl_prov = (
                _short_prov(meta["controller_province"])
                if meta and meta.get("controller_province")
                else ""
            )
            ctrl_type = (meta.get("controller_type") or "") if meta else ""
            if ctrl_type == "民营及其他":
                ctrl_type = "民营"

            name = (meta["name"] if meta and meta.get("name") else r["name"]) or code
            first_time = (r["first_limit_time"] or "")[:5]
            amount_yi = round(float(r["amount_yi"]), 2) if r["amount_yi"] is not None else None
            turnover = round(float(r["turnover_rate"]), 1) if r["turnover_rate"] is not None else None

            is_fb = is_fanbao_stock(r["is_fanbao"], r["boards_desc"])
            raw_stocks[code] = {
                "code": code,
                "name": name,
                "height": h,
                "boards_desc": _clean_text(r["boards_desc"]),
                "first_time": first_time,
                "amount_yi": amount_yi,
                "turnover": turnover,
                "is_one_word": is_ow,
                "is_fanbao": is_fb,
                "fanbao_gain_pct": _compute_fanbao_gain_pct(conn, code, date, r["boards_desc"]) if is_fb else None,
                "province": prov,
                "controller_province": ctrl_prov if ctrl_prov and ctrl_prov != prov else "",
                "controller_type": ctrl_type,
                "industry": (meta.get("em_industry") or "") if meta else "",
                "themes": themes,
                "evidences": evidences,
                "ma_events": [
                    {
                        "type": m["event_type"],
                        "target": m["target_name"],
                        "target_l1": m["target_l1"] or "",
                        "from_date": m["from_date"] or "",
                    }
                    for m in ma_list
                ],
                "primary_theme": "",
                "driver": None,
                "driver2": None,
                "driver_basis": "",
                "driver_basis_type": "",
                "driver_source": "",
                "display_source": "",
            }

        news_text_all = " ".join(
            f"{_clean_text(nw['headline'])} {_clean_text(nw['detail'])}" for nw in news_rows
        )
        for r in core_rows:
            code = r["code"]
            st = raw_stocks[code]
            h = st["height"]
            is_ow = st["is_one_word"]
            d_row = driver_rows.get(code)
            if d_row:
                drv = d_row.get("driver") or None
                drv2 = d_row.get("driver2") or None
                btype = d_row.get("basis_type") or ""
                basis = _clean_text(d_row.get("basis"))
                dsrc = d_row.get("source") or "llm"
            else:
                drv = rule_driver(
                    st["themes"],
                    ev_text_by_code.get(code, {}),
                    news_text_all,
                    tag_pop,
                    prev_driver_map.get(code),
                    h,
                )
                drv2 = None
                btype = "resonance" if drv else ""
                basis = "规则兜底：同涨共振/证据匹配" if drv else ""
                dsrc = "rule"

            st["driver"] = drv
            st["driver2"] = drv2
            st["driver_basis"] = basis
            st["driver_basis_type"] = btype
            st["driver_source"] = dsrc

            for t in (drv, drv2):
                if t and t not in st["themes"]:
                    st["themes"].append(t)
                    theme_members[t].append(code)
                    tag_pop[t] += 1
                    ev_text_by_code[code][t] = basis
                    st["evidences"].append({"theme": t, "pct": None, "text": basis})

            weighted_pairs: list[tuple[str, float]] = []
            if drv:
                weighted_pairs.append((drv, 1.0))
            if drv2 and drv2 != drv:
                weighted_pairs.append((drv2, 0.4))
            for t, w in weighted_pairs:
                theme_drivers[t].append(code)
                theme_core_total[t] += w
                if h >= 2:
                    theme_multi[t] += 1
                    theme_core_multi[t] += w
                if is_ow:
                    theme_one_word[t] += 1
                if h > theme_max_h[t]:
                    theme_max_h[t] = h

        # Pass 2: build Top Catalyst Cards FIRST from daily_hot_news + driver-based ladders
        name_to_code = {st["name"]: code for code, st in raw_stocks.items()}
        pool_set = set(raw_stocks.keys())
        theme_news_map: dict[str, list[dict[str, Any]]] = defaultdict(list)
        event_catalysts: list[dict[str, Any]] = []

        for nw in news_rows:
            hl = _clean_text(nw["headline"])
            dt = _clean_text(nw["detail"])
            combined = f"{hl} {dt}"

            mentioned: list[str] = []
            raw_codes = nw.get("codes")
            if raw_codes:
                try:
                    parsed_codes = json.loads(raw_codes) if isinstance(raw_codes, str) else raw_codes
                    mentioned = [str(c) for c in parsed_codes if str(c) in pool_set]
                except Exception:
                    mentioned = []
            if not mentioned:
                mentioned = [
                    code
                    for sname, code in name_to_code.items()
                    if sname and sname in combined
                ]
            mentioned.sort(
                key=lambda c: (
                    -raw_stocks[c]["height"],
                    -int(raw_stocks[c]["is_one_word"]),
                    raw_stocks[c]["first_time"],
                )
            )

            mapped_theme: str | None = None
            event_label: str | None = None
            event_accent: str = "amber"
            nw_theme = _clean_text(nw.get("theme"))
            if nw_theme and (nw_theme in VOCAB_SET or nw_theme.endswith("字辈")):
                if nw_theme in theme_drivers:
                    mapped_theme = nw_theme
                else:
                    event_label = nw_theme
                    event_accent = _accent_for(nw_theme)

            if not mapped_theme and not event_label:
                for kw, label, acc in NEWS_EVENT_SHORT_TITLES:
                    if kw in combined:
                        event_label = label
                        event_accent = acc
                        break

            if mapped_theme:
                theme_news_map[mapped_theme].append(
                    {
                        "rank": nw["rank"],
                        "headline": hl,
                        "detail": dt,
                        "hit_count": int(nw.get("hit_count") or 1),
                        "mentioned": mentioned,
                    }
                )
            else:
                max_h_m = max((raw_stocks[c]["height"] for c in mentioned), default=0)
                if len(mentioned) >= 2 or max_h_m >= 3:
                    ev_title = event_label or hl[:6]
                    ev_multi = sum(1 for c in mentioned if raw_stocks[c]["height"] >= 2)
                    ev_ow = sum(1 for c in mentioned if raw_stocks[c]["is_one_word"])
                    event_catalysts.append(
                        {
                            "id": f"event:{nw['rank']}",
                            "kind": "event",
                            "title": ev_title,
                            "theme": None,
                            "accent": event_accent,
                            "headline": hl,
                            "news": [{"headline": hl, "detail": dt}],
                            "codes": mentioned,
                            "total": len(mentioned),
                            "multi": ev_multi,
                            "one_word": ev_ow,
                            "max_height": max_h_m,
                            "leaders": [
                                {
                                    "code": c,
                                    "name": raw_stocks[c]["name"],
                                    "height": raw_stocks[c]["height"],
                                    "is_one_word": raw_stocks[c]["is_one_word"],
                                }
                                for c in mentioned[:3]
                            ],
                            "_score": 20.0 + int(nw.get("hit_count") or 1) * 3.0 + max_h_m * 3.0 - nw["rank"] * 0.6,
                        }
                    )

        catalysts: list[dict[str, Any]] = []
        included_themes: set[str] = set()

        def _make_theme_catalyst(t: str, news_list: list[dict[str, Any]]) -> dict[str, Any]:
            codes_t = list(theme_drivers[t])
            seen_c = set(codes_t)
            for nw in news_list:
                for c in nw["mentioned"]:
                    if c not in seen_c:
                        seen_c.add(c)
                        codes_t.append(c)
            codes_t.sort(
                key=lambda c: (
                    -raw_stocks[c]["height"],
                    -int(raw_stocks[c]["is_one_word"]),
                    raw_stocks[c]["first_time"],
                    -(raw_stocks[c]["amount_yi"] or 0),
                )
            )
            multi_cnt = sum(1 for c in codes_t if raw_stocks[c]["height"] >= 2)
            ow_cnt = sum(1 for c in codes_t if raw_stocks[c]["is_one_word"])
            max_h = max((raw_stocks[c]["height"] for c in codes_t), default=1)
            heights_present = sorted({raw_stocks[c]["height"] for c in codes_t}, reverse=True)

            if news_list:
                headline = news_list[0]["headline"]
                news_payload = [
                    {"headline": n["headline"], "detail": n["detail"]}
                    for n in news_list
                ]
            else:
                lead = raw_stocks[codes_t[0]]
                h_chain = "→".join(("反包" if x == 1 else f"{x}板") for x in heights_present[:4])
                ow_note = "一字" if lead["is_one_word"] else ""
                lead_h = lead["boards_desc"] if lead["height"] == 1 and lead["boards_desc"] else f"{lead['height']}板"
                headline = f"{lead_h}{ow_note}{lead['name']}领涨，梯队覆盖 {h_chain}"
                news_payload = []

            best_rank = min((n["rank"] for n in news_list), default=14)
            news_hits = sum(int(n.get("hit_count") or 1) for n in news_list)
            score = (
                max_h * 9.0
                + (24.0 + news_hits * 2.5 if news_list else 0.0)
                + theme_core_multi[t] * 6.5
                + theme_core_total[t] * 2.0
                - best_rank * 0.45
            )
            return {
                "id": f"theme:{t}",
                "kind": "theme",
                "title": t,
                "theme": t,
                "accent": _accent_for(t),
                "headline": headline,
                "news": news_payload,
                "codes": codes_t,
                "total": len(codes_t),
                "multi": multi_cnt,
                "one_word": ow_cnt,
                "max_height": max_h,
                "leaders": [
                    {
                        "code": c,
                        "name": raw_stocks[c]["name"],
                        "height": raw_stocks[c]["height"],
                        "is_one_word": raw_stocks[c]["is_one_word"],
                    }
                    for c in codes_t[:3]
                ],
                "_score": score,
            }

        # Add news-backed pure themes that have >= 1 driving core stock
        for t, nlist in theme_news_map.items():
            if len(theme_drivers[t]) >= 1:
                included_themes.add(t)
                catalysts.append(_make_theme_catalyst(t, nlist))

        # Add strong driver-backed core ladder themes (>=2 core drivers, or >=3B / >=3-board fanbao leader)
        for t, drv_codes in theme_drivers.items():
            if t in included_themes:
                continue
            has_strong_fb = any(fanbao_board_count(raw_stocks[c]["boards_desc"]) >= 3 for c in drv_codes)
            if len(drv_codes) >= 2 or ((theme_max_h[t] >= 3 or has_strong_fb) and len(drv_codes) >= 1):
                included_themes.add(t)
                catalysts.append(_make_theme_catalyst(t, []))

        catalysts.extend(event_catalysts)
        catalysts.sort(key=lambda x: -x["_score"])
        for c_item in catalysts:
            c_item.pop("_score", None)
        catalysts = catalysts[:10]

        # Assign explicit intraday fermentation heat_rank (1 = 最强发酵 红, 2 = 第二发酵 橙, 3+ = 常规)
        theme_heat_rank: dict[str, int] = {}
        for idx, c_item in enumerate(catalysts, 1):
            c_item["heat_rank"] = idx
            if c_item["theme"]:
                theme_heat_rank[c_item["theme"]] = idx
            else:
                c_item["event_rank"] = idx

        # Pass 3: Strict User Display Rule (core stocks: 连板+反包):
        #   1. slot1 = driver if driver in top10
        #   2. else slot1 = most recent prior primary_theme in last 5 trading days (yesterday for streaks, pre-break for fanbao)
        #   3. else slot1 = main_business(em_industry, own_tags)
        top10_themes = {c_item["theme"] for c_item in catalysts if c_item.get("theme")}

        prev_display_map: dict[str, list[str]] = {}
        if prev_dates and _depth < 60:
            for pd in reversed(prev_dates):
                if pd not in _DAY_DISPLAY_CACHE:
                    get_day_payload(pd, _depth=_depth + 1)
                for c_prev, pair_prev in _DAY_DISPLAY_CACHE.get(pd, {}).items():
                    if pair_prev:
                        prev_display_map[c_prev] = pair_prev

        today_display_map: dict[str, list[str]] = {}
        for code, st in raw_stocks.items():
            drv = st["driver"]
            drv2 = st["driver2"]
            prev_pair = prev_display_map.get(code) or []
            prev_first = prev_pair[0] if prev_pair else None

            if drv and drv in top10_themes:
                slot1 = drv
                dsrc = "driver"
            elif prev_first:
                slot1 = prev_first
                dsrc = "prev"
            else:
                slot1 = main_business(st["industry"], st["themes"])
                dsrc = "main"

            pair = [slot1] if slot1 else []
            st["primary_theme"] = slot1
            st["primary_accent"] = _accent_for(slot1)
            st["display_source"] = dsrc
            st["display_themes"] = [
                {"name": t, "heat_rank": theme_heat_rank.get(t, 99)}
                for t in pair
            ]
            today_display_map[code] = pair

        if date:
            _DAY_DISPLAY_CACHE[date] = today_display_map

        # Build complete theme index (core stocks only: drivers ordered first, non-driver followers after)
        themes_index: dict[str, dict[str, Any]] = {}
        for t, members in theme_members.items():
            drv_set = set(theme_drivers.get(t, []))
            sorted_m = sorted(
                members,
                key=lambda c: (
                    0 if c in drv_set else 1,
                    -raw_stocks[c]["height"],
                    -fanbao_board_count(raw_stocks[c]["boards_desc"]),
                    -int(raw_stocks[c]["is_one_word"]),
                    raw_stocks[c]["first_time"],
                    -(raw_stocks[c]["amount_yi"] or 0),
                ),
            )
            news_list = [
                {"headline": n["headline"], "detail": n["detail"]}
                for n in theme_news_map.get(t, [])
            ]
            themes_index[t] = {
                "name": t,
                "accent": _accent_for(t),
                "heat_rank": theme_heat_rank.get(t, 99),
                "codes": sorted_m,
                "driver_codes": [c for c in sorted_m if c in drv_set],
                "total": len(sorted_m),
                "multi": sum(1 for c in sorted_m if raw_stocks[c]["height"] >= 2),
                "fanbao": sum(1 for c in sorted_m if raw_stocks[c]["height"] == 1),
                "one_word": sum(1 for c in sorted_m if raw_stocks[c]["is_one_word"]),
                "max_height": max((raw_stocks[c]["height"] for c in sorted_m), default=1),
                "news": news_list,
            }

        # Order each stock's themes: driver first, driver2 second, then heat & breadth
        for st in raw_stocks.values():
            drv = st["driver"]
            drv2 = st["driver2"]
            st["themes"].sort(
                key=lambda t: (
                    0 if t == drv else (1 if t == drv2 else 2),
                    theme_heat_rank.get(t, 99),
                    0 if t == st["primary_theme"] else 1,
                    -(themes_index[t]["multi"] * 4 + themes_index[t]["total"])
                    if t in themes_index
                    else 0,
                )
            )
            # If the stock participates in rank-1 or rank-2 intraday hottest theme, check if its primary_theme is that rank
            pt_rank = theme_heat_rank.get(st["primary_theme"], 99)
            if pt_rank > 2:
                best_owned = min((theme_heat_rank.get(t, 99) for t in st["themes"]), default=99)
                st["best_heat_rank"] = best_owned
            else:
                st["best_heat_rank"] = pt_rank
            st["primary_heat_rank"] = pt_rank

        # Build ladder tiers (>=2板) & fanbao_boards (反包 / N天M板); a stock can appear in BOTH!
        tiers_map: dict[int, list[str]] = defaultdict(list)
        fanbao_boards: list[str] = []
        for r in core_rows:
            code = r["code"]
            st = raw_stocks[code]
            if st["height"] >= 2:
                tiers_map[st["height"]].append(code)
            if st["is_fanbao"]:
                fanbao_boards.append(code)

        fanbao_boards.sort(
            key=lambda c: (
                -fanbao_board_count(raw_stocks[c]["boards_desc"]),
                -raw_stocks[c]["height"],
                -int(raw_stocks[c]["is_one_word"]),
                raw_stocks[c]["first_time"],
                -(raw_stocks[c]["amount_yi"] or 0),
            )
        )

        ladder = [
            {"height": h, "codes": tiers_map[h]}
            for h in sorted(tiers_map.keys(), reverse=True)
        ]

        multi_total = sum(len(x["codes"]) for x in ladder)
        ow_total = sum(1 for st in raw_stocks.values() if st["is_one_word"])
        max_height = ladder[0]["height"] if ladder else (1 if total_zt else 0)
        mood = _get_day_mood(date, total_zt, fetch_remote=True)

        return {
            "date": date,
            "summary": {
                "total": total_zt,
                "core": len(raw_stocks),
                "multi": multi_total,
                "fanbao": len(fanbao_boards),
                "first": 0,
                "one_word": ow_total,
                "max_height": max_height,
                "zb_count": mood["zb_count"],
                "zhaban_rate": mood["zhaban_rate"],
                "dt_count": mood["dt_count"],
                "sign": mood["sign"],
            },
            "catalysts": catalysts,
            "ladder": ladder,
            "fanbao_boards": fanbao_boards,
            "first_boards": [],
            "stocks": raw_stocks,
            "themes": themes_index,
        }
    finally:
        conn.close()


class SuperBoardHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        # Quiet concise logs
        return

    def _send_json(self, payload: Any, status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _send_file(self, path: Path) -> None:
        if not path.exists() or not path.is_file():
            self.send_error(404)
            return
        mime, _ = mimetypes.guess_type(str(path))
        if path.suffix == ".js":
            mime = "application/javascript; charset=utf-8"
        elif path.suffix == ".css":
            mime = "text/css; charset=utf-8"
        elif path.suffix == ".html":
            mime = "text/html; charset=utf-8"
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mime or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/api/dates":
            self._send_json({"dates": get_available_dates()})
            return
        if path == "/api/day":
            qs = parse_qs(parsed.query)
            date = qs.get("date", [None])[0]
            self._send_json(get_day_payload(date))
            return

        rel = "index.html" if path in ("/", "") else path.lstrip("/")
        target = (WEB_DIR / rel).resolve()
        if not str(target).startswith(str(WEB_DIR.resolve())):
            self.send_error(403)
            return
        self._send_file(target)


def _local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def export_static_site(limit: int = 30) -> None:
    """Export compact static JSON snapshots into web/data/ for GitHub Pages."""
    _DAY_DISPLAY_CACHE.clear()
    out_data = WEB_DIR / "data"
    out_days = out_data / "days"
    out_days.mkdir(parents=True, exist_ok=True)
    (WEB_DIR / ".nojekyll").write_text("", encoding="utf-8")

    all_dates = get_available_dates(limit=limit)[:limit]
    payloads_by_date: dict[str, dict[str, Any]] = {}
    for d_info in reversed(all_dates):
        dt = d_info["date"]
        payload = get_day_payload(dt)
        payloads_by_date[dt] = payload
        (out_days / f"{dt}.json").write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )

    exported_dates: list[dict[str, Any]] = []
    for d_info in all_dates:
        dt = d_info["date"]
        payload = payloads_by_date[dt]
        d_copy = dict(d_info)
        if payload["summary"].get("zhaban_rate") is not None:
            d_copy["zhaban_rate"] = payload["summary"]["zhaban_rate"]
        exported_dates.append(d_copy)

    (out_data / "dates.json").write_text(
        json.dumps({"dates": exported_dates}, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"Exported {len(exported_dates)} trading days to {out_data}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Super-Board Mobile Web Server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--export-site", action="store_true", help="Export static site JSONs to web/data/ for GitHub Pages")
    parser.add_argument("--days", type=int, default=30, help="Number of recent trading days to export")
    args = parser.parse_args()

    if args.export_site:
        export_static_site(limit=args.days)
        return

    server = ThreadingHTTPServer((args.host, args.port), SuperBoardHandler)
    lan_ip = _local_ip()
    print(f"Super-Board Mobile UI running:")
    print(f"  Local : http://127.0.0.1:{args.port}")
    print(f"  Mobile: http://{lan_ip}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
