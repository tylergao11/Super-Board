"""Pure-stdlib run_workflow orchestrator for Super-Board zero-truncation tagging."""
import json
import sys
from pathlib import Path

ROOT = Path(args.get("root", r"C:\Ai\Super-Board")) if "args" in dir() else Path(r"C:\Ai\Super-Board")
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from common import load_taxonomy, validate_record  # noqa: E402
from build_db import upsert_from_tagged  # noqa: E402

TAXONOMY = load_taxonomy(ROOT / "taxonomy.json")
SHARD_DIR = ROOT / "data/shards"
TAGGED_DIR = ROOT / "data/tagged"
TAGGED_DIR.mkdir(parents=True, exist_ok=True)

PREFIX = args.get("prefix", "verify_70") if "args" in dir() else "verify_70"
WAVE_SIZE = int(args.get("wave_size", 40)) if "args" in dir() else 40

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
                    "static_tags": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "l1": {"type": "string"},
                                "weight": {"type": "string"},
                                "revenue_pct": {"type": ["number", "null"]},
                                "evidence": {"type": "string"},
                            },
                            "required": ["l1", "weight", "evidence"],
                        },
                    },
                    "dynamic_tags": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "group_name": {"type": "string"},
                                "from_date": {"type": "string"},
                                "to_date": {"type": ["string", "null"]},
                                "evidence": {"type": "string"},
                            },
                            "required": ["group_name", "from_date", "evidence"],
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
                                "status": {"type": "string"},
                                "from_date": {"type": "string"},
                                "to_date": {"type": ["string", "null"]},
                                "evidence": {"type": "string"},
                            },
                            "required": ["event_type", "target_name", "status", "from_date", "evidence"],
                        },
                    },
                    "exclusions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "tag": {"type": "string"},
                                "reason_type": {"type": "string"},
                                "evidence": {"type": "string"},
                                "evidence_date": {"type": ["string", "null"]},
                            },
                            "required": ["tag", "reason_type", "evidence"],
                        },
                    },
                    "audit_notes": {"type": "string"},
                },
                "required": [
                    "code", "name", "province", "controller_type",
                    "static_tags", "dynamic_tags", "ma_events", "exclusions",
                ],
            },
        },
    },
    "required": ["shard_id", "stocks"],
}

RULES_PROMPT = f"""你是A股超短线纯净题材库首席研判专家（只读模式，直接通过 finish 返回JSON）。
【绝对指令】本分片全部股票的完整未截断客观证据（含 F10 经营评述、核心题材、公告原文、近年涨停轨迹）已100%附在下方，**严禁调用任何工具（禁止 read_file / run_command 等）**，通读全文后一次性输出结构化 JSON！

【四大核心表与严格词典】
1. static_tags（“我一直有” · 只归 **25 个静态一级大类 L1**，可多个但**每个 L1 最多一条**，严禁 `xx/xx` 或 `芯片(洁净室)` 等嵌套词！具体产品与占比全写进 evidence）：
   25个唯一允许 L1：{json.dumps(TAXONOMY["l1_list"], ensure_ascii=False)}
   分量 weight：{json.dumps(TAXONOMY["static_weights"], ensure_ascii=False)}
   - "主营"：分产品或分行业营收占比 >= 10%（或 >= 5% 且 >= 2.5 亿元）的长期核心业务，至少 1 条；若最新一期产品表缺拆分占比，回退采信行业表或上年报真实占比。
   - "副业"：占比 < 10% 但自身确有子公司/产线/产品/硬壁垒配套（如金螳螂子公司金柏瑞半导体洁净室 ~1% -> l1="芯片", weight="副业"；日发精机SK76丝杠磨床 -> l1="机器人", weight="副业"；顺钠股份AIDC干式变压器 -> l1="算力", weight="副业"；固态电池电解质/负极材料 -> l1="锂电", weight="副业"）。
   - "参股"：二维红线达标股权——直接持股 **>= 3%**（或穿透 >= 2%）且标的是市场核心硬科技/AI/机器人/芯片/航天/券商热点实体（如九阳股份直持深思考7.92% -> l1="机器人", weight="参股"），或直持 **>= 10%** 产业联营实体（如重仓参股矿企/半导体公司）。
   **核心归纳铁律（静先动后）**：凡能归入 25 大 L1 的细分（固态电池->锂电、光刻胶/洁净室/先进封装/GPU->芯片、电子皮肤/丝杠磨床/深思考->机器人、智能驾驶->汽车、AIDC/液冷/算力租赁->算力、冰雪/免税/零售->消费、水产/猪肉/种业->农业），**必须直接归入对应 L1 的 static_tags，严禁在 dynamic_tags 里新开单行业小马甲！**

2. dynamic_tags（“市场正在炒作” · **仅限 25 个 L1 碰不到的跨行业动态分组**）：
   优先复用：{json.dumps(TAXONOMY["dynamic_groups"], ensure_ascii=False)}
   （如遇全新跨多行业题材可新起 <=8 字简短分组名，否则严禁乱开！）
   **严禁塞入 dynamic_tags**：① 25 个 L1 本身或单个 L1 细分名（固态电池/光刻胶/洁净室/人形机器人/算力租赁/冰雪产业/GPU/电子皮肤等）；② 任何并购重组/控股权变更事项！
   单股现行（to_date=null）dynamic_tags 严格 **<= 4 条**，纯正单行业股可为 `[]`。

3. ma_events（并购重组/控股权事项独立表 — **必须写明重组对象！**）：
   event_type：{json.dumps(TAXONOMY["ma_event_types"], ensure_ascii=False)}
   status：{json.dumps(TAXONOMY["ma_statuses"], ensure_ascii=False)}
   - target_name 必须写清楚收购/置入资产名或受让新实控方（如 `开曼铝业(三门峡)99.44%股权`、`华鲲振宇`、`海南免税资产注入预期`；若控股权转让暂未公开受让方写 `控制权拟协议转让(未定受让方)`）；
   - target_l1：重组对象所属 25 个 L1（如拟买半导体公司写 `芯片`，仅控股权变动未定注入标的填 `null`）；
   - 已终止的 2024-2026 并购/控股权筹划：status="已终止" 且 **必填 to_date=终止公告日**；
   - 已完成并表转正且营收达标的并购，除保留 status="已完成" 事件外，静态 static_tags 也相应更新为新主业或副业。

4. exclusions（4类显性排雷 · tag 必须为<=20字简短名称，严禁与自身 static_tags L1 重名！）：
   reason_type：{json.dumps(TAXONOMY["exclusion_reasons"], ensure_ascii=False)}
   - "不涉及"：公告/澄清/问询函彻底否认无业务无合作（**严禁凭免责声明前半句“不从事核心产业”把低占比硬壁垒配套误杀进来！**）。
   - "仅客户需求"：无壁垒通用泛服务/纯分销（给发射场或机房盖办公楼食堂、办展、纯品牌代理分销、通用外壳/门禁/索具）。
   - "微量参股"：基金穿透 < 2%、直持 < 1% 或无热度地方小农商/城商行。
   - "脏标签"：软件强贴的壳词、业绩增长、陈年僵尸概念。

5. 基础档案：{json.dumps(TAXONOMY["provinces"], ensure_ascii=False)}；controller_type：{json.dumps(TAXONOMY["controller_types"], ensure_ascii=False)}。
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
            if validate_record(rec, ev_map.get(c), TAXONOMY):
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
                errs.extend(validate_record(rec, ev_by_code.get(c), TAXONOMY))
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
            final_errs.extend(validate_record(rec, ev_by_code.get(str(rec.get("code") or "")), TAXONOMY))
        if final_errs:
            return {"shard_id": shard_id, "ok": False, "error": str(final_errs[:8])}

        res["shard_id"] = shard_id
        (TAGGED_DIR / f"{shard_id}.json").write_text(json.dumps(res, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return {"shard_id": shard_id, "ok": True, "count": len(res["stocks"])}
    except Exception as exc:
        return {"shard_id": shard_id, "ok": False, "error": f"{type(exc).__name__}: {exc}"}


phase(f"Super-Board Tagging ({PREFIX})")
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

phase(f"Compile Super-Board DB ({PREFIX})")
summary = upsert_from_tagged(PREFIX)
log("Compile done:", json.dumps(summary, ensure_ascii=False))
