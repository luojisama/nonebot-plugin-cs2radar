from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any

import httpx
from nonebot import logger


DEFAULT_PROFILE_SYSTEM_PROMPT = (
    "你是一名CS2顶级职业战队的数据总监兼首席战术分析师。你的任务是根据选手的赛季综合战绩、雷达六维能力数据、武器与地图池表现，结合HLTV职业选手多维属性基准，提供一份客观、硬核、具备顶级职业视角的战术风格画像与天梯瓶颈诊断报告。\n\n"
    "【分析维度规范】\n"
    "1. 战力定位：结合天梯分数/段位、Rating、ADR及胜率，界定其在当前层级的真实统治力与竞技生态位（如高分天梯绝对大腿、稳健控图副核、高风险拼抢型先锋）。\n"
    "2. 技术风格与职业对标：依据六维雷达（枪法/致胜/突破/道具/狙击）及首杀率、爆头率，对标具体的职业选手模板（如 donk、ropz、sh1ro、b1t、m0NESY、apEX、ZywOo 等），剖析风格契合点、优势项目及与职业模板的关键差距。\n"
    "3. 偏科与武器地图：分析常用武器杀敌比重与地图胜率，指出其武器池专精深度与地图池盲区（如单图战神或全图适应性）。\n"
    "4. 天梯瓶颈突破：针对假性高Rating低胜率、首杀偏低、冲锋白给、道具短板或顺风刷分逆风隐身等问题，提供1-2条切中要害的职业级瓶颈突破与提升清单。\n\n"
    "【输出格式严格要求】\n"
    "必须仅输出标准 JSON 格式，不要包含任何额外说明或 Markdown 代码块标记，字段定义如下：\n"
    "{\n"
    '  "title": "6-14字精准概括玩家定位与战力画像（如：超强破点锋刃·对标donk / 控图残局大师·对标ropz）",\n'
    '  "detail": "220-350字系统画像分析。必须严格使用【战力定位】【技术风格与职业对标】【偏科与武器地图】【天梯瓶颈突破】四个标签清晰分段，语言专业硬核、数据说话、切中要害。"\n'
    "}"
)

DEFAULT_MATCH_SYSTEM_PROMPT = (
    "你是一名CS2顶级职业战队的首席数据与战术分析师。你的任务是根据选手的整场对局多维数据，提供一份专业、系统、犀利的赛后战术复盘报告。\n\n"
    "【分析维度规范】\n"
    "1. 战局走势：结合攻守半场比分、连续回合走向及比赛最终结果，定位经济局翻盘或崩盘的关键胜负手回合。\n"
    "2. 核心表现：深度结合 Rating、ADR、RWS 胜局贡献值、爆头率、首杀突破、多杀高光及1vN残局处理，剖析其正面硬解能力与对位敌方主力的压制力。\n"
    "3. 团队对比：横向对比队友与对手数据，区分有效伤害与保枪白嫖，评定主角在队内的战力担当程度（如尽力型孤勇者、致胜功臣或状态断档）。\n"
    "4. 改进建议：基于对局暴露的失误或短板，提出1-2条具备可落地性的战术改进方案（如道具联动、残局时间管理、首杀后站位收缩）。\n\n"
    "【输出格式严格要求】\n"
    "必须仅输出标准 JSON 格式，不要包含任何额外说明或 Markdown 代码块标记，字段定义如下：\n"
    "{\n"
    '  "title": "6-14字精准概括打法风格与表现定位（如：撕裂防线的绝对突破尖刀 / 逆风扛旗的大心脏残局主宰 / 独木难支的尽力局孤勇者）",\n'
    '  "detail": "200-320字系统复盘报告。必须严格使用【战局走势】【核心表现】【团队对比】【改进建议】四个标签呈现，语言专业犀利、切中要害。"\n'
    "}"
)


@dataclass
class LLMResult:
    title: str
    detail: str


class LLMEvaluator:
    def __init__(
        self,
        enabled: bool,
        api_type: str,
        api_url: str,
        api_key: str,
        model: str,
        backup_enabled: bool,
        backup_api_type: str,
        backup_api_url: str,
        backup_api_key: str,
        backup_model: str,
        timeout: int,
        system_prompt: str,
    ) -> None:
        self.enabled = enabled
        self.api_type = (api_type or "openai").strip().lower()
        self.api_url = (api_url or "").rstrip("/")
        self.api_key = (api_key or "").strip()
        self.model = (model or "").strip()
        self.backup_enabled = backup_enabled
        self.backup_api_type = (backup_api_type or "openai").strip().lower()
        self.backup_api_url = (backup_api_url or "").rstrip("/")
        self.backup_api_key = (backup_api_key or "").strip()
        self.backup_model = (backup_model or "").strip()
        self.timeout = timeout
        self.system_prompt = system_prompt
        self._cache: dict[str, tuple[float, LLMResult]] = {}

    def _get_cached(self, key: str) -> LLMResult | None:
        item = self._cache.get(key)
        if not item:
            return None
        expire_at, result = item
        if time.time() > expire_at:
            self._cache.pop(key, None)
            return None
        return result

    def _set_cached(self, key: str, result: LLMResult, ttl: float = 86400.0) -> None:
        if len(self._cache) > 1000:
            keys_to_remove = list(self._cache.keys())[:200]
            for k in keys_to_remove:
                self._cache.pop(k, None)
        self._cache[key] = (time.time() + ttl, result)

    @staticmethod
    def _build_match_cache_key(match_context: dict) -> str:
        match_id = str(match_context.get("match_id") or "")
        player = match_context.get("player") or {}
        player_id = str(player.get("uuid") or player.get("name") or "")
        if match_id and player_id:
            return f"match_{match_id}_{player_id}"
        raw = json.dumps(match_context, sort_keys=True, ensure_ascii=False)
        return f"match_{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]}"

    @staticmethod
    def _generate_smart_profile_fallback(profile_context: dict) -> LLMResult:
        """基于真实客观指标智能匹配职业选手模板与天梯瓶颈诊断（智能动态兜底算法）"""
        def _to_float(v: Any, default: float = 0.0) -> float:
            if v is None:
                return default
            if isinstance(v, (int, float)):
                return float(v)
            s = str(v).replace("%", "").strip()
            try:
                return float(s)
            except Exception:
                return default

        score = profile_context.get("pvp_score") or profile_context.get("elo") or 0
        rating = _to_float(profile_context.get("rating"), 1.0)
        adr = _to_float(profile_context.get("adr"), 75.0)
        kd = _to_float(profile_context.get("kd"), 1.0)
        wr = _to_float(profile_context.get("win_rate"), 50.0)
        hs = _to_float(profile_context.get("headshot_ratio"), 40.0)
        ek = _to_float(profile_context.get("entry_kill_ratio"), 18.0)

        radar = profile_context.get("radar") or {}
        shot = _to_float(radar.get("shot"), 65.0)
        victory = _to_float(radar.get("victory"), 65.0)
        breach = _to_float(radar.get("breach"), 65.0)
        prop = _to_float(radar.get("prop"), 60.0)
        snipe = _to_float(radar.get("snipe"), 50.0)

        platform = str(profile_context.get("platform") or "")
        is_5e = "5E" in platform or "5e" in platform.lower()
        role_name = str(profile_context.get("role_name") or "")
        role_tags = profile_context.get("role_tags") or []

        if is_5e:
            if "狙击" in role_name or "狙" in str(role_tags):
                snipe = max(snipe, 92.0)
            if "突破" in role_name or "锋刃" in str(role_tags):
                breach = max(breach, 90.0)
                ek = max(ek, 23.0)
            elif "首杀" in str(role_tags):
                breach = max(breach, 82.0)
                ek = max(ek, 20.0)
            if "自由人" in role_name or "残局" in str(role_tags):
                victory = max(victory, 88.0)
            if hs >= 50.0:
                shot = max(shot, 88.0)

        # 职业选手模板映射
        if snipe >= 75.0 and snipe >= shot and snipe >= breach:
            if victory >= 75.0 or kd >= 1.15:
                pro_name = "sh1ro"
                pro_archetype = "高胜率残局狙神"
                pro_desc = "兼具极高残局阅读转化率与防守架枪稳定性，选位严密、极少非受迫性失误"
                style_short = "残局冷面死神"
            else:
                pro_name = "m0NESY"
                pro_archetype = "极限反应狂狙"
                pro_desc = "依靠灵动身法与非常规进攻位打开防线，具有极高的首杀开局威慑力"
                style_short = "灵动破局狂狙手"
        elif hs >= 52.0 or (shot >= 84.0 and hs >= 46.0 and shot > breach):
            pro_name = "b1t"
            pro_archetype = "精准爆头机器"
            pro_desc = "机械化急停定位与第一发爆头摧毁力极高，常规架枪与首发击杀效率极高"
            style_short = "机械准星爆头怪"
        elif breach >= 82.0 or ek >= 21.0:
            if rating >= 1.18 or adr >= 85.0:
                pro_name = "donk"
                pro_archetype = "极致暴力首破"
                pro_desc = "第一身位大拉拼抢与正面硬解能力极强，以狂暴的单兵火力压制摧毁对手防线"
                style_short = "撕裂防线尖刀"
            else:
                pro_name = "NiKo"
                pro_archetype = "重炮推进步枪手"
                pro_desc = "预瞄搜点极其扎实，纯粹的步枪正面交火给予对手窒息般的压制力"
                style_short = "强权正面突击手"
        elif victory >= 80.0 or "自由人" in role_name or "残局" in str(role_tags):
            pro_name = "ropz"
            pro_archetype = "深层控图自由人"
            pro_desc = "残局时间管理大师与信息搜集先锋，擅长在侧翼隐蔽摸排并收割残局"
            style_short = "深层控图智将"
        elif prop >= 78.0 or (rating < 1.05 and wr >= 52.0):
            pro_name = "apEX"
            pro_archetype = "战术道具指挥"
            pro_desc = "无私的战术道具覆盖与信息交换先锋，以团队控图节奏与道具联动见长"
            style_short = "战术协同指挥中坚"
        else:
            if rating >= 1.12:
                pro_name = "ZywOo"
                pro_archetype = "全维度战术核心"
                pro_desc = "武器池覆盖极广、攻守一体的高下限战术基石，在各种交火局均有稳定输出"
                style_short = "全能竞技核心"
            else:
                pro_name = "frozen"
                pro_archetype = "稳健二楼步枪手"
                pro_desc = "站位稳健、补枪效率扎实，是支撑队伍防守与道具推进的坚固防线"
                style_short = "稳健补枪中坚"

        title = f"{style_short}·对标{pro_name}"

        # 4 维微报告构建
        score_desc = f"当前天梯积分/分段为 {score}，" if score else "天梯处于活跃排位阶段，"
        if rating >= 1.20 and adr >= 85.0:
            power_eval = f"{score_desc}Rating高达 {rating:.2f}，场均ADR {adr:.1f}，胜率 {wr:.1f}%，在当前竞技层级具备绝对的战场支配力与稳定的大核carry能力。"
        elif rating >= 1.05:
            power_eval = f"{score_desc}Rating维持在 {rating:.2f}，场均ADR {adr:.1f}，攻防输出均衡，是队伍不可或缺的中流砥柱与关键得分点。"
        else:
            power_eval = f"{score_desc}Rating {rating:.2f}，场均ADR {adr:.1f}，胜率 {wr:.1f}%，在当前分段面临一定交火对抗压力，整体偏向功能辅助与团队协同。"

        tech_eval = (
            f"综合雷达能力与关键攻防比率，技术打法高度契合职业选手 {pro_name}（{pro_archetype}）。{pro_desc}。"
            f"爆头率 {hs:.1f}%，首杀参与率 {ek:.1f}%，正面交火风格鲜明；与顶尖职业哥的关键差距主要体现在高压逆风局的连续多杀能力与极端失误容错率。"
        )

        hot_weapons = profile_context.get("hot_weapons") or []
        hot_maps = profile_context.get("hot_maps") or []
        weapon_desc = ""
        if hot_weapons:
            w_top = hot_weapons[0]
            weapon_desc = f"主力枪械深度依赖 {w_top.get('name', '主战步枪')}（{w_top.get('kills', 0)}杀），"
        map_desc = ""
        if hot_maps:
            m_top = hot_maps[0]
            map_desc = f"地图池以 {m_top.get('map', '主打地图')} 为主力战区（胜率 {m_top.get('win_rate', '50%')}），"
        if not weapon_desc and not map_desc:
            weapon_map_eval = "武器使用较为均衡，主战步枪熟练度过关；建议拓展非常规副选武器熟练度，并在非常规地图上加深道具投掷点位储备。"
        else:
            weapon_map_eval = f"{weapon_desc}{map_desc}在主力图上熟悉度极高，但次选地图与非常规地图的控图深度和防守道具联动存在明显断档，需拓展地图池广度。"

        if wr < 50.0 and rating >= 1.10:
            bottleneck_eval = "存在典型‘虚高Rating’病灶：击杀与伤害未能有效转化为胜局贡献（RWS），多见于残局保枪或无效刷分。建议前置对枪身位，将火力转化为攻点首杀与防守首杀。"
        elif breach >= 80.0 and kd < 1.05:
            bottleneck_eval = "突破进攻侵略性极高但首杀后白给率偏高，属于‘高损耗冲锋’。需控制第一身位推进速度，强化二道烟闪掩护并等待队友就位补枪，降低非必要减员。"
        elif prop < 70.0:
            bottleneck_eval = "道具维度成为突破高分天梯的明显掣肘。在纯枪法之外，欠缺反清回防闪、瞬爆封路烟与深层控图火的配合，必须系统化提升常规点位成套道具熟练度。"
        elif hs < 36.0:
            bottleneck_eval = "第一发爆头定位偏弱，击杀过度依赖中近距离扫射压枪，在中远距离对抗时劣势显著。建议每日安排预瞄急停定位与创意工坊爆头死斗训练。"
        else:
            bottleneck_eval = "整体基础扎实，当前主要瓶颈在于顺风顺水向逆风抗压的转换能力。需在比分落后时主动调整防守反常规架枪策略与残局强拆心理博弈，提高关键回合翻盘率。"

        detail = (
            f"【战力定位】{power_eval}\n"
            f"【技术风格与职业对标】{tech_eval}\n"
            f"【偏科与武器地图】{weapon_map_eval}\n"
            f"【天梯瓶颈突破】{bottleneck_eval}"
        )
        return LLMResult(title=title[:24], detail=detail)

    @staticmethod
    def _generate_smart_match_fallback(match_context: dict) -> LLMResult:
        """基于对局比分、攻防半场与全员对位数据智能生成单局战术复盘报告（兜底生成算法）"""
        map_name = str(match_context.get("map") or "常规地图")
        result_text = str(match_context.get("result") or "对局结束")
        final_score = match_context.get("final_score") or {}
        score_text = str(final_score.get("text") or "")
        our_score = int(final_score.get("our") or 0)
        enemy_score = int(final_score.get("enemy") or 0)
        if not score_text:
            score_text = f"{our_score}:{enemy_score}" if (our_score or enemy_score) else "13:x"

        is_win = "胜" in result_text or our_score > enemy_score
        is_tie = "平" in result_text or (our_score == enemy_score and our_score > 0)

        player = match_context.get("player") or {}
        kills = int(player.get("kills") or 0)
        deaths = int(player.get("deaths") or 0)
        assists = int(player.get("assists") or 0)
        rating = float(player.get("rating") or 1.0)
        adr = float(player.get("adr") or 75.0)
        first_kills = int(player.get("first_kills") or 0)
        clutches = int(player.get("clutch_wins") or 0)
        multi_kills = int(player.get("multi_kills") or 0)

        teammates = match_context.get("teammates") or []
        all_team_ratings = [rating] + [float(t.get("rating") or 0) for t in teammates if t.get("rating")]
        all_team_ratings.sort(reverse=True)
        rank_in_team = all_team_ratings.index(rating) + 1 if rating in all_team_ratings else 1

        opponents = match_context.get("opponents") or []
        top_opp = opponents[0] if opponents else {}
        top_opp_name = str(top_opp.get("nickname") or "敌方核心")

        if is_win:
            if rank_in_team == 1 and rating >= 1.25:
                title = "正面摧毁·绝对带飞核心"
            elif first_kills >= 3:
                title = "锋刃破局·关键胜局先锋"
            elif clutches >= 1:
                title = "大心脏残局·终结悬念"
            else:
                title = "协同稳健·奠定胜利基石"
        else:
            if rank_in_team == 1 and rating >= 1.15:
                title = "孤勇扛旗·尽力型败局孤胆"
            elif rating < 0.85 or deaths >= kills + 5:
                title = "状态低迷·正面交火受限"
            else:
                title = "惜败局势·关键回合欠火候"

        score_diff = abs(our_score - enemy_score)
        if is_win:
            if score_diff <= 2:
                trend = f"在 {map_name} 经过激战以 {score_text} 险胜。双方在关键经济局展开激烈博弈，胜负手出现在后半程的关键长枪局与残局强拆。"
            else:
                trend = f"在 {map_name} 以 {score_text} 轻松拿下比赛。全队在攻守两端建立起巨大经济与站位优势，始终牢牢掌控交火节奏。"
        elif is_tie:
            trend = f"在 {map_name} 战成 {score_text} 握手言和。两队比分咬合极紧，攻守互换后数次回合反转将悬念保留到最后一刻。"
        else:
            if score_diff <= 2:
                trend = f"在 {map_name} 以 {score_text} 惜败。开局比分接近，但下半场在关键经济重置局遭遇对手反扑，未能守住微弱领先优势。"
            else:
                trend = f"在 {map_name} 以 {score_text} 告负。开局交火处境被动，防线数次被对手战术道具撕裂，经济持续崩溃导致崩盘。"

        perf = (
            f"全场贡献 {kills} 杀 {deaths} 亡 {assists} 助攻，Rating 达到 {rating:.2f}，ADR 为 {adr:.1f}。"
            f"斩获 {first_kills} 次首杀突破、{clutches} 次关键残局与 {multi_kills} 次多杀高光，"
        )
        if rating >= 1.20:
            perf += "正面拼抢与补枪效率极高，对枪第一反应果断，在多个关键回合打出摧毁性击杀。"
        elif rating >= 1.00:
            perf += "攻防发挥可圈可点，基本完成常规防守选位与进攻道具协同，交火表现稳定。"
        else:
            perf += "正面受制于对手道具封锁与多角度交叉火力，首发定位效率不足，交火略显被动。"

        if rank_in_team == 1:
            team_comp = f"个人数据高居全队第 1 位，在火力输出与战场影响力上承担主要重任，对位敌方核心 {top_opp_name} 丝毫不落下风。"
        elif rank_in_team <= 3:
            team_comp = f"位列全队第 {rank_in_team} 位，有效分担了主攻手火力，在反清与补枪环节表现扎实，团队协同紧密。"
        else:
            team_comp = f"位列全队第 {rank_in_team} 位，相较队友状态略有起伏，在与敌方主力 {top_opp_name} 对位拼抢时未能占得便宜。"

        if deaths > kills:
            sugg = "需重点反思白给回合，减少无道具掩护下的单人前压窥视；长枪局注意与队友拉开双人补枪身位。"
        elif first_kills == 0:
            sugg = "首杀参与偏低导致打法偏保守，进攻端应积极跟进突破手补枪，防守端适度前压侦查以获取首要信息。"
        elif clutches == 0 and not is_win:
            sugg = "残局处理需加强对比赛时钟的精准把控与假拆信息博弈，残局切忌急躁主动探头寻找对枪。"
        else:
            sugg = "保持当前良好的正面交火节奏，后续可进一步强化道具反清深度以及逆风局的保枪经济规划。"

        detail = (
            f"【战局走势】{trend}\n"
            f"【核心表现】{perf}\n"
            f"【团队对比】{team_comp}\n"
            f"【改进建议】{sugg}"
        )
        return LLMResult(title=title[:24], detail=detail)

    async def evaluate(self, match_context: dict, *, refresh: bool = False) -> LLMResult:
        cache_key = self._build_match_cache_key(match_context)
        if not refresh:
            cached = self._get_cached(cache_key)
            if cached:
                return cached

        if not self.enabled or (not self.api_key and (not self.backup_enabled or not self.backup_api_key)):
            fallback = self._generate_smart_match_fallback(match_context)
            self._set_cached(cache_key, fallback)
            return fallback

        user_prompt = (
            "请基于以下CS2整场对局的多维统计数据（包含比赛比分走向、个人高光与核心指标、全队及对手数据对比），"
            "严格遵循分析师规范输出JSON：\n"
            "{\n"
            '  "title": "6-14字精准概括打法风格与表现定位",\n'
            '  "detail": "200-320字系统复盘报告。必须严格使用【战局走势】【核心表现】【团队对比】【改进建议】四个标签清晰呈现，语言专业犀利、切中要害。"\n'
            "}\n"
            "仅输出合法JSON，不要包含任何额外说明或Markdown外包装。\n\n"
            f"对局数据:\n{json.dumps(match_context, ensure_ascii=False)}"
        )

        content = ""
        system_prompt = self.system_prompt or DEFAULT_MATCH_SYSTEM_PROMPT
        try:
            if self.api_key:
                content = await self._call_llm(
                    user_prompt,
                    system_prompt=system_prompt,
                    api_type=self.api_type,
                    api_url=self.api_url,
                    api_key=self.api_key,
                    model=self.model,
                )
        except Exception as e:
            logger.warning(f"[cs2radar] Primary LLM failed: {e}")

        if not content and self.backup_enabled and self.backup_api_key:
            try:
                content = await self._call_llm(
                    user_prompt,
                    system_prompt=system_prompt,
                    api_type=self.backup_api_type,
                    api_url=self.backup_api_url,
                    api_key=self.backup_api_key,
                    model=self.backup_model,
                )
            except Exception as e:
                logger.warning(f"[cs2radar] Backup LLM failed: {e}")

        obj = self._extract_json(content) if content else None
        if not obj:
            fallback = self._generate_smart_match_fallback(match_context)
            self._set_cached(cache_key, fallback)
            return fallback

        title = str(obj.get("title") or "风格待定").strip()
        detail = str(obj.get("detail") or "").strip()
        if not detail:
            fallback = self._generate_smart_match_fallback(match_context)
            self._set_cached(cache_key, fallback)
            return fallback

        result = LLMResult(title=title[:24], detail=detail[:1000])
        self._set_cached(cache_key, result)
        return result

    async def evaluate_profile(
        self,
        profile_context: dict,
        *,
        platform: str = "pw",
        refresh: bool = False,
        target_steam_id: str = "",
        match_cnt: int = 0,
        season_id: str = "",
    ) -> LLMResult:
        cache_key = f"profile_v2_{platform}_{target_steam_id}_{match_cnt}_{season_id}"
        if not refresh:
            cached = self._get_cached(cache_key)
            if cached:
                return cached

        if not self.enabled or (not self.api_key and (not self.backup_enabled or not self.backup_api_key)):
            fallback = self._generate_smart_profile_fallback(profile_context)
            self._set_cached(cache_key, fallback)
            return fallback

        user_prompt = (
            "请基于以下CS2玩家赛季综合生涯战绩（包含天梯分数、核心攻防数据、六维能力评分、常用武器与地图池、近期战绩波动及职业选手属性基准），"
            "严格遵循电竞职业分析师规范输出JSON：\n"
            "{\n"
            '  "title": "6-14字精准概括玩家定位与战力画像（如：超强破点锋刃·对标donk / 控图残局大师·对标ropz）",\n'
            '  "detail": "220-350字系统画像分析。必须严格使用【战力定位】【技术风格与职业对标】【偏科与武器地图】【天梯瓶颈突破】四个标签清晰分段，语言专业硬核、数据说话、切中要害。"\n'
            "}\n"
            "仅输出合法JSON，不要包含任何额外说明或Markdown外包装。\n\n"
            f"生涯数据:\n{json.dumps(profile_context, ensure_ascii=False)}"
        )

        content = ""
        try:
            if self.api_key:
                content = await self._call_llm(
                    user_prompt,
                    system_prompt=DEFAULT_PROFILE_SYSTEM_PROMPT,
                    api_type=self.api_type,
                    api_url=self.api_url,
                    api_key=self.api_key,
                    model=self.model,
                )
        except Exception as e:
            logger.warning(f"[cs2radar] Primary LLM profile evaluation failed: {e}")

        if not content and self.backup_enabled and self.backup_api_key:
            try:
                content = await self._call_llm(
                    user_prompt,
                    system_prompt=DEFAULT_PROFILE_SYSTEM_PROMPT,
                    api_type=self.backup_api_type,
                    api_url=self.backup_api_url,
                    api_key=self.backup_api_key,
                    model=self.backup_model,
                )
            except Exception as e:
                logger.warning(f"[cs2radar] Backup LLM profile evaluation failed: {e}")

        obj = self._extract_json(content) if content else None
        if not obj:
            fallback = self._generate_smart_profile_fallback(profile_context)
            self._set_cached(cache_key, fallback)
            return fallback

        title = str(obj.get("title") or "全能型竞技核心").strip()
        detail = str(obj.get("detail") or "").strip()
        if not detail:
            fallback = self._generate_smart_profile_fallback(profile_context)
            self._set_cached(cache_key, fallback)
            return fallback

        result = LLMResult(title=title[:24], detail=detail[:1000])
        self._set_cached(cache_key, result)
        return result

    async def _call_llm(
        self,
        user_prompt: str,
        *,
        system_prompt: str,
        api_type: str,
        api_url: str,
        api_key: str,
        model: str,
    ) -> str:
        api_type = self._normalize_api_type(api_type, api_url)
        if api_type == "gemini":
            return await self._call_gemini(user_prompt, system_prompt=system_prompt, api_url=api_url, api_key=api_key, model=model)
        if api_type == "anthropic":
            return await self._call_anthropic(user_prompt, system_prompt=system_prompt, api_url=api_url, api_key=api_key, model=model)
        return await self._call_openai(user_prompt, system_prompt=system_prompt, api_url=api_url, api_key=api_key, model=model)

    async def _call_openai(
        self,
        user_prompt: str,
        *,
        system_prompt: str,
        api_url: str,
        api_key: str,
        model: str,
    ) -> str:
        url = api_url if api_url.endswith("/chat/completions") else f"{api_url}/chat/completions"
        payload = {
            "model": model,
            "temperature": 0.6,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        return data.get("choices", [{}])[0].get("message", {}).get("content", "")

    async def _call_gemini(
        self,
        user_prompt: str,
        *,
        system_prompt: str,
        api_url: str,
        api_key: str,
        model: str,
    ) -> str:
        if "generateContent" not in api_url:
            if not api_url.endswith("/"):
                api_url += "/"
            if "models/" not in api_url:
                api_url += f"v1beta/models/{model}:generateContent"
            else:
                api_url += ":generateContent"
        connector = "&" if "?" in api_url else "?"
        if "key=" not in api_url:
            api_url = f"{api_url}{connector}key={api_key}"

        payload = {
            "contents": [
                {
                    "parts": [{"text": system_prompt + "\n\n" + user_prompt}]
                }
            ],
            "generationConfig": {"temperature": 0.6}
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(api_url, json=payload, headers=headers if "headers" in locals() else None)
            resp.raise_for_status()
            data = resp.json()

        try:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError):
            return ""

    async def _call_anthropic(
        self,
        user_prompt: str,
        *,
        system_prompt: str,
        api_url: str,
        api_key: str,
        model: str,
    ) -> str:
        url = api_url if api_url.endswith("/messages") else f"{api_url}/messages"
        payload = {
            "model": model,
            "max_tokens": 1024,
            "temperature": 0.6,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        }
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        content = data.get("content", [])
        texts = [str(x.get("text", "")) for x in content if isinstance(x, dict)]
        return "\n".join([x for x in texts if x]).strip()

    @staticmethod
    def _normalize_api_type(api_type: str, api_url: str) -> str:
        v = (api_type or "openai").strip().lower()
        if v in {"openai", "gemini", "anthropic"}:
            return v
        url = (api_url or "").lower()
        if "generativelanguage.googleapis.com" in url or "gemini" in url:
            return "gemini"
        if "anthropic.com" in url:
            return "anthropic"
        return "openai"

    @staticmethod
    def _extract_json(text: str) -> dict | None:
        if not text:
            return None
        text = text.strip()
        try:
            return json.loads(text)
        except Exception:
            pass

        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            return json.loads(text[start : end + 1])
        except Exception:
            return None

    @staticmethod
    def _fallback(text: str) -> LLMResult:
        cleaned = (text or "").strip().replace("\n", " ")
        if not cleaned:
            return LLMResult(
                title="评价暂不可用",
                detail="【战力定位】模型返回异常，本次先展示战绩数据。",
            )
        title = cleaned[:14]
        if len(title) < 6:
            title = "风格概览"
        return LLMResult(title=title, detail=cleaned[:220])
