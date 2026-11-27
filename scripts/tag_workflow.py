"""Pure-stdlib run_workflow orchestrator for Super-Board v2 full-dynamic tagging."""
import json
import sys
from pathlib import Path

ROOT = Path(args.get("root", r"d:\Super-Board")) if "args" in dir() else Path(r"d:\Super-Board")
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from common import load_taxonomy, validate_record  # noqa: E402
from build_db import upsert_from_tagged  # noqa: E402

TAXONOMY = load_taxonomy(ROOT / "taxonomy.json")
SHARD_DIR = ROOT / "data/shards"
TAGGED_DIR = ROOT / "data/tagged"
TAGGED_DIR.mkdir(parents=True, exist_ok=True)

PREFIX = args.get("prefix", "day_latest") if "args" in dir() else "day_latest"
WAVE_SIZE = int(args.get("wave_size", 40)) if "args" in dir() else 40
MIN_TAG_DATE = str(args.get("min_tag_date", "2025-11-26")) if "args" in dir() else "2025-11-26"
SKIP_COMPILE = bool(args.get("skip_compile", False)) if "args" in dir() else False

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "shard_id": {"type": "string"},
        "stocks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "code": {"type": "string"},
                    "name": {"type": "string"},
                    "province": {"type": "string"},
                    "city": {"type": ["string", "null"]},
                    "controller_type": {"type": "string"},
                    "overseas_pct": {"type": ["number", "null"]},
                    "tags": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "tag": {"type": "string"},
                                "from_date": {"type": "string"},
                                "evidence": {"type": "string"},
                            },
                            "required": ["tag", "from_date", "evidence"],
                        },
                    },
                    "ma_events": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "event_type": {"type": "string"},
                                "target_name": {"type": "string"},
                                "target_l1": {"type": ["string", "null"]},
                                "from_date": {"type": "string"},
                                "evidence": {"type": "string"},
                            },
                            "required": ["event_type", "target_name", "from_date", "evidence"],
                        },
                    },
                    "audit_notes": {"type": "string"},
                },
                "required": [
                    "code", "name", "province", "controller_type",
                    "tags", "ma_events",
                ],
            },
        },
    },
    "required": ["shard_id", "stocks"],
}

RULES_PROMPT = f"""你是A股超短线全动态纯净题材库首席研判专家（只读模式，直接通过 finish 返回JSON）。
【绝对指令】本分片全部股票的完整未截断客观证据（含 F10 经营评述、核心题材、公告原文、近年涨停轨迹）已100%附在下方，**严禁调用任何工具（禁止 read_file / run_command 等）**，通读全文后一次性输出结构化 JSON！

【Super-Board v2 全动态铁律：彻底废除静态/动态分裂，以“跨领域想象力（底层能力同源复用）”为第一性原理】
1. `tags`（全动态纯净题材唯一列表，**不设死板的 4 条上限：有几个实锤可炒的真逻辑就如实给几个，绝不人为硬砍真实题材，也绝不拿废话凑数；按当下市场核心度与近期催化强度从高到低排序**）：
   - **唯一允许词表（40 个标准词 + 盘面多股共振 `XX字辈`）**：
     - 25 个一级赛道：{json.dumps(TAXONOMY["l1_list"], ensure_ascii=False)}
     - 15 个跨界/字辈分组：{json.dumps(TAXONOMY["dynamic_groups"], ensure_ascii=False)}
   - **关键归口铁律（严禁自造细分碎词）**：
     - 洁净室、光刻胶/光刻机、先进封装、存储/HBM、半导体设备材料 → **`芯片`**；
     - 液冷、AIDC、算力租赁、算力电源、服务器/算力基础设施 → **`算力`**；
     - 光模块/CPO、PCB、覆铜板(CCL)、电子铜箔、光纤光缆、高速连接 → **`通信`**（IC 封装载板归 `芯片`；`消费电子` 专指手机/PC/穿戴/显示面板及终端精密件）；
     - 减速器/伺服/丝杠/微型传动/传感视觉/工业与人形机器人及自动化产线 → **`机器人`**；通用机床/液压/注塑机/紧固件/焊材兜底归 **`工业设备`**；
     - 纯软件/大模型/AI智能体/SaaS/信创及对外商业化 AI 产品内容服务 → **`AI应用`**；强垂直行业专用软件归对应行业（金融IT→`金融`、电网自动化→`电力`、军工信息化→`军工`、医疗IT→`医药`）。
   - **第一性原理（跨领域想象力 / 底层能力同源复用）**：
     - **不卡财报 5% 门槛，允许当前营收 0% 或 1%，允许外围配套、材料、结构件、洁净室、专用与后道组装/测试设备**（全行业一视同仁，如：汽车/消费电子精密件→`机器人`、铝型材→`光伏`/`算力`/`机器人`、洁净室→`芯片`、精密自动组装→`通信`、制冷/配电→`算力`）。
     - 只要**公司产品/工艺/产线/资质/实体可向目标赛道输出**，且 F10/公告/投关/互动易有**实质动作**（产品、送样、产线应用、子公司/参股实体、产业合作或近 1 年盘面催化）→ **一律算有**。
   - **去僵尸旧壳原则**：
     - 本身仍在被炒作的主业正常保留进 `tags`；
     - 已转型且早已被市场抛弃、近 1 年毫无盘面炒作价值的**旧壳主业**（如顺灏的烟标消费、哈森的女鞋消费、大胜达的纸箱消费、全筑的传统家装基建），不再硬塞进 `tags` 占位置，仅在 `audit_notes` 说明主营底色即可。
   - **`from_date` 与 1 年有效期**：
     - 必填 `YYYY-MM-DD`，取最近一次确认/公告/涨停催化/定期报告日（必须 `>= {MIN_TAG_DATE}`）；超过 1 年既无产业进展也无盘面催化的陈年老概念直接淘汰。

2. `ma_events`（**仅限当前筹划中/进行中**的并购重组与控股权拟变更，与 `tags` 严格分离）：
   - event_type：{json.dumps(TAXONOMY["ma_event_types"], ensure_ascii=False)}
   - 已完成并入 `tags`，已终止直接忽略不写；必写 `target_name`、`target_l1`（未定标的填 `null`）、`from_date`、`evidence`。

3. 【唯一 4 条硬剔除红线（直接剔除不给标签）】
   - **官方辟谣/彻底不涉及**：仅当公告明确斩钉截铁否认**“未开展、无相关技术储备、无相关布局打算、无任何合作关系”**时才剔除！**【严防被免责套话误杀】**：A股异动/风险提示公告极其喜欢写“当前某某业务无收入 / 占比极低 / 尚未形成规模销售 / 尚处于早期培育或研发阶段 / 对本年度业绩无重大影响 / 公司不直接从事整机本体”——**这绝不代表公司没在做或没打算做！**只要公司确有相关配套产品、研发试制、送样验证、产线适配、设立子公司/参股实体、战略合作或明确产业布局打算，**一律算【有】，绝不误杀！**
   - **纯买家内部赋能**：企业内部接 DeepSeek 写文案/客服/画图/辅助研发，或买机器人放自己仓库自用（不是“我的东西往外输出”）；
   - **纯行政/生活泛服务**：给发射场/机房盖办公楼食堂公寓、物业、办展、常规绿电直供、纯品牌经销代理；
   - **软件脏词与陈年僵尸**：业绩增长、超跌、ST摘帽、次新股、以及超 1 年毫无新进展与催化的陈年概念。

4. 基础档案：{json.dumps(TAXONOMY["provinces"], ensure_ascii=False)}；controller_type：{json.dumps(TAXONOMY["controller_types"], ensure_ascii=False)}。
"""


def _is_valid(shard_id: str) -> bool:
    ev_p = SHARD_DIR / f"{shard_id}.json"
    out_p = TAGGED_DIR / f"{shard_id}.json"
    if not ev_p.exists() or not out_p.exists():
        return False
    try:
        ev_doc = json.loads(ev_p.read_text(encoding="utf-8"))
        out_doc = json.loads(out_p.read_text(encoding="utf-8"))
        ev_map = {s["code"]: s for s in ev_doc["stocks"]}
        got = set()
        for rec in out_doc.get("stocks", []):
            c = str(rec.get("code") or "")
            got.add(c)
            if validate_record(rec, ev_map.get(c), TAXONOMY, min_tag_date=MIN_TAG_DATE):
                return False
        return got == set(ev_map.keys())
    except Exception:
        return False


async def tag_shard(shard_id: str) -> dict:
    try:
        ev_doc = json.loads((SHARD_DIR / f"{shard_id}.json").read_text(encoding="utf-8"))
        stocks = ev_doc["stocks"]
        ev_by_code = {s["code"]: s for s in stocks}
        prompt = (
            RULES_PROMPT
            + f"\n现在请对分片 {shard_id} 的全部 {len(stocks)} 只股票逐一深审打标，严禁遗漏：\n"
            + json.dumps(stocks, ensure_ascii=False, separators=(",", ":"))
        )
        a = agent(role=f"Tag {shard_id}", type_name="research")
        res = await a(prompt, OUTPUT_SCHEMA)
        for _ in range(2):
            errs = []
            got = set()
            for rec in res.get("stocks", []):
                c = str(rec.get("code") or "")
                got.add(c)
                errs.extend(validate_record(rec, ev_by_code.get(c), TAXONOMY, min_tag_date=MIN_TAG_DATE))
            missing = sorted(set(ev_by_code.keys()) - got)
            if missing:
                errs.append(f"遗漏股票: {missing}")
            if not errs:
                break
            res = await a("校验未通过，请逐条修正后重新输出完整全部股票JSON：\n" + "\n".join(errs[:35]), OUTPUT_SCHEMA)
        del a

        final_errs = []
        got = {str(r.get("code") or "") for r in res.get("stocks", [])}
        missing = sorted(set(ev_by_code.keys()) - got)
        if missing:
            final_errs.append(f"missing: {missing}")
        for rec in res.get("stocks", []):
            final_errs.extend(validate_record(rec, ev_by_code.get(str(rec.get("code") or "")), TAXONOMY, min_tag_date=MIN_TAG_DATE))
        if final_errs:
            return {"shard_id": shard_id, "ok": False, "error": str(final_errs[:8])}

        res["shard_id"] = shard_id
        (TAGGED_DIR / f"{shard_id}.json").write_text(json.dumps(res, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return {"shard_id": shard_id, "ok": True, "count": len(res["stocks"])}
    except Exception as exc:
        return {"shard_id": shard_id, "ok": False, "error": f"{type(exc).__name__}: {exc}"}


phase(f"Super-Board v2 Full-Dynamic Tagging ({PREFIX})")
manifest = json.loads((SHARD_DIR / f"{PREFIX}_manifest.json").read_text(encoding="utf-8"))
all_shards = [s["shard_id"] for s in manifest["shards"]]
pending = [sid for sid in all_shards if not _is_valid(sid)]
log(f"Prefix={PREFIX}, total={len(all_shards)}, valid={len(all_shards)-len(pending)}, pending={len(pending)}")

failed = []
for i in range(0, len(pending), WAVE_SIZE):
    wave = pending[i : i + WAVE_SIZE]
    res_list = await parallel(wave, tag_shard)
    bad = [r for r in res_list if not r["ok"]]
    failed.extend(r["shard_id"] for r in bad)
    log(f"Wave {i//WAVE_SIZE+1}: ok={len(wave)-len(bad)}/{len(wave)}, failed={bad}")

if failed:
    log(f"Retrying {len(failed)} failed shards...")
    r_list = await parallel(failed, tag_shard)
    still_bad = [r for r in r_list if not r["ok"]]
    if still_bad:
        raise RuntimeError(f"Shards still failed after retry: {still_bad}")

if SKIP_COMPILE:
    log(f"Skipping DB compile for {PREFIX} (skip_compile=True); tagged shards ready.")
else:
    phase(f"Compile Super-Board v2 DB ({PREFIX})")
    summary = upsert_from_tagged(PREFIX)
    log("Compile done:", json.dumps(summary, ensure_ascii=False))
