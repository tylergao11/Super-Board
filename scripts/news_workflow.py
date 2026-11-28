"""Pure-stdlib run_workflow script to distill intraday objective hot news per trading day."""
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(args.get("root", r"c:\Ai\Super-Board")) if "args" in dir() else Path(r"c:\Ai\Super-Board")
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from common import extract_intrinsic_tags, is_zibei_tag  # noqa: E402
from driver_rules import VOCAB_SET, candidates, format_region, is_event_theme  # noqa: E402

DB_PATH = ROOT / "data/super_board.sqlite"
RAW_NEWS_DIR = ROOT / "data/raw_news"
TARGET_DATE = str(args.get("date") or "").strip() if "args" in dir() else ""
MONTH = str(args.get("month") or "2026-11").strip() if "args" in dir() else "2026-11"
OUT_PATH = ROOT / (f"data/hot_news/day_{TARGET_DATE}.json" if TARGET_DATE else f"data/hot_news/{MONTH}.json")

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "trade_date": {"type": "string"},
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "rank": {"type": "integer"},
                    "headline": {"type": "string"},
                    "detail": {"type": "string"},
                    "hit_count": {"type": "integer"},
                    "theme": {"type": ["string", "null"]},
                    "codes": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["rank", "headline", "detail", "hit_count", "theme", "codes"],
            },
        },
    },
    "required": ["trade_date", "items"],
}

RULES_PROMPT = """你是A股游资超短线日内盘面消息提炼专家（只读模式，严禁调用任何工具，直接通过 finish 返回结构化 JSON）。
【最高定位】本库按 **A 股游资与超短线资金的炒作视角** 归类题材（区别于传统申万/东财行业归类），归口板块时以盘面游资真实共识与资金共振方向为准。

下方提供某一交易日（`trade_date`）两份客观材料：
1) `stocks`：当日全部涨停股票（代码、名称、板数、`region` 省/市/国资归属及自家纯净标签 `tags`）；
2) `intraday_news`（如有）：**严格卡在 `(上一交易日 15:00, 当日 15:00]` 窗口内的东财焦点加红快讯**（隔夜外盘/晚间重磅政策 + 早盘/盘中突发催化）。

请融合这两份材料，去重提炼出 **6 到 10 条真正驱动当日日内盘面（截止当日 15:00 收盘）的客观热门消息/催化事件**，按当日盘面影响力 / 带动热度（`hit_count`）从高到低排序（`rank` 从 1 开始连续编号）：

【提炼铁律】
1. **严格只看日内（截止 15:00），绝不做次日预期**：只提炼推动当天隔夜开盘、早盘或盘中拉升的消息/政策/突发事件/情绪暗线。**严禁写入 15:00 收盘后的监管函、晚间公告、次日展望或“当日涨停复盘汇总帖（XX只股涨停/几连板）”！**
2. **优先抓真正带起日内异动的消息**：政策发布（如部委文件/6G/AI出海）、监管批准（如SpaceX星座）、隔夜外盘/大厂突发（如美光/英伟达/华为HBM/交期拉长）、权威媒体报道、行业涨价/爆单、前夜已公告并触发当日日内涨停的重磅并购/要约，以及满足“消息报道 + 盘面响应”双印证的**玄学字辈暗线**与**地域行情暗线**。
3. **`headline`（<= 28字）**：高度凝练的事件标题，建议尽量带出关键时点词（如 `午后突发：英伟达暂停东南亚芯片出货`、`隔夜FCC批SpaceX百万颗卫星星座`、`盘中：八部门支持AI大模型及云计算出海`、`央视财经：国产冰雪装备出口爆单`、`2027农历羊年名称异动暗线`）。
4. **`detail`（1句话客观摘要）**：写明具体事件内容、时间点与出处，并在句末括号内点明当日日内受其催化的代表涨停/异动股（无则写所涉方向）。
5. **`theme`**：该消息对应的唯一核心板块，取自以下两类之一（跨行业综合宏观/贸易/资本市场动态填 `null`）：
   - **标准词表（33 词）**：23 个一级赛道 + 10 个跨界组（含 `端侧AI`）；单股或单一行业的并购重组快讯必须穿透至被并购/注入标的所属的真实赛道（如收购存储器→`"芯片"`、收购覆铜板→`"通信"`、注入热电→`"电力"`、收购车联网→`"智能驾驶"`、收购 AI 眼镜/终端→`"端侧AI"`）；
   - **常驻固有属性（无时效性，盘面发酵即提炼）**：
     - **央国企改革/市值管理主线（`"国企改革"`）**：仅当出现国家级/国资委央国企改革、市值管理、央企整合重组等政策催化且盘面多只跨行业央国企同步涨停共振时提炼 `theme = "国企改革"` 并列出命中代码（单只国企并购按标的赛道穿透）；
     - **经典字辈（`华字辈`/`东方字辈`/`龙字辈`/`金字辈`/`羊字辈`，及其他突发新字辈 `XX字辈`）**：当日快讯点名，或高标龙头带动多只跨行业涨停股以同一字辈/谐音集体共振发酵时提炼，并把命中的涨停股代码填入 `codes`；
     - **常驻地域（直接用省/市简称，不加“本地”二字）**：当该省或核心城市出现政策、重磅事件或媒体报道，或盘面该地域多只不同行业涨停股明显抱团共振时提炼（如 `"上海"`、`"深圳"`、`"杭州"`、`"苏州"`、`"海南"`、`"福建"`、`"西藏"`），把响应代码填入 `codes`；
   - **临时政策级暗线（`"并购"`）**：仅当出现国家级/监管级重磅并购重组新政，且盘面多只跨行业并购标的同步批量涨停共振时激活 `theme = "并购"`；常态下零星个股并购穿透归入标的所属真实赛道。
6. **`codes`**：受该消息在当日日内直接带动的涨停股代码数组（`string[]`），所有代码必须严格来自输入 `stocks` 的 `code`。
7. **严禁充数的假消息**：严禁把日常经营背景、常规业绩增长、指数日常波动（如“恒生科技涨3%”）或泛泛而谈的宏观数据当成热门消息！
"""


def _load_days_payload(target_date: str, month: str) -> list[dict]:
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    if target_date:
        days = [target_date]
    else:
        days = [
            r[0]
            for r in conn.execute(
                "SELECT DISTINCT trade_date FROM daily_limit_pool WHERE trade_date LIKE ? ORDER BY trade_date ASC",
                (f"{month}-%",),
            ).fetchall()
        ]
    out = []
    for d in days:
        rows = conn.execute(
            """
            SELECT p.code, p.name, p.board_height, s.province, s.city, s.controller_province
            FROM daily_limit_pool p
            LEFT JOIN stocks s ON p.code = s.code
            WHERE p.trade_date = ?
            ORDER BY p.board_height DESC, p.first_limit_time ASC, p.code ASC
            """,
            (d,),
        ).fetchall()
        raw_p = RAW_NEWS_DIR / f"{d}.json"
        intraday_news = []
        if raw_p.exists():
            raw_doc = json.loads(raw_p.read_text(encoding="utf-8"))
            raw_items = raw_doc.get("items") or []
            intraday_news = [
                {"time": it.get("time", ""), "title": it.get("title", ""), "summary": it.get("summary") or ""}
                for it in raw_items
            ]
        out.append(
            {
                "trade_date": d,
                "intraday_news": intraday_news,
                "stocks": [
                    {
                        "code": r[0],
                        "name": r[1],
                        "h": r[2],
                        "region": format_region(r[3], r[4], r[5]),
                        "zibei": [
                            t for t, _ in extract_intrinsic_tags(r[0], r[1], r[3], r[4], r[5]) if is_zibei_tag(t)
                        ],
                        "tags": candidates(conn, r[0], d, include_intrinsic=False),
                    }
                    for r in rows
                ],
            }
        )
    conn.close()
    return out


def _validate_day(day: str, doc: dict, valid_codes: set[str]) -> list[str]:
    errs = []
    if doc.get("trade_date") != day:
        errs.append(f"trade_date must be {day}, got {doc.get('trade_date')!r}")
    items = doc.get("items")
    if not isinstance(items, list) or not (1 <= len(items) <= 12):
        errs.append("items must have 1..12 entries")
        return errs
    for idx, it in enumerate(items, 1):
        hl = str(it.get("headline") or "").strip()
        dt = str(it.get("detail") or "").strip()
        if not hl or len(hl) > 40:
            errs.append(f"item[{idx}] invalid headline length: {hl!r}")
        if not dt:
            errs.append(f"item[{idx}] empty detail")
        th = it.get("theme")
        if th is not None:
            th_s = str(th).strip()
            if not th_s:
                it["theme"] = None
            elif th_s not in VOCAB_SET and not is_event_theme(th_s):
                errs.append(f"item[{idx}] invalid theme {th_s!r} (must be null, in VOCAB, 'XX字辈', or 'XX本地')")
        codes = it.get("codes")
        if not isinstance(codes, list):
            errs.append(f"item[{idx}] codes must be list")
        else:
            bad_codes = [c for c in codes if str(c) not in valid_codes]
            if bad_codes:
                errs.append(f"item[{idx}] codes not in daily pool: {bad_codes[:5]}")
    return errs


async def distill_day(payload: dict) -> dict:
    day = payload["trade_date"]
    valid_codes = {s["code"] for s in payload["stocks"]}
    prompt = (
        RULES_PROMPT
        + f"\n现在请提炼 {day}（共 {len(payload['stocks'])} 只涨停，{len(payload['intraday_news'])} 条日内焦点快讯）的当日热门消息：\n"
        + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    )
    a = agent(role=f"News {day}", type_name="research")
    res = await a(prompt, OUTPUT_SCHEMA)
    errs = _validate_day(day, res, valid_codes)
    if errs:
        res = await a("输出不符合要求，请修正后重新输出：\n" + "\n".join(errs), OUTPUT_SCHEMA)
        errs = _validate_day(day, res, valid_codes)
    del a
    if errs:
        raise RuntimeError(f"{day} hot news validation failed: {errs}")
    for idx, it in enumerate(res["items"], 1):
        it["rank"] = idx
    return res


label = TARGET_DATE or MONTH
phase(f"Distill Intraday Hot News ({label})")
day_payloads = _load_days_payload(TARGET_DATE, MONTH)
log(f"Target={label}, days={len(day_payloads)}")
results = await parallel(day_payloads, distill_day)

OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
OUT_PATH.write_text(
    json.dumps({"target": label, "days": results}, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
log("Hot news written:", str(OUT_PATH), "days=", len(results))
