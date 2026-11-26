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
                                "revenue_pct": {"type": "number"},
                                "evidence": {"type": "string"},
                            },
                            "required": ["l1", "revenue_pct", "evidence"],
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
                    "static_tags", "dynamic_tags", "ma_events",
                ],
            },
        },
    },
    "required": ["shard_id", "stocks"],
}

RULES_PROMPT = f"""你是A股超短线纯净题材库首席研判专家（只读模式，直接通过 finish 返回JSON）。
【绝对指令】本分片全部股票的完整未截断客观证据（含 F10 经营评述、核心题材、公告原文、近年涨停轨迹）已100%附在下方，**严禁调用任何工具（禁止 read_file / run_command 等）**，通读全文后一次性输出结构化 JSON！

【方案 A 硬铁律：静态死卡财务线人人平等 + 动态严格 1 年有效】
1. static_tags（“我一直有” · 客观财务铁尺，**零特权！仅归 25 个一级大类 L1，单股 1~4 条、每个 L1 唯一**）：
   25个唯一允许 L1：{json.dumps(TAXONOMY["l1_list"], ensure_ascii=False)}
   - **唯一准入硬门槛**：最新一期或上年报分产品/分行业营收占比 **>= 5%**（或营收明确 **>= 2亿元**且占比 > 0，并必须在 evidence 写出具体金额如 `2.50亿元`），**`revenue_pct` 必填客观正数，严禁 `null` 或 `0`**！
   - **零特权**：金螳螂洁净室(1%)、全筑EUV/边缘算力(0%)、九阳参股深思考(7.92%无并表营收)、顺钠AIDC变压器、0%电力、1~2%边角料、2016旧样机**一律不准进 `static_tags`**！
   - **核心行业映射铁律**：
     - **PCB（印制电路板）、覆铜板（CCL）、电子铜箔、光模块/CPO、光纤光缆** 一律归入 **`通信`**（若IC封装载板单独拆分 >=5% 归 `芯片`；`消费电子` 专指手机/PC/耳机/AI眼镜/显示面板/终端组装与专属零组件，严禁把 PCB/覆铜板丢进消费电子！）。
     - **`AI应用`（替代原 `软件`）分类铁律**：AI 硬件 5 大类为 `芯片`/`算力`/`通信`/`消费电子`/`机器人`，AI 软件静态大类为 **`AI应用`**（已废除 `软件`）。纯软件/大模型/AI智能体/数据标注/SaaS/信创及通用政务企业数字化集成软件营收占比 `>= 5%`（或 `>= 2亿元`）**直接归静态 `AI应用`**，严禁再重复挂动态 `AI应用`；强垂直依附单一实体行业的专用软件回流对应垂直大类（金融IT→`金融`、电网自动化→`电力`、北斗/ICT软件→`通信`、军工信息化→`军工`、医疗IT→`医药`、工业传感/工厂自动化→`机器人`）；非软件主业但近1年有真实 AI 应用落地的跨界股继续挂 **`dynamic_tags: AI应用`**。
     - **`工业设备` 严格兜底分流铁律**：减速器/伺服系统/丝杠/微型传动/传感器/机器视觉/工业机器人与柔性自动化产线→**直接归静态 `机器人`**；工程机械/水泥矿山辊压机/电梯/建材装备→`基建`；油气钻采管材/油气阀门/空分压缩机→`石油`或`化工`；采煤机→`煤炭`；轨交装备/船舶海工→`交运`；农机→`农业`；缝纫/包装/制冷→`消费`；锂电/光伏/芯片专用设备→各自赛道；**`工业设备`** 仅收容无法归入其余 24 个具体赛道的跨行业通用机床/工业母机、液压泵阀、注塑机、紧固件、焊材、通用输送设备（严禁再膨胀成大杂烩！）。
     - 固态电池->`锂电`、光刻胶/洁净室设备/先进封装->`芯片`、智能驾驶->`汽车`、AIDC/算力租赁->`算力`、冰雪/免税/零售->`消费`、水产/猪肉/种业->`农业`。

2. dynamic_tags（“市场正在炒作” · **严格 1 年有效期，近 1 年无最新确认/催化的过期不看**）：
   - 允许填两类词：① **15 个标准跨界/字辈分组** {json.dumps(TAXONOMY["dynamic_groups"], ensure_ascii=False)}（或真正在盘面多股共振走出来的 `XX字辈`）；② **上述 25 个 L1 大类词**（专门收容占比 `< 5%` 但近 1 年内有真实实体/量产产品/控股子公司/达标热股参股(直持>=3%或穿透>=2%)且市场真正在炒的副业/参股，如金螳螂->`芯片`、全筑->`芯片`/`算力`、九阳->`机器人`、顺钠->`算力`、高速算力PCB->`算力`、传媒/消费AI落地->`AI应用`；**严禁与自身 `static_tags` L1 重名**！）。
   - **有效期 1 年铁律**：`from_date` 必须填 `YYYY-MM-DD` 格式的**近 1 年内最近一次有效确认日**（最新定期报告/2025-11-26之后公告/调研/涨停实锤，必须 **>= 1年前日期**），**超过 1 年无新进展/新催化的直接删除，绝不保留陈年老公告！**
   - 严禁自造单个细分小词，严禁塞入任何并购重组/控股权变更；单股现行（to_date=null）严格 **<= 4 条**。
   - **`dynamic: AI应用` 纯度硬闸门（只认对外商业化 AI 产品/内容/服务）**：必须拥有**独立对外商业化交付/收费的 AI 软件、AI 内容或 AI 智能体产品**（商业化 AI 漫剧/短剧/AIGC平台/GEO营销SaaS/AI游戏、独立收费交付的 AI医疗/金融/教育/行业 Agent 软件、独立销售的 AI 陪伴玩具）才可进 `dynamic: AI应用`；**一刀切剔除三大类噪音**：① 设备/产线自带 AI 算法（产线视觉质检、电梯/色选机/搅拌站 AI 功能、照明安防摄像识别、工控运维平台）；② 消费硬件与端侧 AI 硬件（AI床垫/按摩椅/电视、AI眼镜/AIPC/AI NAS、端侧AI芯片与通信模组）；③ 内部接 DeepSeek 赋能主业（客服/文案/设计/导购小程序/出版校对/湿实验辅助）或仅实控人关联方涉 AI。

3. ma_events（**仅限当前筹划中/进行中**的并购重组与控股权拟变更 — **必须写明重组对象！**）：
   event_type：{json.dumps(TAXONOMY["ma_event_types"], ensure_ascii=False)}
   - **已完成直接并入 `static_tags`、已终止/黄了就是没有（绝对不要写进 `ma_events`！）**，本表只留仍在进行中/筹划中/承诺待注入的事项。
   - target_name 必须写清楚拟收购/拟置入资产名或拟受让新实控方（如 `海南免税资产注入预期`、`北京华著智算85%股权`；控股权拟转让暂未公开受让方写 `控制权拟协议转让(未定受让方)`）；
   - target_l1：重组对象所属 25 个 L1（如拟买算力/半导体公司填 `算力`/`芯片`，仅控股权变更未定注入标的填 `null`）。

4. 【直接剔除红线（不入库、不输出排雷表）】
   下列 4 类噪音**直接剔除，不给任何标签**（不用单独列出；仅遇到市场热传的重大官方辟谣如否认资产注入/华为合作时，可在 `audit_notes` 里顺手带一句备忘）：
   - **彻底不涉及**：公告/澄清/问询函彻底否认无业务无合作（**严禁凭免责声明前半句“不从事核心产业”把低占比硬壁垒配套误杀掉！**）。
   - **仅客户需求**：无壁垒通用泛服务/纯分销（给发射场或机房盖办公楼食堂、办展、纯品牌代理分销、通用外壳/门禁/索具）。
   - **微量参股**：基金穿透 < 2%、直持 < 1% 或无热度地方小农商/城商行。
   - **脏标签**：行情软件强贴的壳词、业绩增长（一季报/中报/三季报增长）、超跌、ST摘帽、次新股、陈年僵尸概念。

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
