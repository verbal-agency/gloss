from __future__ import annotations
import json
import re
import asyncio
from typing import Any
import litellm
from app.config import settings

litellm.drop_params = True

_JSON_INSTRUCTION = (
    "\n\nIMPORTANT: Respond with valid JSON only. "
    "No markdown, no code fences, no explanation outside the JSON object."
)


def resolve_model(model: str | None) -> str:
    """Map an Anthropic-API-style model id to a LiteLLM model id.

    Clients of the proxy send bare Anthropic ids ("claude-sonnet-4-6");
    LiteLLM wants a provider prefix. Ids that already carry a provider
    prefix pass through untouched.
    """
    if not model:
        return settings.litellm_model
    if "/" in model:
        return model
    if model.startswith("claude"):
        return f"anthropic/{model}"
    return model


async def chat(
    messages: list[dict[str, str]],
    model: str | None = None,
    response_format: dict | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> str:
    kwargs: dict[str, Any] = {
        "model": resolve_model(model),
        "messages": messages,
    }
    if response_format:
        kwargs["response_format"] = response_format
    if temperature is not None:
        kwargs["temperature"] = temperature
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens

    response = await litellm.acompletion(**kwargs)
    return response.choices[0].message.content


async def chat_json(
    messages: list[dict[str, str]],
    model: str | None = None,
    temperature: float = 0.0,
) -> dict:
    # response_format is dropped by litellm for Claude; enforce JSON via explicit instruction.
    enforced = list(messages)
    for i in range(len(enforced) - 1, -1, -1):
        if enforced[i]["role"] == "user":
            enforced[i] = {**enforced[i], "content": enforced[i]["content"] + _JSON_INSTRUCTION}
            break

    text = await chat(enforced, model=model, temperature=temperature)
    text = text.strip()
    # Strip markdown code fences if the model wraps the JSON anyway
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\n?", "", text)
        text = re.sub(r"\n?```$", "", text.strip())
        text = text.strip()
    return json.loads(text)


def count_tokens(
    model: str | None = None,
    messages: list[dict[str, str]] | None = None,
    text: str | None = None,
) -> int:
    """Token count for the usage field. Falls back to a chars/4 estimate
    if the tokenizer for the model is unavailable."""
    resolved = resolve_model(model)
    try:
        if messages is not None:
            return litellm.token_counter(model=resolved, messages=messages)
        return litellm.token_counter(model=resolved, text=text or "")
    except Exception:
        source = text if text is not None else " ".join(
            str(m.get("content", "")) for m in (messages or [])
        )
        return max(1, len(source) // 4)


async def embed(texts: list[str]) -> list[list[float]]:
    response = await litellm.aembedding(
        model=settings.litellm_embedding_model,
        input=texts,
    )
    return [item["embedding"] for item in response.data]
