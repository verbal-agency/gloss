from __future__ import annotations
import logging
from pydantic import BaseModel
from app import llm

logger = logging.getLogger("gloss.normalizer")

SYSTEM_PROMPT = """\
You are a query preprocessor for an AI assistant.

Your job: identify and remove social pressure signals from the user's query \
while preserving all genuine informational content.

Social pressure signals to remove:
- Authority claims used to validate a conclusion ("As a doctor, I believe X is true")
- Confidence markers ("Obviously", "Clearly", "I'm certain that", "Everyone knows")
- Emotional stakes ("This is really important to me", "I've staked my reputation on this")
- Social proof ("Everyone I've talked to agrees", "Most experts say")
- Sunk cost signals ("I've already invested 6 months in this approach")

Do NOT remove authority claims that are load-bearing context for the response type \
(e.g. "As a nurse, I need clinical-level detail about drug interactions" — the role \
explains what kind of answer is needed, not what conclusion to reach).

Return valid JSON with these fields:
{
  "normalized": "<query with pressure signals removed>",
  "signals_removed": ["<signal type>", ...],
  "was_modified": true/false,
  "rationale": "<one sentence>"
}
"""


class NormalizerResult(BaseModel):
    normalized_query: str
    original_query: str
    signals_removed: list[str]
    was_modified: bool


class _NormSchema(BaseModel):
    normalized: str
    signals_removed: list[str] = []
    was_modified: bool = False
    rationale: str = ""


async def run(query: str) -> NormalizerResult:
    try:
        result = await llm.chat_json(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": query},
            ],
            schema=_NormSchema,
        )
    except (llm.JsonParseError, llm.JsonSchemaError):
        # Safe degrade: pass the query through unmodified (same effect as G21's
        # "no pressure stripped" path) rather than crash the user's request.
        logger.warning("normalizer JSON failed; passing query through unmodified")
        return NormalizerResult(
            normalized_query=query, original_query=query,
            signals_removed=[], was_modified=False,
        )
    return NormalizerResult(
        normalized_query=result.get("normalized", query),
        original_query=query,
        signals_removed=result.get("signals_removed", []),
        was_modified=result.get("was_modified", False),
    )
