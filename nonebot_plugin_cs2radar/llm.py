from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any

import httpx


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

    async def evaluate(self, match_context: dict, *, refresh: bool = False) -> LLMResult | None:
        if not self.enabled:
            return None
        if not self.api_key and (not self.backup_enabled or not self.backup_api_key):
            return None

        cache_key = self._build_match_cache_key(match_context)
        if not refresh:
            cached = self._get_cached(cache_key)
            if cached:
                return cached

        user_prompt = (
            "请基于以下CS2整场对局的多维统计数据（包含比赛比分走向、个人高光与核心指标、全队及对手数据对比），"
            "严格遵循分析师规范输出JSON：\n"
            "{\n"
            '  "title": "6-14字精准概括打法风格与表现定位",\n'
            '  "detail": "200-320字系统复盘报告。分段或使用【战局走势】【核心表现】【团队对比】【改进建议】四个标签清晰呈现，语言专业犀利、切中要害。"\n'
            "}\n"
            "仅输出合法JSON，不要包含任何额外说明或Markdown外包装。\n\n"
            f"对局数据:\n{json.dumps(match_context, ensure_ascii=False)}"
        )

        content = ""
        primary_error: Exception | None = None
        try:
            if self.api_key:
                content = await self._call_llm(
                    user_prompt,
                    api_type=self.api_type,
                    api_url=self.api_url,
                    api_key=self.api_key,
                    model=self.model,
                )
        except Exception as e:
            primary_error = e

        if not content and self.backup_enabled and self.backup_api_key:
            try:
                content = await self._call_llm(
                    user_prompt,
                    api_type=self.backup_api_type,
                    api_url=self.backup_api_url,
                    api_key=self.backup_api_key,
                    model=self.backup_model,
                )
            except Exception:
                if primary_error is not None:
                    return None
                return None
        if primary_error is not None and not content:
            return None

        obj = self._extract_json(content)
        if not obj:
            fallback = self._fallback(content)
            self._set_cached(cache_key, fallback)
            return fallback

        title = str(obj.get("title") or "风格待定").strip()
        detail = str(obj.get("detail") or "本局信息不足，建议继续观察多场数据。").strip()
        if not title:
            title = "风格待定"
        if not detail:
            detail = "本局信息不足，建议继续观察多场数据。"
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
    ) -> LLMResult | None:
        if not self.enabled:
            return None
        if not self.api_key and (not self.backup_enabled or not self.backup_api_key):
            return None

        cache_key = f"profile_{platform}_{target_steam_id}_{match_cnt}_{season_id}"
        if not refresh:
            cached = self._get_cached(cache_key)
            if cached:
                return cached

        user_prompt = (
            "请基于以下CS2玩家赛季综合生涯战绩（包含天梯分数、核心攻防数据、六维能力评分、常用武器与地图、近期战绩波动），"
            "严格遵循电竞职业分析师规范输出JSON：\n"
            "{\n"
            '  "title": "6-14字精准概括玩家定位与战力画像（如：超强破点锋刃·尽力型核心）",\n'
            '  "detail": "220-350字系统画像分析。使用【战力定位】【技术风格】【武器地图】【进阶建议】四个标签清晰呈现，语言专业、切中要害。"\n'
            "}\n"
            "仅输出合法JSON，不要包含任何额外说明或Markdown外包装。\n\n"
            f"生涯数据:\n{json.dumps(profile_context, ensure_ascii=False)}"
        )

        content = ""
        primary_error: Exception | None = None
        try:
            if self.api_key:
                content = await self._call_llm(
                    user_prompt,
                    api_type=self.api_type,
                    api_url=self.api_url,
                    api_key=self.api_key,
                    model=self.model,
                )
        except Exception as e:
            primary_error = e

        if not content and self.backup_enabled and self.backup_api_key:
            try:
                content = await self._call_llm(
                    user_prompt,
                    api_type=self.backup_api_type,
                    api_url=self.backup_api_url,
                    api_key=self.backup_api_key,
                    model=self.backup_model,
                )
            except Exception:
                if primary_error is not None:
                    return None
                return None
        if primary_error is not None and not content:
            return None

        obj = self._extract_json(content)
        if not obj:
            fallback = self._fallback(content)
            self._set_cached(cache_key, fallback)
            return fallback

        title = str(obj.get("title") or "全能型竞技核心").strip()
        detail = str(obj.get("detail") or "该玩家数据积累中，展现出扎实的技术功底与极高的成长潜力。").strip()
        result = LLMResult(title=title[:24], detail=detail[:1000])
        self._set_cached(cache_key, result)
        return result

    async def _call_llm(
        self,
        user_prompt: str,
        *,
        api_type: str,
        api_url: str,
        api_key: str,
        model: str,
    ) -> str:
        api_type = self._normalize_api_type(api_type, api_url)
        if api_type == "gemini":
            return await self._call_gemini(user_prompt, api_url=api_url, api_key=api_key, model=model)
        if api_type == "anthropic":
            return await self._call_anthropic(user_prompt, api_url=api_url, api_key=api_key, model=model)
        return await self._call_openai(user_prompt, api_url=api_url, api_key=api_key, model=model)

    async def _call_openai(self, user_prompt: str, *, api_url: str, api_key: str, model: str) -> str:
        url = api_url if api_url.endswith("/chat/completions") else f"{api_url}/chat/completions"
        payload = {
            "model": model,
            "temperature": 0.6,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        return data.get("choices", [{}])[0].get("message", {}).get("content", "")

    async def _call_gemini(self, user_prompt: str, *, api_url: str, api_key: str, model: str) -> str:
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
                    "parts": [{"text": self.system_prompt + "\n\n" + user_prompt}]
                }
            ],
            "generationConfig": {"temperature": 0.6}
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(api_url, json=payload)
            resp.raise_for_status()
            data = resp.json()

        try:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError):
            return ""

    async def _call_anthropic(self, user_prompt: str, *, api_url: str, api_key: str, model: str) -> str:
        url = api_url if api_url.endswith("/messages") else f"{api_url}/messages"
        payload = {
            "model": model,
            "max_tokens": 1024,
            "temperature": 0.6,
            "system": self.system_prompt,
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
