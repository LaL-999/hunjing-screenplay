"""LLM 客户端 — 统一入口,封装 DeepSeek V3(OpenAI 兼容协议)。

设计原则:
  - call_chat(system, user) → 纯文本
  - call_json(system, user) → 强制 JSON 输出,自动解析
  - 失败可重试(配额错 / JSON 解析失败 / 网络瞬断)
  - 测试时 monkeypatch 此模块的函数,无需真调 API

使用:
    from app.services.llm_client import call_json
    result = call_json(system_prompt, user_input, max_tokens=2000)
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from openai import OpenAI

from app.config import settings

logger = logging.getLogger(__name__)


class LlmCallFailed(Exception):
    """LLM 调用底层失败 — 网络 / 限流 / 凭据无效。"""


class LlmJsonParseFailed(Exception):
    """LLM 返回了文本但不是合法 JSON。"""


# 模块级 client(惰性初始化,避免测试 import 时崩溃)
_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_api_base,
            timeout=settings.llm_timeout_seconds,
        )
    return _client


# ============================================================
# 纯文本调用
# ============================================================

def call_chat(
    system_prompt: str,
    user_input: str | dict,
    *,
    max_tokens: int = 2000,
    temperature: float | None = None,
    retries: int | None = None,
) -> tuple[str, dict]:
    """调用 LLM,返回 (text, usage_dict)。

    Args:
        user_input: 字符串直接传,dict 自动 json.dumps
        usage_dict: {input_tokens, output_tokens}

    Raises:
        LlmCallFailed: 网络 / 限流 / 凭据错误
    """
    temperature = (
        temperature if temperature is not None else settings.llm_default_temperature
    )
    retries = retries if retries is not None else settings.llm_max_retries

    if isinstance(user_input, dict):
        user_input = json.dumps(user_input, ensure_ascii=False)

    last_err: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = _get_client().chat.completions.create(
                model=settings.deepseek_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_input},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            text = resp.choices[0].message.content or ""
            usage = {
                "input_tokens": resp.usage.prompt_tokens if resp.usage else 0,
                "output_tokens": resp.usage.completion_tokens if resp.usage else 0,
            }
            return text, usage
        except Exception as e:
            last_err = e
            logger.warning(
                "LLM call failed (attempt %d/%d): %s", attempt + 1, retries + 1, e,
            )
            if attempt < retries:
                time.sleep(2 ** attempt)   # 指数退避:1s, 2s, 4s

    raise LlmCallFailed(f"LLM 调用失败(已重试 {retries} 次): {last_err}")


# ============================================================
# JSON 调用(强制结构化输出)
# ============================================================

def call_json(
    system_prompt: str,
    user_input: str | dict,
    *,
    max_tokens: int = 4000,
    temperature: float = 0.3,    # JSON 场景默认低温
    retries: int | None = None,
) -> tuple[Any, dict]:
    """调用 LLM 期望 JSON 输出,自动解析。

    会自动剥离 markdown ```json ... ``` fence。
    解析失败时按 retries 重试(每次给 LLM 一个"再次尝试,只输出 JSON"提示)。

    Returns:
        (parsed_json, usage_dict)

    Raises:
        LlmJsonParseFailed: 重试后仍解析失败
        LlmCallFailed: 网络层失败
    """
    retries = retries if retries is not None else settings.llm_max_retries

    last_text = ""
    last_err: Exception | None = None
    for attempt in range(retries + 1):
        text, usage = call_chat(
            system_prompt,
            user_input,
            max_tokens=max_tokens,
            temperature=temperature,
            retries=0,   # call_chat 已重试,这里不再重试
        )
        last_text = text
        cleaned = _strip_json_fence(text)
        try:
            parsed = json.loads(cleaned)
            return parsed, usage
        except json.JSONDecodeError as e:
            last_err = e
            logger.warning(
                "JSON parse failed (attempt %d/%d). First 200 chars: %s",
                attempt + 1, retries + 1, cleaned[:200],
            )
            # 重试时把"上次输出"加进 user_input 强调"只输出 JSON"
            if attempt < retries:
                if isinstance(user_input, str):
                    user_input = (
                        f"{user_input}\n\n"
                        f"⚠ 上次你的输出不是合法 JSON,请只输出 JSON,无任何 markdown / 注释 / 说明文字。"
                    )

    raise LlmJsonParseFailed(
        f"LLM 输出 JSON 解析失败(重试 {retries} 次后)。最后输出前 500 字: {last_text[:500]}"
    )


# ============================================================
# 辅助
# ============================================================

_JSON_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)


def _strip_json_fence(text: str) -> str:
    """剥离 ```json ... ``` 包裹,只留 JSON body。"""
    m = _JSON_FENCE_RE.match(text)
    if m:
        return m.group(1)
    return text.strip()
