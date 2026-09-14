import re
from datetime import datetime

import httpx
from nonebot import get_driver, get_plugin_config, logger, on_command, require
from nonebot.adapters.onebot.v11 import Bot, Message, MessageEvent, MessageSegment
from nonebot.exception import FinishedException, MatcherException
from nonebot.params import CommandArg
from nonebot.plugin import PluginMetadata

require("nonebot_plugin_htmlrender")
require("nonebot_plugin_localstore")

from .binding_store import BindingStore
from .config import Config
from .crawler import FiveEEventCrawler, FiveECrawler, PWCrawler
from .llm import LLMEvaluator
from .match_service import MatchService, parse_bind_args, parse_match_args
from .renderer import (
    render_events_card,
    render_match_detail_card,
    render_player_detail,
    render_pw_stats_card,
    render_results_card,
    render_matches_card,
    render_stats_card,
)
from .storage import get_bind_db_path

__version__ = "0.2.1"

plugin_config = get_plugin_config(Config)
driver_config = get_driver().config

for legacy_name in (
    "cs_pro_priority",
    "cs_pro_bind_db_path",
    "cs_pro_http_timeout",
    "cs_pro_llm_enabled",
    "cs_pro_llm_api_type",
    "cs_pro_llm_api_url",
    "cs_pro_llm_api_key",
    "cs_pro_llm_model",
    "cs_pro_llm_backup_enabled",
    "cs_pro_llm_backup_api_type",
    "cs_pro_llm_backup_api_url",
    "cs_pro_llm_backup_api_key",
    "cs_pro_llm_backup_model",
    "cs_pro_llm_timeout",
    "cs_pro_llm_system_prompt",
):
    if getattr(plugin_config, legacy_name, None) is not None:
        logger.warning(f"[nonebot_plugin_cs2radar] `{legacy_name}` is deprecated; migrate to `cs2radar_*` config names.")

_USAGE_HELP = """CS2 Radar 插件命令一览：
1. 职业与赛事：
  - cs查询 <选手名> - 查询职业选手资料卡与能力评分 (别名: cs选手, csplayer)
  - cs赛事 - 查询近期重要赛事与进行中比赛 (别名: 赛事, csgo赛事, cs2赛事)
  - 赛果 - 查询近几日完赛比分与赛果 (别名: cs赛果, 赛事赛果)
2. 平台生涯战绩：
  - 5e [ID/昵称] [-r] - 查询 5E 平台综合战绩与 4 维智能战术画像 (别名: 5e战绩, 5e查询, cs战绩)
  - pw [昵称/SteamID] [-r] - 查询完美平台综合战绩与 4 维智能战术画像 (别名: pw战绩, pw查询, 完美战绩)
  - pwlogin <手机号> <验证码> - 登录完美世界电竞平台并保存本地会话 (别名: 完美登录)
3. 账号绑定与复盘：
  - bind <5e|pw> <玩家名> - 绑定当前 QQ 的默认查询对象 (别名: 绑定, 添加)
  - match [5e|pw|mm] [@群友] [局数] [-r] - 查询最近第 N 把详细对局并生成四维战术复盘 (别名: 战绩, 查询战绩)

说明：命令支持 [-r] 参数强制刷新战绩与 AI 战术分析缓存。未配置大模型时会自动基于选手真实数据智能对标职业哥并诊断天梯瓶颈。"""

__plugin_meta__ = PluginMetadata(
    name="CS2 Radar",
    description="CS2 赛事、选手、5E/完美/官匹战绩查询与详细对局分析",
    usage=_USAGE_HELP,
    type="application",
    homepage="https://github.com/luojisama/nonebot-plugin-cs2radar",
    config=Config,
    supported_adapters={"~onebot.v11"},
    extra={
        "author": "luojisama",
        "version": __version__,
        "pypi": "nonebot-plugin-cs2radar",
        "help": _USAGE_HELP,
        "menu": [
            {"cmd": "cs查询 <选手>", "desc": "查询职业选手战队与技术画像", "alias": ["cs选手", "csplayer"]},
            {"cmd": "cs赛事", "desc": "查询近期国际大赛与重要赛程", "alias": ["赛事", "csgo赛事", "cs2赛事"]},
            {"cmd": "赛果", "desc": "查询近几日比赛赛果与比分", "alias": ["cs赛果", "赛事赛果"]},
            {"cmd": "5e [ID/昵称] [-r]", "desc": "查询 5E 平台综合战绩与 4 维智能战术画像", "alias": ["5e战绩", "5e查询", "cs战绩"]},
            {"cmd": "pw [ID/昵称/SteamID] [-r]", "desc": "查询完美平台综合战绩与 4 维智能战术画像", "alias": ["pw战绩", "pw查询", "完美战绩"]},
            {"cmd": "pwlogin <手机号> <验证码>", "desc": "登录完美平台获取会话态", "alias": ["完美登录"]},
            {"cmd": "bind <5e|pw> <玩家名>", "desc": "绑定当前 QQ 的常用查询玩家", "alias": ["绑定", "添加"]},
            {"cmd": "match [5e|pw|mm] [@群友] [局数] [-r]", "desc": "查询最近第 N 把详细对局并生成四维战术复盘", "alias": ["战绩", "查询战绩"]},
        ],
        "configs": {
            "cs2radar_priority": "插件优先级 (默认: 5)",
            "cs2radar_bind_db_path": "绑定数据库路径 (默认: 自动定位至 localstore)",
            "cs2radar_http_timeout": "HTTP 请求超时秒数 (默认: 15)",
            "cs2radar_llm_enabled": "是否启用 LLM 战术分析与智能对标 (默认: true)",
            "cs2radar_llm_api_type": "LLM 接口类型 (openai/gemini/anthropic, 默认: openai)",
            "cs2radar_llm_api_url": "LLM 接口地址 (默认: https://api.openai.com/v1)",
            "cs2radar_llm_api_key": "LLM API Key",
            "cs2radar_llm_model": "LLM 模型名称 (默认: gpt-4o-mini)",
            "cs2radar_llm_backup_enabled": "是否启用备用 LLM (默认: false)",
            "cs2radar_llm_backup_api_type": "备用 LLM 接口类型",
            "cs2radar_llm_backup_api_url": "备用 LLM 接口地址",
            "cs2radar_llm_backup_api_key": "备用 LLM API Key",
            "cs2radar_llm_backup_model": "备用 LLM 模型名称",
            "cs2radar_llm_timeout": "LLM 请求超时秒数 (默认: 30)",
            "cs2radar_llm_system_prompt": "自定义战术复盘 System Prompt",
        },
    },
)

# Commands
cs_search = on_command("cs查询", aliases={"cs选手", "csplayer"}, priority=plugin_config.priority, block=True)
game_search = on_command("cs赛事", aliases={"赛事", "csgo赛事", "cs2赛事"}, priority=plugin_config.priority, block=True)
result_search = on_command("赛果", aliases={"cs赛果", "赛事赛果"}, priority=plugin_config.priority, block=True)
five_e_stats = on_command("5e", aliases={"5e战绩", "5e查询", "cs战绩"}, priority=plugin_config.priority, block=True)
pw_stats = on_command("pw", aliases={"pw战绩", "pw查询", "完美战绩"}, priority=plugin_config.priority, block=True)
pw_login = on_command("pwlogin", aliases={"完美登录"}, priority=plugin_config.priority, block=True)
bind_cmd = on_command("bind", aliases={"绑定", "添加", "绑定用户", "添加用户"}, priority=plugin_config.priority, block=True)
match_cmd = on_command("match", aliases={"战绩", "查询战绩"}, priority=plugin_config.priority, block=True)

# Shared services
store = BindingStore(str(get_bind_db_path(plugin_config.bind_db_path)))
match_service = MatchService(timeout=plugin_config.http_timeout)
_llm_api_key = (plugin_config.llm_api_key or "").strip()
_llm_api_type = plugin_config.llm_api_type
_llm_api_url = plugin_config.llm_api_url
_llm_model = plugin_config.llm_model
_llm_backup_enabled = plugin_config.llm_backup_enabled
_llm_backup_api_key = (plugin_config.llm_backup_api_key or "").strip()
_llm_backup_api_type = plugin_config.llm_backup_api_type
_llm_backup_api_url = plugin_config.llm_backup_api_url
_llm_backup_model = plugin_config.llm_backup_model
if not _llm_api_key:
    _llm_api_key = str(getattr(driver_config, "personification_api_key", "") or "").strip()
    _llm_api_type = str(getattr(driver_config, "personification_api_type", "openai") or "openai")
    _llm_api_url = str(getattr(driver_config, "personification_api_url", "https://api.openai.com/v1") or "https://api.openai.com/v1")
    _llm_model = str(getattr(driver_config, "personification_model", "gpt-4o-mini") or "gpt-4o-mini")
llm = LLMEvaluator(
    enabled=plugin_config.llm_enabled,
    api_type=_llm_api_type,
    api_url=_llm_api_url,
    api_key=_llm_api_key,
    model=_llm_model,
    backup_enabled=_llm_backup_enabled,
    backup_api_type=_llm_backup_api_type,
    backup_api_url=_llm_backup_api_url,
    backup_api_key=_llm_backup_api_key,
    backup_model=_llm_backup_model,
    timeout=plugin_config.llm_timeout,
    system_prompt=plugin_config.llm_system_prompt,
)

# Shared crawler instances
event_crawler = FiveEEventCrawler()
five_e_crawler = FiveECrawler()
pw_crawler = PWCrawler()


def _extract_target_qq(bot: Bot, event: MessageEvent) -> str:
    target = str(event.user_id)
    for seg in event.message:
        if seg.type == "at":
            qq = str(seg.data.get("qq") or "")
            if qq and qq != str(bot.self_id):
                target = qq
                break
    return target


def _platform_theme(platform: str) -> tuple[str, str, str]:
    if platform == "5e":
        return "5E平台", "#f74d4d", "#f78c00"
    if platform == "mm":
        return "官匹", "#2db3ff", "#3b82f6"
    return "完美平台", "#2db3ff", "#06b6d4"


def _fmt_pct(v: float) -> str:
    return f"{v * 100:.1f}%"


def _parse_llm_sections(text: str) -> list[dict]:
    if not text:
        return []
    pattern = r'【([^】]+)】'
    parts = re.split(pattern, text)
    if len(parts) >= 3 and not parts[0].strip():
        sections = []
        for i in range(1, len(parts), 2):
            tag = parts[i].strip()
            body = parts[i+1].strip() if i+1 < len(parts) else ""
            sections.append({"tag": tag, "content": body})
        return sections
    elif len(parts) >= 3:
        sections = []
        if parts[0].strip():
            sections.append({"tag": "总览", "content": parts[0].strip()})
        for i in range(1, len(parts), 2):
            tag = parts[i].strip()
            body = parts[i+1].strip() if i+1 < len(parts) else ""
            sections.append({"tag": tag, "content": body})
        return sections
    return [{"tag": "复盘点评", "content": text.strip()}]


def _build_profile_context_5e(data: dict, hltv_benchmarks: list[dict] | None = None) -> dict:
    nickname = data.get("nickname", "5E玩家")
    stats = data.get("stats", {})
    career = stats.get("career", {})
    role = stats.get("role", {})
    recent_matches = stats.get("recent_matches", [])

    match_total = int(career.get("match_total") or 0)
    win_total = int(career.get("win_total") or 0)
    tie_total = int(career.get("tie_total") or 0)
    loss_total = int(career.get("loss_total") or 0)
    win_rate = f"{(win_total / match_total * 100):.1f}%" if match_total > 0 else "0.0%"

    kill_total = int(career.get("kill_total") or 0)
    headshot_total = int(career.get("headshot_total") or 0)
    hs_rate = f"{(headshot_total / kill_total * 100):.1f}%" if kill_total > 0 else (
        f"{(float(career.get('per_headshot', 0)) * 100):.1f}%" if career.get('per_headshot') else "0.0%"
    )

    recent_list = []
    for rm in recent_matches[:5]:
        is_win = rm.get("is_win")
        is_tie = rm.get("is_tie")
        res = "胜" if is_win else ("平" if is_tie else "负")
        recent_list.append({
            "map": rm.get("map_name") or rm.get("map"),
            "result": res,
            "score": str(rm.get("score") or ""),
            "rating": rm.get("rating"),
            "kill": rm.get("kill"),
            "death": rm.get("death"),
            "adr": rm.get("adr"),
        })

    ctx = {
        "platform": "5E ARENA 对战平台",
        "player_name": nickname,
        "elo": career.get("elo_9") or career.get("elo", 0),
        "rank": career.get("rank", 0),
        "rating": career.get("rating", 0),
        "adr": career.get("adr", 0),
        "kpr": career.get("kpr", 0),
        "rws": career.get("rws", 0),
        "matches": f"总场次 {match_total} (胜 {win_total} / 平 {tie_total} / 负 {loss_total})",
        "win_rate": win_rate,
        "headshot_ratio": hs_rate,
        "win_streak": career.get("win_streak", 0),
        "role_name": role.get("role_name", ""),
        "role_desc": role.get("role_desc", ""),
        "role_tags": role.get("role_tags", []),
        "role_level": role.get("score_level", ""),
        "recent_matches": recent_list,
    }
    if hltv_benchmarks:
        ctx["hltv_pro_benchmarks"] = hltv_benchmarks[:6]
    return ctx


def _build_profile_context(data: dict, hltv_benchmarks: list[dict] | None = None) -> dict:
    summary = data.get("summary", {})
    stats = data.get("stats", {})
    recent_matches = data.get("recent_matches", [])

    wr = stats.get("winRate", 0)
    win_rate_str = f"{wr * 100:.1f}%" if wr and wr <= 1 else f"{wr}%"
    hs = stats.get("headShotRatio", 0)
    hs_str = f"{hs * 100:.1f}%" if hs and hs <= 1 else f"{hs}%"
    ek = stats.get("entryKillRatio", 0)
    ek_str = f"{ek * 100:.1f}%" if ek and ek <= 1 else f"{ek}%"

    hot_maps = [
        {"map": m.get("mapName"), "matches": m.get("totalMatch"), "win_rate": f"{(m.get('winCount', 0)/m.get('totalMatch', 1)*100):.1f}%"}
        for m in stats.get("hotMaps", [])[:3] if m.get("totalMatch")
    ]
    weapons = (stats.get("hotWeapons") or []) + (stats.get("hotWeapons2") or [])
    hot_weapons = [
        {"name": w.get("weaponName") or w.get("nameZh") or w.get("name"), "kills": w.get("weaponKill") or w.get("killNum", 0)}
        for w in weapons[:4]
    ]
    recent_list = [
        {
            "map": rm.get("mapName"),
            "result": "胜" if rm.get("team") == rm.get("winTeam") else ("平" if rm.get("score1") == rm.get("score2") else "负"),
            "score": f"{rm.get('score1')}:{rm.get('score2')}",
            "rating": rm.get("pwRating") if rm.get("pwRating") is not None else rm.get("rating"),
            "kd": f"{rm.get('kill', 0)}/{rm.get('death', 0)}"
        }
        for rm in recent_matches[:5]
    ]

    ctx = {
        "player_name": summary.get("nickname", "未知"),
        "steam_id": str(summary.get("steamId", "")),
        "season": stats.get("seasonId", "当前赛季"),
        "pvp_score": stats.get("pvpScore", 0),
        "pvp_rank": stats.get("pvpRank", 0),
        "rating": stats.get("pwRating") if stats.get("pwRating") is not None else stats.get("rating", 0),
        "adr": stats.get("adr", 0),
        "kd": stats.get("kd", 0),
        "rws": stats.get("rws", 0),
        "win_rate": win_rate_str,
        "headshot_ratio": hs_str,
        "entry_kill_ratio": ek_str,
        "matches_count": stats.get("cnt", 0),
        "mvp_count": stats.get("mvpCount", 0),
        "radar": {
            "shot": round(stats.get("shot", 0), 1),
            "victory": round(stats.get("victory", 0), 1),
            "breach": round(stats.get("breach", 0), 1),
            "prop": round(stats.get("prop", 0), 1),
            "snipe": round(stats.get("snipe", 0), 1),
        },
        "highlights": {
            "multi_kills": f"2K:{stats.get('k2', 0)} / 3K:{stats.get('k3', 0)} / 4K:{stats.get('k4', 0)} / 5K:{stats.get('k5', 0)}",
            "clutch_wins": stats.get("endingWin", 0)
        },
        "hot_maps": hot_maps,
        "hot_weapons": hot_weapons,
        "recent_matches": recent_list
    }
    if hltv_benchmarks:
        ctx["hltv_pro_benchmarks"] = hltv_benchmarks[:6]
    return ctx


def _build_match_view_data(match_data, llm_title: str, llm_detail: str) -> dict:
    platform_label, color_a, color_b = _platform_theme(match_data.platform)

    def _highlight_view(highlights):
        return {
            "first_kills": highlights.first_kills,
            "multi_kills": highlights.multi_kills,
            "clutch_wins": highlights.clutch_wins,
            "summary_cards": [
                {"label": "首杀", "value": highlights.first_kills},
                {"label": "多杀", "value": highlights.multi_kills},
                {"label": "残局", "value": highlights.clutch_wins},
                {"label": "2K/3K/4K/5K", "value": f"{highlights.kills_2}/{highlights.kills_3}/{highlights.kills_4}/{highlights.kills_5}"},
            ],
            "clutch_cards": [
                {"label": "1v1", "value": highlights.clutch_1v1},
                {"label": "1v2", "value": highlights.clutch_1v2},
                {"label": "1v3", "value": highlights.clutch_1v3},
                {"label": "1v4", "value": highlights.clutch_1v4},
                {"label": "1v5", "value": highlights.clutch_1v5},
            ],
        }

    def _p(p):
        return {
            "name": p.name,
            "rating": f"{p.rating:.2f}",
            "adr": f"{p.adr:.1f}",
            "kill": p.kill,
            "death": p.death,
            "hs": _fmt_pct(p.headshot_rate),
            "elo": f"{p.elo_change:+.1f}",
            "rws": f"{p.rws:.2f}",
            "uuid": p.uuid,
            "highlights": _highlight_view(p.highlights),
        }

    def _round_view(item):
        result_map = {"W": ("胜", "win"), "L": ("负", "loss")}
        label, css = result_map.get(item.result, ("?", "unknown"))
        return {
            "no": item.round_no,
            "result": item.result,
            "result_label": label,
            "result_class": css,
            "side": item.side or "",
            "score_after": item.score_after or "",
        }

    def _segment_view(segment):
        return {
            "key": segment.key,
            "label": segment.label,
            "our_score": segment.our_score,
            "enemy_score": segment.enemy_score,
            "score_text": f"{segment.our_score}:{segment.enemy_score}",
            "rounds": [_round_view(x) for x in segment.rounds],
        }

    start_at = datetime.fromtimestamp(match_data.start_time).strftime("%Y-%m-%d %H:%M:%S")
    all_teammates = [match_data.player] + match_data.teammates
    all_teammates.sort(key=lambda x: x.rating, reverse=True)
    halves = [_segment_view(x) for x in match_data.halves]
    half_summary = " / ".join(f"{item['label']} {item['score_text']}" for item in halves) or "暂无"
    player_view = _p(match_data.player)

    return {
        "platform_label": platform_label,
        "theme_a": color_a,
        "theme_b": color_b,
        "map_name": match_data.map_name,
        "match_type": match_data.match_type or "未知模式",
        "start_at": start_at,
        "duration_min": match_data.duration_min,
        "result_text": match_data.result_text,
        "result_class": "good" if match_data.result_text == "胜利" else ("draw" if match_data.result_text == "平局" else "bad"),
        "match_id": match_data.match_id,
        "score_text": f"{match_data.score_our}:{match_data.score_enemy}",
        "half_summary": half_summary,
        "halves": halves,
        "has_rounds": any(item["rounds"] for item in halves),
        "has_overtime": match_data.has_overtime,
        "player": player_view,
        "player_highlights": player_view["highlights"],
        "teammates": [_p(x) for x in all_teammates],
        "opponents": [_p(x) for x in match_data.opponents],
        "llm_title": llm_title,
        "llm_detail": llm_detail,
        "llm_sections": _parse_llm_sections(llm_detail),
    }


@bind_cmd.handle()
async def handle_bind(event: MessageEvent, args: Message = CommandArg()):
    raw = args.extract_plain_text().strip()
    if not raw:
        await bind_cmd.finish("用法: /bind [5e|pw] [玩家名]")

    try:
        default_platform = store.get_default_platform(str(event.user_id))
        platform, name = parse_bind_args(raw, default_platform=default_platform)

        # 5E绑定复用 /5e 查询规则：ID/域名直接绑定，昵称走 search_player 首条匹配。
        if platform == "5e":
            is_id = re.match(r"^\d+s\w+$|^\d+$|^[0-9a-f-]{36}$", name)
            if is_id:
                bound = await match_service.bind_5e_domain(store, str(event.user_id), name, canonical_name=name)
            else:
                candidates = await five_e_crawler.search_player(name)
                if not candidates:
                    await bind_cmd.finish(f"绑定失败: 未找到5E玩家 {name}")
                first = candidates[0]
                domain = str(first.get("domain") or "").strip()
                if not domain:
                    await bind_cmd.finish("绑定失败: 5E搜索结果缺少domain")
                canonical = str(first.get("name") or name)
                bound = await match_service.bind_5e_domain(store, str(event.user_id), domain, canonical_name=canonical)
        else:
            bound = await match_service.bind_player(store, str(event.user_id), platform, name)
    except Exception as e:
        await bind_cmd.finish(f"绑定失败: {e}")

    if bound.platform == "pw" and (not bound.domain or not bound.uuid):
        await bind_cmd.finish(
            f"绑定成功\n平台: {bound.platform}\n玩家: {bound.player_name}\n"
            "已按用户名绑定，将在首次查询官匹/完美战绩时自动补全平台ID与SteamID。"
        )
    await bind_cmd.finish(
        f"绑定成功\n平台: {bound.platform}\n玩家: {bound.player_name}\n平台ID: {bound.domain}\nSteamID: {bound.uuid}"
    )


@match_cmd.handle()
async def handle_match(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    raw = args.extract_plain_text().strip()
    refresh = False
    if "-r" in raw or "--refresh" in raw or "刷新" in raw:
        refresh = True
        raw = raw.replace("--refresh", "").replace("-r", "").replace("刷新", "").strip()

    platform, round_index = parse_match_args(raw)
    target_qq = _extract_target_qq(bot, event)

    await match_cmd.send("正在查询详细战绩并生成评价...")
    try:
        match_data = await match_service.fetch_match(store, target_qq, platform, round_index)
    except Exception as e:
        await match_cmd.finish(f"查询失败: {e}")

    llm_title = "风格待定"
    llm_detail = "【战局走势】比赛数据分析中。【核心表现】战术复盘计算中。【团队对比】正在比对双方攻防数据。【改进建议】保持稳定沟通与道具配合。"
    try:
        result = await llm.evaluate(match_data.llm_context(), refresh=refresh)
        if result:
            llm_title = result.title
            llm_detail = result.detail
        else:
            fallback = llm._generate_smart_match_fallback(match_data.llm_context())
            llm_title = fallback.title
            llm_detail = fallback.detail
    except Exception as e:
        logger.warning(f"[cs2radar] llm evaluate failed: {e}")
        try:
            fallback = llm._generate_smart_match_fallback(match_data.llm_context())
            llm_title = fallback.title
            llm_detail = fallback.detail
        except Exception:
            pass

    view_data = _build_match_view_data(match_data, llm_title, llm_detail)
    image_bytes = await render_match_detail_card(view_data)
    await match_cmd.finish(MessageSegment.image(image_bytes))


@cs_search.handle()
async def handle_cs_search(args: Message = CommandArg()):
    query = args.extract_plain_text().strip()
    if not query:
        await cs_search.finish("请输入选手名称，例如: cs查询 sh1ro")

    search_api = "https://api.viki.moe/pw-cs/search"
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(search_api, params={"type": "player", "s": query})
            data = resp.json()
        except Exception as e:
            await cs_search.finish(f"查询出错: {e}")

    if not isinstance(data, list):
        await cs_search.finish(f"查询出错: {data.get('message') if isinstance(data, dict) else '未知错误'}")
    if not data:
        await cs_search.finish("未找到相关选手，请检查名称")

    player_brief = data[0]
    hltv_id = player_brief.get("hltv_id")
    if not hltv_id:
        await cs_search.finish("未找到选手HLTV ID")

    detail_api = f"https://api.viki.moe/pw-cs/player/{hltv_id}"
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(detail_api)
            player = resp.json()
        except Exception as e:
            await cs_search.finish(f"获取选手详情出错: {e}")

    try:
        image_bytes = await render_player_detail(player)
    except Exception as e:
        logger.error(f"Error rendering player detail: {e}")
        name = player.get("name", "未知")
        team_name = player.get("team", {}).get("name", "无战队")
        await cs_search.finish(f"选手: {name}\n战队: {team_name}\n(图片渲染失败)")

    await cs_search.finish(MessageSegment.image(image_bytes))


@game_search.handle()
async def handle_game_search():
    await game_search.send("正在获取实时赛程与赛事信息...")
    try:
        matches = await event_crawler.get_matches()
        if matches:
            image_bytes = await render_matches_card(matches)
            await game_search.finish(MessageSegment.image(image_bytes))

        events = await event_crawler.get_events()
        if events:
            image_bytes = await render_events_card(events)
            await game_search.finish(MessageSegment.image(image_bytes))

        await game_search.finish("暂无实时赛程数据。")
    except (FinishedException, MatcherException):
        raise
    except Exception as e:
        logger.error(f"Error in game_search: {e}")
        await game_search.finish(f"查询赛事失败: {e}")


@result_search.handle()
async def handle_result_search():
    await result_search.send("正在获取赛果数据...")
    try:
        results = await event_crawler.get_results()
        if not results:
            await result_search.finish("暂无赛果数据。")
        image_bytes = await render_results_card(results)
        await result_search.finish(MessageSegment.image(image_bytes))
    except (FinishedException, MatcherException):
        raise
    except Exception as e:
        logger.error(f"Error in result_search: {e}")
        await result_search.finish(f"查询赛果失败: {e}")


@five_e_stats.handle()
async def handle_five_e_stats(bot: Bot, event: MessageEvent, arg: Message = CommandArg()):
    raw = arg.extract_plain_text().strip()
    refresh = False
    if "-r" in raw or "--refresh" in raw or "刷新" in raw:
        refresh = True
        raw = raw.replace("--refresh", "").replace("-r", "").replace("刷新", "").strip()

    target_qq = _extract_target_qq(bot, event)
    is_self = (target_qq == str(event.user_id))

    input_str = raw
    domain = ""
    target_name = ""
    search_info = {}

    if not input_str:
        # 无参数，查绑定
        binding = store.get_binding(target_qq, "5e")
        if not binding:
            if is_self:
                await five_e_stats.finish("未检测到您的 5E 账号绑定，请先绑定：/bind 5e <玩家名/域名>，或直接指定玩家查询：/5e <玩家名/域名>")
            else:
                await five_e_stats.finish(f"该用户 (QQ: {target_qq}) 暂未绑定 5E 账号。")

        target_name = binding.player_name
        domain = binding.domain or binding.uuid or target_name
        await five_e_stats.send(f"正在查询绑定的 5E 玩家 {target_name or domain}...")
    else:
        # 有参数，查指定玩家
        await five_e_stats.send(f"正在查询 5E 玩家 {input_str}...")
        domain = input_str
        target_name = input_str

    try:
        is_id = bool(re.match(r"^\d+s\w+$|^\d+$|^[0-9a-f-]{36}$", domain))
        if not is_id:
            search_results = await five_e_crawler.search_player(domain)
            if not search_results:
                await five_e_stats.finish(f"未找到昵称为 {domain} 的 5E 玩家。")
            search_info = search_results[0]
            domain = search_info["domain"]
            target_name = search_info.get("name", domain)
            await five_e_stats.send(f"匹配到玩家: {target_name} ({domain})，正在获取详细战绩...")

        data = await five_e_crawler.get_player_data(
            domain,
            nickname=target_name or search_info.get("name", ""),
            avatar=search_info.get("avatar", "")
        )

        if not data or not data.get("stats") or not data["stats"].get("career"):
            await five_e_stats.finish(f"未找到玩家 {domain} 的有效 5E 战绩数据。")

        # 生成 / 获取 LLM 主页评价
        try:
            benchmarks = []
            try:
                benchmarks = await event_crawler.get_hltv_pro_benchmarks()
            except Exception:
                pass
            profile_ctx = _build_profile_context_5e(data, hltv_benchmarks=benchmarks)
            career = data.get("stats", {}).get("career", {})
            cnt = int(career.get("match_total") or 0)
            season_id = str(career.get("best_season") or "")
            llm_res = await llm.evaluate_profile(
                profile_ctx,
                platform="5e",
                refresh=refresh,
                target_steam_id=domain,
                match_cnt=cnt,
                season_id=season_id,
            )
            data["llm_title"] = llm_res.title
            data["llm_detail"] = llm_res.detail
            data["llm_sections"] = _parse_llm_sections(llm_res.detail)
        except Exception as e:
            logger.warning(f"生成5E主页LLM评价失败: {e}")
            fallback_res = llm._generate_smart_profile_fallback(_build_profile_context_5e(data))
            data["llm_title"] = fallback_res.title
            data["llm_detail"] = fallback_res.detail
            data["llm_sections"] = _parse_llm_sections(fallback_res.detail)

        image_bytes = await render_stats_card(data)
        await five_e_stats.finish(MessageSegment.image(image_bytes))
    except (FinishedException, MatcherException):
        raise
    except Exception as e:
        logger.error(f"Error in five_e_stats: {e}")
        await five_e_stats.finish(f"5E 查询失败: {str(e)}")


@pw_login.handle()
async def handle_pw_login(arg: Message = CommandArg()):
    args = arg.extract_plain_text().strip().split()
    if len(args) != 2:
        await pw_login.finish("请输入手机号和验证码，例如: /pwlogin 13800138000 123456")

    mobile, code = args
    await pw_login.send("正在尝试登录完美平台...")

    result = await pw_crawler.login(mobile, code)
    if "error" in result:
        await pw_login.finish(f"登录失败: {result['error']}")

    nickname = result.get("nickname", "未知")
    await pw_login.finish(f"登录成功，欢迎回来，{nickname}。Session 已更新。")


@pw_stats.handle()
async def handle_pw_stats(bot: Bot, event: MessageEvent, arg: Message = CommandArg()):
    raw = arg.extract_plain_text().strip()
    refresh = False
    if "-r" in raw or "--refresh" in raw or "刷新" in raw:
        refresh = True
        raw = raw.replace("--refresh", "").replace("-r", "").replace("刷新", "").strip()

    target_qq = _extract_target_qq(bot, event)
    is_self = (target_qq == str(event.user_id))

    input_str = raw
    target_steam_id = ""
    search_info = {}

    if not input_str:
        # 无参数查询，走绑定
        binding = store.get_binding(target_qq, "pw")
        if not binding:
            if is_self:
                await pw_stats.finish("未检测到您的完美账号绑定，请先绑定：/bind pw <玩家名>，或直接指定玩家查询：/pw <玩家名/SteamID>")
            else:
                await pw_stats.finish(f"该用户 (QQ: {target_qq}) 暂未绑定完美账号。")

        target_name = binding.player_name
        target_steam_id = str(binding.uuid or "").strip()

        if not target_steam_id or not target_steam_id.isdigit():
            if not pw_crawler.has_session():
                await pw_stats.finish("请先使用 /pwlogin <手机号> <验证码> 登录完美平台后再查询。")
            await pw_stats.send(f"正在查询绑定的完美玩家 {target_name}...")
            search_results = await pw_crawler.search_player(target_name)
            if not search_results:
                await pw_stats.finish(f"未找到已绑定昵称 {target_name} 的完美玩家，请检查绑定：/bind pw <玩家名>")
            search_info = search_results[0]
            target_steam_id = str(search_info["steamId"])
            # 自动补全 SteamID
            domain = str(search_info.get("domain") or "").strip()
            store.upsert_binding(target_qq, "pw", target_name, domain, target_steam_id)
        else:
            await pw_stats.send(f"正在查询绑定的完美玩家 {target_name or target_steam_id}...")
    else:
        # 有参数查询，查指定玩家
        await pw_stats.send(f"正在查询完美玩家 {input_str}...")
        is_steam_id = input_str.isdigit() and len(input_str) > 10
        target_steam_id = input_str

        if not is_steam_id:
            if not pw_crawler.has_session():
                await pw_stats.finish("请先使用 /pwlogin <手机号> <验证码> 登录完美平台后再查询。")
            search_results = await pw_crawler.search_player(input_str)
            if not search_results:
                await pw_stats.finish(f"未找到昵称为 {input_str} 的玩家。")
            search_info = search_results[0]
            target_steam_id = str(search_info["steamId"])
            await pw_stats.send(f"匹配到玩家: {search_info.get('pvpNickName', '未知')}，正在获取详细战绩...")

    try:
        data = await pw_crawler.get_player_data(target_steam_id)
        if "error" in data:
            await pw_stats.finish(f"查询完美战绩失败: {data['error']}")
        if not data or not data.get("stats"):
            await pw_stats.finish(f"未找到玩家 {target_steam_id} 的有效战绩数据。")

        if not data.get("summary", {}).get("nickname"):
            data["summary"]["nickname"] = search_info.get("pvpNickName", "Unknown")
        if not data.get("summary", {}).get("avatarUrl"):
            data["summary"]["avatarUrl"] = search_info.get("pvpAvatar")

        # 生成 / 获取 LLM 主页评价
        try:
            benchmarks = []
            try:
                benchmarks = await event_crawler.get_hltv_pro_benchmarks()
            except Exception:
                pass
            profile_ctx = _build_profile_context(data, hltv_benchmarks=benchmarks)
            cnt = data.get("stats", {}).get("cnt", 0)
            season_id = str(data.get("stats", {}).get("seasonId") or "")
            llm_res = await llm.evaluate_profile(
                profile_ctx,
                refresh=refresh,
                target_steam_id=target_steam_id,
                match_cnt=cnt,
                season_id=season_id,
            )
            data["llm_title"] = llm_res.title
            data["llm_detail"] = llm_res.detail
            data["llm_sections"] = _parse_llm_sections(llm_res.detail)
        except Exception as e:
            logger.warning(f"生成主页LLM评价失败: {e}")
            fallback_res = llm._generate_smart_profile_fallback(_build_profile_context(data))
            data["llm_title"] = fallback_res.title
            data["llm_detail"] = fallback_res.detail
            data["llm_sections"] = _parse_llm_sections(fallback_res.detail)

        image_bytes = await render_pw_stats_card(data)
        await pw_stats.finish(MessageSegment.image(image_bytes))
    except (FinishedException, MatcherException):
        raise
    except Exception as e:
        logger.error(f"Error in pw_stats: {e}")
        await pw_stats.finish(f"完美战绩查询失败: {str(e)}")
