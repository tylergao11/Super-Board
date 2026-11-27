"""Pure-stdlib run_workflow script for full-ladder core-stock (连板+反包) driver attribution (zero kpl)."""
import json
import sqlite3
import sys
from collections import defaultdict
from datetime import date as dt_date, timedelta
from pathlib import Path

ROOT = Path(args.get("root", r"d:\Super-Board")) if "args" in dir() else Path(r"d:\Super-Board")
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from driver_rules import (  # noqa: E402
    candidates,
    detect_dynamic_name_lines,
    fanbao_board_count,
    is_core_stock,
    rule_driver,
)

DB_PATH = ROOT / "data/super_board.sqlite"
RAW_NEWS_DIR = ROOT / "data/raw_news"
RAW_ANN_DAY_DIR = ROOT / "data/raw_ann_day"
DRIVERS_DIR = ROOT / "data/drivers"
DRIVERS_DIR.mkdir(parents=True, exist_ok=True)

TARGET_DATE = str(args.get("date") or "").strip() if "args" in dir() else ""
MONTH = str(args.get("month") or "").strip() if "args" in dir() else ""
MONTHS = list(args.get("months") or []) if "args" in dir() else []
REFRESH = bool(args.get("refresh", False)) if "args" in dir() else False
MA_ANN_KWS = ("收购", "重组", "要约", "控制权", "股权转让", "股份转让", "资产注入", "借壳", "吸收合并", "发行股份购买")

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "trade_date": {"type": "string"},
        "stocks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "code": {"type": "string"},
                    "driver": {"type": "string"},
                    "driver2": {"type": ["string", "null"]},
                    "basis_type": {"type": "string", "enum": ["news", "announcement", "resonance", "continue"]},
                    "basis": {"type": "string"},
                },
                "required": ["code", "driver", "driver2", "basis_type", "basis"],
            },
        },
    },
    "required": ["trade_date", "stocks"],
}

RULES_PROMPT = """你是A股超短线连板梯队复盘专家（只读模式，严禁调用任何工具，直接通过 finish 返回结构化 JSON）。

下面给你提供某一交易日**完整且未分片**的全部核心强势股梯队（**仅含连板 ≥2板 与 断板反包/N天M板**，已剔除普通纯首板噪音），请你站在**日内连板梯队全局视角**，结合龙头身位、盘口强度（一字/首封/成交额/换手）、近期主线记忆与当日消息/公告，逐只判定每只核心股的**今日核心驱动（`driver`）**与可选次要驱动（`driver2`）。

【输入材料说明】
- `hot_news`：当日提炼的客观热门消息（含 `theme` 与核心带动股）。
- `intraday_news`：当日东财盘前/盘中焦点快讯标题。
- `dynamic_name_lines`：当日盘面触发的动态字辈暗线（如华字辈/金字辈/羊字辈，已注入对应个股候选集）。
- `core_ladder`：当日全部核心股，按“高标连板 → 低位连板 → 反包(N天M板)”排序，每只包含：
  - 盘口身位：`h`(连板数)、`boards_desc`(如`7天6板`)、`is_fanbao`、`is_one_word`、`first_time`、`amount_yi`、`turnover_rate`；
  - `prev_driver`：该股近 5 个交易日上一次涨停时确立的驱动主线（连板看昨日，反包看断板前主线）；
  - `candidates`：该股全部纯净标签与完整证据原文（含临时并购公告与动态字辈）；
  - `announcements`：该股当日窗口巨潮公告标题；
  - `core_tag_counts`：各候选标签在今日**核心梯队（连板+反包）**中的同题材家数。

【核心铁律】
1. **封闭候选集**：`driver` 必须且只能严格取自该股 `candidates` 中的某个 `tag`（不得为空、不得自造词）；`driver2` 为 `null` 或 `candidates` 中另一个不同 `tag`（仅在明确双线共振时填）。
2. **连板与反包主线延续（反摇摆铁律）**：
   - 若该股带有 `prev_driver`（且仍在今日 `candidates` 中），**默认延续 `prev_driver` 作为 `driver`**（若今日原主线仍在梯队发酵，写 `continue` 或结合今日相关消息写 `news`；若今日叠加另一条热点新闻，只把新热点放在 `driver2`，**严禁因为次要新闻擦边就随意来回切换主线**）。
   - **仅在以下两种硬情形下允许切换 `driver`**：
     ① 本股当日发布了实质性新公告（如并购重组/控制权变更/要约收购/重大合同，`basis_type = "announcement"`，`basis` 必须原封不动等于输入的 `announcements` 中的某条标题）；
     ② `prev_driver` 今日在核心梯队与热门消息中已彻底熄火，且该股今日明显切换并引领/参与了另一条更强的当日核心梯队主线（此时需在 `basis` 中点明主线切换原因）。
3. **新晋 2 板与字辈暗线判定**：
   - 优先顺序：`announcement`（实质公告，原样填标题） > `news`（匹配热门消息/盘中快讯） > `resonance`（核心梯队同涨共振）；
   - 若多只不同行业核心股因当日 `dynamic_name_lines`（如 `华字辈`、`金字辈`、`羊字辈`）集体封板且无更好产业催化，可果断归入对应 `XX字辈`。
4. **红线禁止**：严禁把业绩增长、ST摘帽、超跌、次新股当作驱动依据。
"""


def _load_month_days(month: str) -> list[str]:
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    days = [
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT trade_date FROM daily_limit_pool WHERE trade_date LIKE ? ORDER BY trade_date ASC",
            (f"{month}-%",),
        ).fetchall()
    ]
    conn.close()
    return days


def _seed_recent_history(first_day: str) -> dict[str, dict]:
    """Seed up-to-5-trading-day driver history before first_day from SQLite."""
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    prev_dates = [
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT trade_date FROM daily_limit_pool WHERE trade_date < ? ORDER BY trade_date DESC LIMIT 5",
            (first_day,),
        ).fetchall()
    ]
    hist: dict[str, dict] = {}
    for pd in reversed(prev_dates):
        for code, drv, drv2, basis in conn.execute(
            "SELECT code, driver, driver2, basis FROM daily_stock_driver WHERE trade_date=? AND driver IS NOT NULL",
            (pd,),
        ).fetchall():
            hist[code] = {"date": pd, "driver": drv, "driver2": drv2, "basis": basis or ""}
    conn.close()
    return hist


def _build_day_context(day: str, recent_hist: dict[str, dict]) -> dict:
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    pool_rows = conn.execute(
        """
        SELECT code, name, board_height, boards_desc, is_fanbao, is_one_word,
               first_limit_time, amount_yi, turnover_rate
        FROM daily_limit_pool
        WHERE trade_date = ?
        ORDER BY board_height DESC, is_one_word DESC, first_limit_time ASC, amount_yi DESC, code ASC
        """,
        (day,),
    ).fetchall()

    core_rows = [r for r in pool_rows if is_core_stock(r[2], r[4], r[3])]
    # Order: height>=2 descending, then fanbao sorted by M in N天M板 desc
    core_rows.sort(
        key=lambda r: (
            0 if int(r[2] or 1) >= 2 else 1,
            -int(r[2] or 1),
            -fanbao_board_count(r[3]),
            -int(r[5] or 0),
            (r[6] or "")[:5],
            -(float(r[7]) if r[7] is not None else 0.0),
        )
    )

    codes = [r[0] for r in core_rows]
    cutoff = (dt_date.fromisoformat(day[:10]) - timedelta(days=365)).isoformat()
    placeholders = ",".join("?" * len(codes)) if codes else "''"

    ev_by_code: dict[str, dict[str, tuple[str, str]]] = defaultdict(dict)
    ma_by_code: dict[str, list[tuple[str, str, str, str]]] = defaultdict(list)
    ind_by_code: dict[str, str] = {}
    if codes:
        for c, ind in conn.execute(
            f"SELECT code, em_industry FROM stocks WHERE code IN ({placeholders})", codes
        ).fetchall():
            ind_by_code[c] = ind or ""
        for c, t, fdt, ev in conn.execute(
            f"SELECT code, tag, from_date, evidence FROM stock_tags WHERE code IN ({placeholders}) AND from_date >= ? ORDER BY id ASC",
            [*codes, cutoff],
        ).fetchall():
            ev_by_code[c][t] = (fdt, ev)
        for c, et, tn, fdt, ev in conn.execute(
            f"SELECT code, event_type, target_name, from_date, evidence FROM ma_events WHERE code IN ({placeholders}) ORDER BY from_date DESC, id ASC",
            codes,
        ).fetchall():
            ma_by_code[c].append((et, tn, fdt, ev))

    hot_news = [
        {
            "rank": r[0],
            "headline": r[1],
            "detail": r[2],
            "theme": r[3],
            "codes": [c for c in (json.loads(r[4]) if r[4] else []) if c in set(codes)],
        }
        for r in conn.execute(
            "SELECT rank, headline, detail, theme, codes FROM daily_hot_news WHERE trade_date=? ORDER BY rank ASC",
            (day,),
        ).fetchall()
    ]

    cands_map: dict[str, list[str]] = {c: candidates(conn, c, day) for c in codes}
    conn.close()

    raw_news_p = RAW_NEWS_DIR / f"{day}.json"
    intraday_news = []
    if raw_news_p.exists():
        raw_doc = json.loads(raw_news_p.read_text(encoding="utf-8"))
        intraday_news = [
            {"time": it.get("time", ""), "title": it.get("title", "")}
            for it in (raw_doc.get("items") or [])
        ]

    ann_p = RAW_ANN_DAY_DIR / f"{day}.json"
    ann_map: dict[str, list[str]] = {}
    if ann_p.exists():
        raw_ann = json.loads(ann_p.read_text(encoding="utf-8"))
        for c in codes:
            items = raw_ann.get(c) or []
            ann_map[c] = [str(it.get("title") or "").strip() for it in items if str(it.get("title") or "").strip()]

    # Dynamic name lines (XX字辈) on core stocks
    core_meta_for_zb = [
        {"code": r[0], "name": r[1], "em_industry": ind_by_code.get(r[0], "")}
        for r in core_rows
    ]
    dyn_name_lines = detect_dynamic_name_lines(core_meta_for_zb, hot_news)

    temp_ev: dict[tuple[str, str], str] = {}
    tag_pop: dict[str, int] = defaultdict(int)
    for c in codes:
        cs = cands_map[c]
        ma_hits = [title for title in ann_map.get(c, []) if any(kw in title for kw in MA_ANN_KWS)]
        if "并购" not in cs and ma_hits:
            cs.append("并购")
            temp_ev[(c, "并购")] = "；".join(ma_hits)
        for zb_tag, (matched_codes, zb_ev) in dyn_name_lines.items():
            if c in matched_codes and zb_tag not in cs:
                cs.append(zb_tag)
                temp_ev[(c, zb_tag)] = zb_ev
        # Keep prior XX字辈 candidate if this stock was driven by it in the past 5 days
        prev_info = recent_hist.get(c)
        if prev_info and prev_info.get("driver", "").endswith("字辈"):
            p_zb = prev_info["driver"]
            if p_zb not in cs:
                cs.append(p_zb)
                temp_ev[(c, p_zb)] = f"延续前期{p_zb}主线"
        for t in cs:
            tag_pop[t] += 1

    stocks = []
    empty_codes = []
    for code, name, h, bdesc, is_fb, is_ow, ftime, amt, turn in core_rows:
        cs = cands_map[code]
        if not cs:
            empty_codes.append(code)
            continue
        cand_objs = []
        for t in cs:
            if (code, t) in temp_ev:
                cand_objs.append({"tag": t, "from_date": day, "evidence": temp_ev[(code, t)]})
            elif t == "并购" and t not in ev_by_code[code]:
                ms = ma_by_code.get(code, [])
                fdt = ms[0][2] if ms else ""
                ev_txt = "；".join(f"{et}：{tn}（{ev}）" for et, tn, _, ev in ms[:2])
                cand_objs.append({"tag": "并购", "from_date": fdt, "evidence": ev_txt})
            else:
                fdt, ev_txt = ev_by_code[code].get(t, ("", ""))
                cand_objs.append({"tag": t, "from_date": fdt, "evidence": ev_txt})

        stocks.append(
            {
                "code": code,
                "name": name,
                "h": int(h or 1),
                "boards_desc": bdesc or f"{int(h or 1)}板",
                "is_fanbao": bool(is_fb) or int(h or 1) == 1,
                "is_one_word": bool(is_ow),
                "first_time": (ftime or "")[:5],
                "amount_yi": round(float(amt), 2) if amt is not None else None,
                "turnover_rate": round(float(turn), 1) if turn is not None else None,
                "prev_driver": recent_hist.get(code),
                "candidates": cand_objs,
                "announcements": ann_map.get(code, []),
                "core_tag_counts": {t: tag_pop[t] for t in cs},
            }
        )

    return {
        "trade_date": day,
        "hot_news": hot_news,
        "intraday_news": intraday_news,
        "dynamic_name_lines": {k: {"codes": sorted(v[0]), "evidence": v[1]} for k, v in dyn_name_lines.items()},
        "core_ladder": stocks,
        "empty_codes": empty_codes,
        "recent_hist": recent_hist,
    }


def _validate_day(day: str, res: dict, ladder_stocks: list[dict]) -> tuple[dict[str, dict], list[str], set[str]]:
    by_code_in = {s["code"]: s for s in ladder_stocks}
    errs: list[str] = []
    bad_codes: set[str] = set()
    valid_out: dict[str, dict] = {}

    if res.get("trade_date") != day:
        errs.append(f"trade_date must be {day}")

    got_codes: set[str] = set()
    for rec in res.get("stocks") or []:
        c = str(rec.get("code") or "").strip()
        if c not in by_code_in:
            continue
        if c in got_codes:
            errs.append(f"duplicate code {c}")
            bad_codes.add(c)
            continue
        got_codes.add(c)
        inp = by_code_in[c]
        cands = {x["tag"] for x in inp["candidates"]}
        drv = str(rec.get("driver") or "").strip()
        drv2 = str(rec["driver2"]).strip() if rec.get("driver2") else None
        btype = str(rec.get("basis_type") or "").strip()
        basis = str(rec.get("basis") or "").strip()

        item_errs = []
        if drv not in cands:
            item_errs.append(f"{c}: driver {drv!r} not in candidates {sorted(cands)}")
        if drv2 is not None and (drv2 not in cands or drv2 == drv):
            item_errs.append(f"{c}: invalid driver2 {drv2!r}")
        if btype not in ("news", "announcement", "resonance", "continue"):
            item_errs.append(f"{c}: invalid basis_type {btype!r}")
        if not basis:
            item_errs.append(f"{c}: empty basis")
        if btype == "announcement":
            anns = set(inp["announcements"])
            if basis not in anns:
                item_errs.append(f"{c}: basis must exactly match one of announcements {sorted(anns)}")

        if item_errs:
            errs.extend(item_errs)
            bad_codes.add(c)
        else:
            valid_out[c] = {
                "code": c,
                "driver": drv,
                "driver2": drv2,
                "basis_type": btype,
                "basis": basis,
                "source": "llm",
            }

    missing = sorted(set(by_code_in.keys()) - got_codes)
    if missing:
        errs.append(f"missing codes: {missing}")
        bad_codes.update(missing)
    return valid_out, errs, bad_codes


async def process_day(day: str, recent_hist: dict[str, dict]) -> dict:
    p = DRIVERS_DIR / f"{day}.json"
    if p.exists() and not REFRESH:
        try:
            existing = json.loads(p.read_text(encoding="utf-8"))
            if existing.get("trade_date") == day and existing.get("mode") == "core_ladder_v2":
                for st in existing.get("stocks") or []:
                    if st.get("driver"):
                        recent_hist[st["code"]] = {
                            "date": day,
                            "driver": st["driver"],
                            "driver2": st.get("driver2"),
                            "basis": st.get("basis") or "",
                        }
                return {"trade_date": day, "skipped": True, "stocks": len(existing.get("stocks") or [])}
        except Exception:
            pass

    ctx = _build_day_context(day, recent_hist)
    ladder = ctx["core_ladder"]
    ordered_stocks: list[dict] = []
    rule_cnt = 0

    if ladder:
        payload_for_llm = {
            "trade_date": day,
            "hot_news": ctx["hot_news"],
            "intraday_news": ctx["intraday_news"],
            "dynamic_name_lines": ctx["dynamic_name_lines"],
            "core_ladder": ladder,
        }
        prompt = (
            RULES_PROMPT
            + f"\n现在请一次性全局审视 {day} 全部 {len(ladder)} 只核心强势股（连板+反包），输出完整归因 JSON：\n"
            + json.dumps(payload_for_llm, ensure_ascii=False, separators=(",", ":"))
        )
        a = agent(role=f"CoreLadder {day}", type_name="research")
        res = await a(prompt, OUTPUT_SCHEMA)
        valid_out, errs, bad_codes = _validate_day(day, res, ladder)
        if errs:
            res = await a(
                "校验未通过，请修正以下问题后重新输出完整 JSON：\n" + "\n".join(errs[:25]),
                OUTPUT_SCHEMA,
            )
            valid_out, errs, bad_codes = _validate_day(day, res, ladder)
        del a

        if bad_codes:
            news_text = " ".join(
                f"{n['headline']} {n['detail']}" for n in ctx["hot_news"]
            ) + " " + " ".join(n["title"] for n in ctx["intraday_news"])
            by_code_in = {s["code"]: s for s in ladder}
            for c in sorted(bad_codes):
                inp = by_code_in[c]
                c_list = [x["tag"] for x in inp["candidates"]]
                ev_map = {x["tag"]: x["evidence"] for x in inp["candidates"]}
                prev_d = (inp["prev_driver"] or {}).get("driver")
                drv = rule_driver(c_list, ev_map, news_text, inp["core_tag_counts"], prev_d, inp["h"])
                valid_out[c] = {
                    "code": c,
                    "driver": drv,
                    "driver2": None,
                    "basis_type": "continue" if prev_d and drv == prev_d else "resonance",
                    "basis": "规则兜底：主线延续/核心共振",
                    "source": "rule",
                }
                rule_cnt += 1

        for st in ladder:
            rec = valid_out[st["code"]]
            ordered_stocks.append(rec)
            if rec.get("driver"):
                recent_hist[st["code"]] = {
                    "date": day,
                    "driver": rec["driver"],
                    "driver2": rec.get("driver2"),
                    "basis": rec.get("basis") or "",
                }

    for c in ctx["empty_codes"]:
        ordered_stocks.append(
            {"code": c, "driver": None, "driver2": None, "basis_type": None, "basis": "", "source": "llm"}
        )

    out_doc = {"trade_date": day, "mode": "core_ladder_v2", "stocks": ordered_stocks}
    p.write_text(json.dumps(out_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"trade_date": day, "stocks": len(ordered_stocks), "rule_fallback": rule_cnt}


async def run_month_seq(month: str) -> list[dict]:
    days = _load_month_days(month)
    if not days:
        return []
    hist = _seed_recent_history(days[0])
    out = []
    for d in days:
        out.append(await process_day(d, hist))
    return out


if TARGET_DATE:
    phase(f"Core Ladder Driver Attribution ({TARGET_DATE})")
    hist = _seed_recent_history(TARGET_DATE)
    r = await process_day(TARGET_DATE, hist)
    log("Done:", json.dumps(r, ensure_ascii=False))
elif MONTHS:
    phase(f"Core Ladder Driver Attribution ({MONTHS[0]}..{MONTHS[-1]})")
    log(f"Running {len(MONTHS)} monthly sequential pipelines in parallel (refresh={REFRESH})")
    all_res = await parallel(MONTHS, run_month_seq)
    flat = [item for sub in all_res for item in sub]
    tot_stocks = sum(x.get("stocks", 0) for x in flat)
    tot_fb = sum(x.get("rule_fallback", 0) for x in flat)
    log(f"Completed {len(flat)} days, core_stocks={tot_stocks}, rule_fallback={tot_fb}")
else:
    m = MONTH or "2026-11"
    phase(f"Core Ladder Driver Attribution ({m})")
    res_list = await run_month_seq(m)
    log("Done:", json.dumps(res_list, ensure_ascii=False))
