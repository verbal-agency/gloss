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


async def chat(
    messages: list[dict[str, str]],
    model: str | None = None,
    response_format: dict | None = None,
    temperature: float | None = None,
) -> str:
    kwargs: dict[str, Any] = {
        "model": model or settings.litellm_model,
        "messages": messages,
    }
    if response_format:
        kwargs["response_format"] = response_format
    if temperature is not None:
        kwargs["temperature"] = temperature

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


async def embed(texts: list[str]) -> list[list[float]]:
    response = await litellm.aembedding(
        model=settings.litellm_embedding_model,
        input=texts,
    )
    return [item["embedding"] for item in response.data]
