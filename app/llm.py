from __future__ import annotations
import json
import re
import asyncio
import contextvars
from typing import Any
import litellm
from pydantic import BaseModel, ValidationError
from app.config import settings

litellm.drop_params = True


class CallBudgetExceeded(RuntimeError):
    """A single request tried to make more upstream LLM calls than the cap."""
    def __init__(self, budget: int):
        self.budget = budget
        super().__init__(f"per-request LLM call budget ({budget}) exceeded")


class _Budget:
    """Mutable call counter. Stored in a ContextVar by reference, so the copies
    that asyncio.gather / create_task make of the context all share this one
    object — increments from concurrent pipeline calls accumulate correctly."""
    def __init__(self, cap: int):
        self.n = 0
        self.cap = cap

    def tick(self) -> None:
        self.n += 1
        if self.cap and self.n > self.cap:
            raise CallBudgetExceeded(self.cap)


_budget: contextvars.ContextVar[_Budget | None] = contextvars.ContextVar("gloss_budget", default=None)


def reset_call_budget() -> None:
    """Start a fresh per-request budget. Call at the top of a request handler;
    calls made outside a reset window (e.g. the composable stage endpoints) are
    unbudgeted."""
    _budget.set(_Budget(settings.max_llm_calls_per_request))


def _tick_budget() -> None:
    b = _budget.get()
    if b is not None:
        b.tick()

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
    # Count every completion against the per-request budget. chat_json routes
    # through here too, so JSON calls (and their retries) are counted as well.
    _tick_budget()

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


class JsonParseError(ValueError):
    """The model returned text that isn't valid JSON, twice. Carries the raw
    text so callers can log/skip rather than crash on a bare decode error."""
    def __init__(self, raw: str):
        self.raw = raw
        super().__init__(f"model did not return valid JSON: {raw[:200]!r}")


class JsonSchemaError(ValueError):
    """The model returned valid JSON of the WRONG shape, twice. Distinct from a
    parse failure: this is the silent-corruption case (valid JSON that would
    otherwise be read with .get(...) defaults into a wrong result)."""
    def __init__(self, raw: str, errors):
        self.raw = raw
        self.errors = errors
        super().__init__(f"model JSON did not match schema: {str(errors)[:200]}")


def _extract_json(text: str) -> dict:
    text = text.strip()
    # Strip markdown code fences if the model wraps the JSON anyway
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\n?", "", text)
        text = re.sub(r"\n?```$", "", text.strip())
        text = text.strip()
    return json.loads(text)


async def chat_json(
    messages: list[dict[str, str]],
    model: str | None = None,
    temperature: float = 0.0,
    schema: type[BaseModel] | None = None,
) -> dict:
    """Return a dict of parsed JSON. When `schema` is given, the JSON is
    validated/coerced against it before returning — a valid-JSON-wrong-shape
    response raises JsonSchemaError instead of silently reaching a caller's
    `.get(key, default)`. Retries once on either failure (LLMs self-correct)."""
    # response_format is dropped by litellm for Claude; enforce JSON via explicit instruction.
    enforced = list(messages)
    for i in range(len(enforced) - 1, -1, -1):
        if enforced[i]["role"] == "user":
            enforced[i] = {**enforced[i], "content": enforced[i]["content"] + _JSON_INSTRUCTION}
            break

    def _parse(text: str) -> dict:
        data = _extract_json(text)                       # may raise JSONDecodeError
        if schema is not None:
            return schema.model_validate(data).model_dump()  # may raise ValidationError
        return data

    text = await chat(enforced, model=model, temperature=temperature)
    try:
        return _parse(text)
    except (json.JSONDecodeError, ValidationError):
        # One retry — LLMs frequently self-correct. Nudge temperature up so a
        # deterministic bad completion has a chance to vary.
        retry_text = await chat(enforced, model=model, temperature=max(temperature, 0.4))
        try:
            return _parse(retry_text)
        except json.JSONDecodeError:
            raise JsonParseError(retry_text)
        except ValidationError as e:
            raise JsonSchemaError(retry_text, e.errors())


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
