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

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data/super_board.sqlite"
WEB_DIR = ROOT / "web"
ULTRA_BOARD_RAW = Path(r"C:\Ai\Ultra-Board\data\kaipanla\raw")
MOOD_CACHE_PATH = ROOT / "data/market_mood_cache.json"
_MOOD_CACHE: dict[str, dict[str, Any]] | None = None
_DAY_DISPLAY_CACHE: dict[str, dict[str, list[str]]] = {}

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


# Broad background L1 categories that shouldn't overshadow sharp thematic catalysts
# when a stock carries both a sharp active theme (e.g. 机器人/商业航天/AI应用/芯片/算力) and a broad L1
BROAD_BACKGROUND_L1 = {"工业设备", "基建", "环保", "汽车", "农业", "交运", "地产"}


def _accent_for(theme: str) -> str:
    return THEME_ACCENTS.get(theme, "slate")


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

        prev_row = conn.execute(
            "SELECT MAX(trade_date) AS prev_date FROM daily_limit_pool WHERE trade_date < ?",
            (date,),
        ).fetchone()
        prev_date = prev_row["prev_date"] if prev_row and prev_row["prev_date"] else None

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

        codes = [r["code"] for r in pool_rows]
        if not codes:
            return {
                "date": date,
                "summary": {"total": 0, "multi": 0, "one_word": 0, "max_height": 0},
                "catalysts": [],
                "ladder": [],
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
                SELECT rank, headline, detail, hit_count
                FROM daily_hot_news
                WHERE trade_date = ?
                ORDER BY rank ASC
                """,
                (date,),
            ).fetchall()
        ]

        # Pass 1: build unified full-dynamic pure themes per stock
        raw_stocks: dict[str, dict[str, Any]] = {}
        theme_members: dict[str, list[str]] = defaultdict(list)
        theme_multi: dict[str, int] = defaultdict(int)
        theme_core_multi: dict[str, float] = defaultdict(float)
        theme_core_total: dict[str, float] = defaultdict(float)
        theme_one_word: dict[str, int] = defaultdict(int)
        theme_max_h: dict[str, int] = defaultdict(int)
        stock_tag_dates: dict[str, dict[str, str]] = defaultdict(dict)
        stock_tag_rank: dict[str, dict[str, int]] = defaultdict(dict)

        def _days_gap(d1: str | None, d2: str | None) -> int:
            if not d1 or not d2 or len(d1) < 10 or len(d2) < 10:
                return 999
            try:
                return abs((dt_date.fromisoformat(d1[:10]) - dt_date.fromisoformat(d2[:10])).days)
            except Exception:
                return 999

        for r in pool_rows:
            code = r["code"]
            meta = stock_meta.get(code)
            t_list = tags_by_code.get(code, [])
            ma_list = ma_by_code.get(code, [])

            themes: list[str] = []
            seen_t: set[str] = set()
            evidences: list[dict[str, Any]] = []

            for idx_t, t_row in enumerate(t_list):
                t = _clean_text(t_row["tag"])
                if t and t not in seen_t:
                    seen_t.add(t)
                    themes.append(t)
                    stock_tag_dates[code][t] = _clean_text(t_row.get("from_date"))
                    stock_tag_rank[code][t] = idx_t
                    evidences.append(
                        {
                            "theme": t,
                            "pct": None,
                            "text": _clean_text(t_row["evidence"]),
                        }
                    )

            if ma_list and "并购" not in seen_t:
                seen_t.add("并购")
                themes.append("并购")
                stock_tag_dates[code]["并购"] = _clean_text(ma_list[0].get("from_date"))
                stock_tag_rank[code]["并购"] = len(themes) - 1
                ma_summary = "；".join(
                    f"{m['event_type']}：{m['target_name']}" for m in ma_list[:2]
                )
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
                rk = stock_tag_rank[code].get(t, 0)
                w = 1.0 if rk == 0 else (0.85 if rk == 1 else 0.7)
                theme_core_total[t] += w
                if h >= 2:
                    theme_multi[t] += 1
                    theme_core_multi[t] += w
                if is_ow:
                    theme_one_word[t] += 1
                if h > theme_max_h[t]:
                    theme_max_h[t] = h

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

            raw_stocks[code] = {
                "code": code,
                "name": name,
                "height": h,
                "boards_desc": _clean_text(r["boards_desc"]),
                "first_time": first_time,
                "amount_yi": amount_yi,
                "turnover": turnover,
                "is_one_word": is_ow,
                "is_fanbao": bool(r["is_fanbao"]),
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
            }

        # Pure Super-Board intraday theme strength (revenue-weighted so tiny side-businesses never inflate fake heat)
        def _theme_score(t: str) -> float:
            broad_penalty = 0.68 if t in BROAD_BACKGROUND_L1 else 1.0
            news_bonus = 24.0 if t in theme_news_map else 0.0
            return (
                news_bonus
                + theme_max_h[t] * 3.5
                + theme_one_word[t] * 3.5
                + theme_core_multi[t] * 6.5
                + theme_core_total[t] * 2.2
            ) * broad_penalty

        # Pass 2: build Top Catalyst Cards FIRST from daily_hot_news + pure Super-Board ladders
        name_to_code = {st["name"]: code for code, st in raw_stocks.items()}
        theme_news_map: dict[str, list[dict[str, Any]]] = defaultdict(list)
        event_catalysts: list[dict[str, Any]] = []

        for nw in news_rows:
            hl = _clean_text(nw["headline"])
            dt = _clean_text(nw["detail"])
            combined = f"{hl} {dt}"

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
            for kw, label, acc in NEWS_EVENT_SHORT_TITLES:
                if kw in combined:
                    if label in theme_members:
                        mapped_theme = label
                    else:
                        event_label = label
                        event_accent = acc
                    break

            if not mapped_theme and not event_label and mentioned:
                counts: dict[str, int] = defaultdict(int)
                for c in mentioned:
                    for t in raw_stocks[c]["themes"]:
                        counts[t] += 1
                if counts:
                    top_t, top_cnt = max(counts.items(), key=lambda kv: (kv[1], _theme_score(kv[0])))
                    if top_cnt >= max(1, len(mentioned) // 2):
                        mapped_theme = top_t

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
            codes_t = list(theme_members[t])
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
                h_chain = "→".join(f"{x}板" for x in heights_present[:4])
                ow_note = "一字" if lead["is_one_word"] else ""
                headline = f"{lead['height']}板{ow_note}{lead['name']}领涨，梯队覆盖 {h_chain}"
                news_payload = []

            best_rank = min((n["rank"] for n in news_list), default=14)
            news_hits = sum(int(n.get("hit_count") or 1) for n in news_list)
            broad_factor = 0.58 if (t in BROAD_BACKGROUND_L1 and not news_list) else 1.0
            # Catalyst heat combines: Leader Height (高标牵引) + Intraday News & Core Breadth (热点发酵)
            score = (
                max_h * 9.0
                + (24.0 + news_hits * 2.5 if news_list else 0.0)
                + theme_core_multi[t] * 6.5
                + theme_core_total[t] * 2.0
                - best_rank * 0.45
            ) * broad_factor
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

        # Add all news-backed pure themes
        for t, nlist in theme_news_map.items():
            included_themes.add(t)
            catalysts.append(_make_theme_catalyst(t, nlist))

        # Add strong pure ladder themes even if not explicitly named in overnight news
        for t, members in theme_members.items():
            if t in included_themes:
                continue
            if t in BROAD_BACKGROUND_L1 and theme_multi[t] < 3:
                continue
            if theme_multi[t] >= 2 or (theme_max_h[t] >= 3 and len(members) >= 3):
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

        # Pass 3: Select 1~2 crisp display themes per stock (never padding with <25% cold side-businesses):
        #   Slot 1 (主位): Today's real hot catalyst (#1/#2 or news-backed Top 8) -> yesterday's streak theme -> #1 main business
        #   Slot 2 (共振/补位, optional): 2nd hot catalyst -> dynamic cross-sector/M&A tag -> yesterday's 2nd theme -> core main business (>=25% revenue, deprioritizing broad catch-all 机械/基建/环保)
        hot_theme_ranks: dict[str, int] = {}
        for c_item in catalysts:
            t = c_item.get("theme")
            if not t:
                continue
            r = c_item["heat_rank"]
            has_news = len(c_item.get("news") or []) > 0
            if r <= 2 or (has_news and r <= 8):
                hot_theme_ranks[t] = r

        need_prev = any(
            st["height"] >= 2 and st["themes"]
            for st in raw_stocks.values()
        )
        prev_display_map: dict[str, list[str]] = {}
        if need_prev and prev_date and _depth < 12:
            if prev_date not in _DAY_DISPLAY_CACHE:
                get_day_payload(prev_date, _depth=_depth + 1)
            prev_display_map = _DAY_DISPLAY_CACHE.get(prev_date, {})

        today_display_map: dict[str, list[str]] = {}
        GENERIC_SECOND_SKIP = {"机械", "基建", "环保", "工业设备"}

        def _is_stale_tag(c: str, t: str) -> bool:
            """Non-primary tag confirmed >60 days away from trade_date yields to fresh hot catalysts."""
            if t == "并购" or stock_tag_rank[c].get(t, 0) == 0:
                return False
            fdate = stock_tag_dates[c].get(t)
            return _days_gap(date, fdate) > 60

        for code, st in raw_stocks.items():
            own_themes = st["themes"]
            if not own_themes:
                st["primary_theme"] = ""
                st["primary_accent"] = "slate"
                st["display_themes"] = []
                continue

            prev_pair = prev_display_map.get(code) or []
            prev_first = prev_pair[0] if len(prev_pair) >= 1 else None

            # --- Slot 1 ---
            hot_owned = sorted(
                [t for t in own_themes if t in hot_theme_ranks],
                key=lambda t: (
                    1 if _is_stale_tag(code, t) else 0,
                    hot_theme_ranks[t],
                    stock_tag_rank[code].get(t, 9),
                ),
            )
            fresh_hot = [t for t in hot_owned if not _is_stale_tag(code, t)]

            if fresh_hot:
                slot1 = fresh_hot[0]
            elif st["height"] >= 2 and prev_first in own_themes:
                slot1 = prev_first
            elif hot_owned:
                slot1 = hot_owned[0]
            else:
                slot1 = own_themes[0]

            # --- Slot 2 (2nd fresh hot catalyst OR stock's own #1 core tag if Slot 1 was another catalyst) ---
            slot2: str | None = None
            rem = [t for t in own_themes if t != slot1]
            if rem:
                rem_fresh_hot = [t for t in fresh_hot if t != slot1]
                if rem_fresh_hot:
                    slot2 = rem_fresh_hot[0]
                elif own_themes[0] != slot1 and own_themes[0] not in GENERIC_SECOND_SKIP:
                    slot2 = own_themes[0]

            pair = [slot1] + ([slot2] if slot2 else [])
            st["primary_theme"] = slot1
            st["primary_accent"] = _accent_for(slot1)
            st["display_themes"] = [
                {"name": t, "heat_rank": theme_heat_rank.get(t, 99)}
                for t in pair
            ]
            today_display_map[code] = pair

        if date:
            _DAY_DISPLAY_CACHE[date] = today_display_map

        # Build complete theme index (for clicking ANY tag inside Stock Modal or Theme Modal!)
        themes_index: dict[str, dict[str, Any]] = {}
        for t, members in theme_members.items():
            sorted_m = sorted(
                members,
                key=lambda c: (
                    -raw_stocks[c]["height"],
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
                "total": len(sorted_m),
                "multi": sum(1 for c in sorted_m if raw_stocks[c]["height"] >= 2),
                "one_word": sum(1 for c in sorted_m if raw_stocks[c]["is_one_word"]),
                "max_height": max((raw_stocks[c]["height"] for c in sorted_m), default=1),
                "news": news_list,
            }

        # Order each stock's themes so rank-1/rank-2 and primary_theme come first, and attach primary_heat_rank
        for st in raw_stocks.values():
            st["themes"].sort(
                key=lambda t: (
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
                # Check if stock carries rank-1 or rank-2 directly when primary wasn't top-2
                best_owned = min((theme_heat_rank.get(t, 99) for t in st["themes"]), default=99)
                st["best_heat_rank"] = best_owned
            else:
                st["best_heat_rank"] = pt_rank
            st["primary_heat_rank"] = pt_rank

        # Build ladder tiers (>=2板) & first_boards (1板)
        tiers_map: dict[int, list[str]] = defaultdict(list)
        first_boards: list[str] = []
        for r in pool_rows:
            code = r["code"]
            h = raw_stocks[code]["height"]
            if h >= 2:
                tiers_map[h].append(code)
            else:
                first_boards.append(code)

        ladder = [
            {"height": h, "codes": tiers_map[h]}
            for h in sorted(tiers_map.keys(), reverse=True)
        ]

        multi_total = sum(len(x["codes"]) for x in ladder)
        ow_total = sum(1 for st in raw_stocks.values() if st["is_one_word"])
        max_height = ladder[0]["height"] if ladder else (1 if first_boards else 0)
        mood = _get_day_mood(date, len(raw_stocks), fetch_remote=True)

        return {
            "date": date,
            "summary": {
                "total": len(raw_stocks),
                "multi": multi_total,
                "first": len(first_boards),
                "one_word": ow_total,
                "max_height": max_height,
                "zb_count": mood["zb_count"],
                "zhaban_rate": mood["zhaban_rate"],
                "dt_count": mood["dt_count"],
                "sign": mood["sign"],
            },
            "catalysts": catalysts,
            "ladder": ladder,
            "first_boards": first_boards,
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
    out_data = WEB_DIR / "data"
    out_days = out_data / "days"
    out_days.mkdir(parents=True, exist_ok=True)
    (WEB_DIR / ".nojekyll").write_text("", encoding="utf-8")

    all_dates = get_available_dates(limit=limit)[:limit]
    exported_dates: list[dict[str, Any]] = []
    for d_info in all_dates:
        dt = d_info["date"]
        payload = get_day_payload(dt)
        (out_days / f"{dt}.json").write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
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
