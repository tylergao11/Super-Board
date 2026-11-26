"""Pure-stdlib run_workflow script for Scheme-A + 1-year dynamic + PCB->通信 stock cleanup audit."""
import json
import sys
from pathlib import Path

ROOT = Path(args.get("root", r"C:\Ai\Super-Board")) if "args" in dir() else Path(r"C:\Ai\Super-Board")
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from common import load_taxonomy, validate_record  # noqa: E402

TAXONOMY = load_taxonomy(ROOT / "taxonomy.json")
SHARD_DIR = ROOT / "data/shards"
OUT_DIR = ROOT / "data/audit_out"
OUT_DIR.mkdir(parents=True, exist_ok=True)

PREFIX = args.get("prefix", "scheme_a") if "args" in dir() else "scheme_a"
WAVE_SIZE = int(args.get("wave_size", 40)) if "args" in dir() else 40
MIN_DYN_DATE = str(args.get("min_dynamic_date", "2025-11-26")) if "args" in dir() else "2025-11-26"

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
                    "controller_type": {"type": "string"},
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
                    "audit_notes": {"type": "string"},
                },
                "required": ["code", "name", "province", "controller_type", "static_tags", "dynamic_tags", "audit_notes"],
            },
        },
    },
    "required": ["shard_id", "stocks"],
}

AUDIT_PROMPT = f"""你是 A股纯净题材库“方案A + 1年有效期 + 行业口径统一”专项审计官（只读模式，**严禁调用任何工具**，通读证据后直接通过 finish 返回 JSON）。

【本次清淤铁律：全部股票共用同一把尺子，绝不双标！】
1. **static_tags（静态 · 客观财务铁尺，单股 1~4 条，每个 L1 唯一）**：
   25个唯一允许 L1：{json.dumps(TAXONOMY["l1_list"], ensure_ascii=False)}
   - **唯一准入硬门槛**：严格核对 `latest_mix` / `annual_mix`，**只保留最新期（若缺失拆分或年报更完整可采信上年报）分产品/分行业营收占比 `>= 5%` 的真实业务**（或营收明确 **`>= 2亿元`** 且占比 `> 0`，此时 evidence 必须写出如 `2.50亿元`）。
   - **`revenue_pct` 必填具体正数（严禁 `null` 或 `0`）**！如果某只股同个 L1 对应多条财报子项（如化工90%+化肥5%），合并填其总占比。
   - **零特权清零**：
     - 占比 `0%`（如金牛化工电力0%）、`< 5%` 且 `< 2亿` 的边角料（如青山纸业1~2%环保/机械/农业）**一律踢出 `static_tags`**！
     - 低占比无拆分硬科技/参股（如金螳螂1%洁净室、全筑0% EUV/云阙智算、九阳7.92%参股深思考、顺钠AIDC变压器）**一律不准进 `static_tags`**（近1年有实体的去 `dynamic_tags`，没有的直接删）！
     - **陈年僵尸踢出**：仅出现在开盘啦历史涨停文案、但最新 F10（`latest_mix`、`business_review`、`core_conception`）与近 2 年公告完全查无实质业务的（如全筑股份 2016 智能划线机器人样机），**彻底删除**！
   - **PCB / 覆铜板核心纠偏（必看！）**：
     - **PCB（印制电路板）、覆铜板（CCL）、电子铜箔、光模块/CPO、光纤光缆** 营收占比 `>= 5%`，一律归入 **`通信`**（严禁丢进 `消费电子`！如骏亚科技、澳弘电子、金安国纪、沪电股份、嘉立创、宝鼎科技、贤丰控股、满坤科技等主营 PCB/覆铜板全改归 `通信`；深南电路/兴森科技单独拆分 `IC封装基板 >=5%` 归 `芯片`、其余 PCB 归 `通信`）。
   - **`AI应用`（替代原 `软件`）分类铁律**：
     - AI 硬件 5 大类为 `芯片`/`算力`/`通信`/`消费电子`/`机器人`；AI 软件静态大类为 **`AI应用`**（已废除 `软件`）。
     - 纯软件/大模型/AI智能体/数据标注/SaaS/信创及通用政务企业数字化集成软件（如常山北明、拓维信息、海天瑞声、易点天下、证通电子等）营收占比 `>= 5%`（或 `>= 2亿元`）**直接归静态 `AI应用`**，同时删除重复的动态 `AI应用`（严禁静动重名）。
     - 强垂直依附单一实体行业的专用软件/自动化系统归对应垂直大类：券商/银行金融IT（顶点软件、汇金科技、银之杰、楚天龙等）→ **`金融`**；电力/电网调度自动化软件（海得控制、中恒电气等）→ **`电力`**；北斗/ICT网络软件（司南导航、广脉科技等）→ **`通信`**；军工信息化/涉军网安（高凌信息等）→ **`军工`**；医疗IT（阳普医疗等）→ **`医药`**；工业传感器/工厂自动化软件（汉威科技、赛摩智能等）→ **`机器人`**。
     - 非软件主业但近 1 年有真实 AI 应用落地/催化的跨界股（如 `传媒`/`消费`/`医药`/`金融` 等，`AI应用` 营收 `< 5%`）继续放在 **`dynamic_tags: AI应用`**。
   - **`工业设备` 严格兜底分流铁律（严禁再膨胀！）**：
     - 已废除 `机械`，25大类现为 **`工业设备`** 严格兜底：减速器/伺服系统/丝杠/微型传动/传感器/机器视觉/工业机器人与柔性自动化产线（中大力德、兆威机电、雷赛智能、奥普特、安培龙、克来机电、派斯林等）**直接归静态 `机器人`**；
     - 工程机械/水泥矿山辊压机/电梯/建材装备（利君股份、南方路机、江顺科技、快意电梯等）归 **`基建`**；油气钻采管材/阀门/空分压缩机（山东墨龙、纽威股份、福斯达等）归 **`石油`** 或 **`化工`**；采煤机（林州重机、山东矿机）归 **`煤炭`**；轨交/船舶海工（今创集团、必得科技等）归 **`交运`**；农机（天鹅股份等）归 **`农业`**；缝纫/包装/制冷（杰克科技、冰山冷热、中捷资源等）归 **`消费`**；锂电/光伏/芯片/PCB专用设备（尚水智能、博杰股份、快克智能等）归对应具体赛道；
     - **`工业设备`** 仅收容无法归入其余 24 个具体赛道的跨行业通用工业母机/机床、液压泵阀、注塑机、紧固件、焊材、通用输送设备（如沈阳机床、泰瑞机器、腾达科技、大西洋、邵阳液压、和泰机电）。

2. **dynamic_tags（动态 · 严格 1 年有效期，`from_date >= {MIN_DYN_DATE}`，现行 <= 4 条）**：
   - 允许两类标准词：① 15个标准跨界/字辈分组 {json.dumps(TAXONOMY["dynamic_groups"], ensure_ascii=False)}（或盘面走出的 `XX字辈`）；② **25个 L1 大类词**（用于收容上述 `<5%` 但近1年内有明确实体[控股子公司/量产供货/直接>=3%或穿透>=2%热点参股]且市场在炒作的低占比方向，如金螳螂->`芯片`、全筑->`芯片`/`算力`、九阳->`机器人`、顺钠->`算力`、高速算力板/AI服务器PCB->`算力`、传媒/消费AI落地->`AI应用`；**严禁与自身 `static_tags` L1 重名**！）。
   - **1 年有效期铁律**：对 `current_dynamic` 中的每条历史动态标签（尤其是 `from_date < {MIN_DYN_DATE}` 的老标签），核查 F10（2025年报/2026中报）、2025-11-26 之后的公告或涨停轨迹里是否仍有明确实质落地或炒作催化：
     - **近 1 年确有新确认/催化**：保留并将 `from_date` 更新为最近一次确认/公告/涨停日期（必须 `>= {MIN_DYN_DATE}`）；
     - **仅靠 1 年前老公告/陈年概念撑着、近 1 年毫无实质进展**：**直接删除！**
   - `to_date` 设为 `null`（只输出仍有效且 `from_date >= {MIN_DYN_DATE}` 的条目，过期的直接删掉）。
   - **`dynamic: AI应用` 纯度硬闸门（只认对外商业化 AI 产品/内容/服务，严禁“万物皆可 AI+ 赋能”！）**：
     - **唯一准入**：必须拥有**独立对外商业化交付/收费的 AI 软件、AI 内容或 AI 智能体产品**（或独立运营的对外 AI 控股子公司）：① 商业化 AI 漫剧/短剧/AI原生电影/AIGC内容平台/AI营销投放SaaS(GEO)/AI核心玩法游戏；② 独立对外收费交付的垂类 AI 软件/智能体（AI医疗诊断注册证或医院中标产品、AI金融投研/券商软件、AI教育平台、独立对外 AI Agent/SaaS 服务）；③ 独立品牌对外销售的 AI 陪伴玩具/对话交互产品。
     - **三大类一刀切剔除（严禁保留在 `dynamic: AI应用`）**：
       1) **设备/产线自带 AI 算法**：工业产线 AI 视觉质检/噪声检测（克来机电）、色选机 AI 分选（泰禾智能）、电梯 AI 故障诊断（快意电梯）、搅拌站 AI 上料（南方路机）、工业机器人本体平台（埃斯顿）、照明/摄像/安防 AI 识别（海洋王/同为股份/维海德/安邦护卫）、电力/环保/油田设备运维系统（宏英智能/信通电子/德林海/神开股份/理工能科）；
       2) **消费硬件与端侧 AI 硬件**：AI 床垫/按摩椅（慕思股份/梦百合/奥佳华）、智能电视语音大模型（四川长虹）、AI眼镜/AIPC/AI NAS/播控硬件（康冠科技/亿道信息/润贝航科/卡莱特/奥拓电子/智微智能）、端侧AI芯片与通信模组（博通集成/汇顶科技/移远通信/美格智能/润欣科技）——此类属 AI 硬件（`消费电子`/`芯片`/`通信`/`算力`）或传统消费品；
       3) **内部降本增效 / 接 DeepSeek 赋能主业 / 空壳关联方**：企业内部接 DeepSeek 做在线客服/写营销文案/画设计图/做导购小程序/辅助出版校对/辅助药物湿实验（天威视讯/丽人丽妆/大胜达/华孚时尚/深赛格/皮阿诺/万事利/华阳国际/奥雅股份/读者传媒/凯撒文化/富春股份/药明康德/百普赛斯/近岸蛋白/华体科技/正和生态），以及上市公司本身无 AI 业务仅实控人关联方涉 AI（真爱美家）。
     - **范围纪律**：若本股只是 `dynamic: AI应用` 被上述闸门剔除，请保持其余合规的 `static_tags` 与其它合法 `dynamic_tags`。
   - **后道组装/测试/检测设备不贴下游大类铁律**：卖通用/后道组装、点胶、贴片、焊接、测试检测设备或第三方实验室检测服务（营收占比 `< 5%`）给下游客户，**一律不贴下游大类 `dynamic_tags`**（如给光模块厂卖组装/点胶/耦合/检测设备或测光器件不贴 `通信`，给液冷/服务器厂卖焊接或产线设备不贴 `算力`，给AI眼镜厂卖组装检测设备不贴 `消费电子`，给机器人厂卖IMU测试设备不贴 `机器人`，卖通用测试仪器方案不贴 `芯片`；注：半导体晶圆前道/封测核心专用设备及光刻机核心光学部件本身属 `芯片` 赛道，直接制造器件/核心材料/核心零部件/PCB钻针耗材者仍按方案 A 归动态）。例如 `603960 克来机电` 仅保留静态 `汽车、机器人`，`AI应用` 与 `通信` 均踢出动态。

3. 输出字段：`province` / `controller_type` 优先修正错漏（参考 `province_hint` 与 `provinces`: {json.dumps(TAXONOMY["provinces"], ensure_ascii=False)}，`controller_types`: {json.dumps(TAXONOMY["controller_types"], ensure_ascii=False)}），`audit_notes` 简明写清本次清淤改判依据。
"""


def _validate_with_ev(rec: dict, ev: dict | None) -> list[str]:
    merged = dict(rec)
    merged["ma_events"] = []
    return validate_record(merged, ev, TAXONOMY, min_dynamic_date=MIN_DYN_DATE)


def _is_valid(shard_id: str) -> bool:
    ev_p = SHARD_DIR / f"{shard_id}.json"
    out_p = OUT_DIR / f"{shard_id}.json"
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
            if _validate_with_ev(rec, ev_map.get(c)):
                return False
        return got == set(ev_map.keys())
    except Exception:
        return False


async def audit_shard(shard_id: str) -> dict:
    try:
        ev_doc = json.loads((SHARD_DIR / f"{shard_id}.json").read_text(encoding="utf-8"))
        stocks = ev_doc["stocks"]
        ev_by_code = {s["code"]: s for s in stocks}
        prompt = (
            AUDIT_PROMPT
            + f"\n请严格按方案A与1年有效期审核分片 {shard_id} 全部 {len(stocks)} 只股票：\n"
            + json.dumps(stocks, ensure_ascii=False, separators=(",", ":"))
        )
        a = agent(role=f"Audit {shard_id}", type_name="research")
        res = await a(prompt, OUTPUT_SCHEMA)
        for _ in range(2):
            errs = []
            got = set()
            for rec in res.get("stocks", []):
                c = str(rec.get("code") or "")
                got.add(c)
                errs.extend(_validate_with_ev(rec, ev_by_code.get(c)))
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
            final_errs.extend(_validate_with_ev(rec, ev_by_code.get(str(rec.get("code") or ""))))
        if final_errs:
            return {"shard_id": shard_id, "ok": False, "error": str(final_errs[:8])}

        res["shard_id"] = shard_id
        (OUT_DIR / f"{shard_id}.json").write_text(json.dumps(res, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return {"shard_id": shard_id, "ok": True, "count": len(res["stocks"])}
    except Exception as exc:
        return {"shard_id": shard_id, "ok": False, "error": f"{type(exc).__name__}: {exc}"}


phase(f"Scheme-A Cleanup Audit ({PREFIX})")
manifest = json.loads((SHARD_DIR / f"{PREFIX}_manifest.json").read_text(encoding="utf-8"))
all_shards = [s["shard_id"] for s in manifest["shards"]]
pending = [sid for sid in all_shards if not _is_valid(sid)]
log(f"Prefix={PREFIX}, total={len(all_shards)}, valid={len(all_shards)-len(pending)}, pending={len(pending)}")

failed = []
for i in range(0, len(pending), WAVE_SIZE):
    wave = pending[i : i + WAVE_SIZE]
    res_list = await parallel(wave, audit_shard)
    bad = [r for r in res_list if not r["ok"]]
    failed.extend(r["shard_id"] for r in bad)
    log(f"Wave {i//WAVE_SIZE+1}: ok={len(wave)-len(bad)}/{len(wave)}, failed={bad}")

if failed:
    log(f"Retrying {len(failed)} failed shards...")
    r_list = await parallel(failed, audit_shard)
    still_bad = [r for r in r_list if not r["ok"]]
    if still_bad:
        raise RuntimeError(f"Audit shards still failed after retry: {still_bad}")

log("Audit complete. Ready for merge and compile.")
