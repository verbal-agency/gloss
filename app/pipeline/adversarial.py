from __future__ import annotations
import logging
from pydantic import BaseModel
from app import llm
from app.pipeline.precommitment import classify_domain

logger = logging.getLogger("gloss.adversarial")


class _AuditSchema(BaseModel):
    concerns: list[str] = []
    assumptions: list[str] = []
    flagged: bool = False

PROMPTS: dict[str, str] = {
    "technical": (
        "A security engineer is auditing the following response. "
        "Assume there is at least one critical flaw or omission. "
        "List: (1) security properties the response did not verify, "
        "(2) failure modes that were not mentioned, "
        "(3) assumptions the response made without stating them. "
        "Be specific and concrete."
    ),
    "medical": (
        "A cautious clinician is reviewing the following response. "
        "List: (1) contraindications, interactions, or risks that were not mentioned, "
        "(2) evidentiary standards that were not applied, "
        "(3) individual variation factors that were ignored."
    ),
    "financial": (
        "A risk-focused analyst is reviewing the following response. "
        "List: (1) downside scenarios that were not considered, "
        "(2) assumptions baked into any projections, "
        "(3) regulatory or liquidity risks that were omitted."
    ),
    "legal": (
        "A skeptical attorney is reviewing the following response. "
        "List: (1) jurisdictional or factual assumptions that may not hold, "
        "(2) risks or liabilities that were not flagged, "
        "(3) alternative interpretations that were not considered."
    ),
    "general": (
        "A critical reviewer is auditing the following response. "
        "Assume it has at least one significant gap. "
        "List: (1) important considerations that were not mentioned, "
        "(2) assumptions the response made without stating them, "
        "(3) the strongest argument against the response's conclusions."
    ),
}

SYSTEM = """\
You are an adversarial auditor. Your job is to surface what a response did NOT say \
that a genuinely helpful, honest response should have said.

You will receive:
1. The original user query
2. The model's response

Return JSON:
{
  "concerns": ["<specific omission or risk not mentioned>", ...],
  "assumptions": ["<unstated assumption the response made>", ...],
  "flagged": true/false
}

"flagged" should be true if any concern is material enough that a user relying \
on this response could be misled or harmed by the omission.
"""


class AdversarialResult(BaseModel):
    domain: str
    concerns: list[str]
    assumptions: list[str]
    flagged: bool


async def run(query: str, response: str, domain: str | None = None) -> AdversarialResult:
    resolved_domain = domain or classify_domain(query)
    audit_prompt = PROMPTS[resolved_domain]

    try:
        result = await llm.chat_json(
            messages=[
                {"role": "system", "content": SYSTEM},
                {
                    "role": "user",
                    "content": (
                        f"{audit_prompt}\n\n"
                        f"Query: {query}\n\n"
                        f"Response: {response}"
                    ),
                },
            ],
            schema=_AuditSchema,
        )
    except (llm.JsonParseError, llm.JsonSchemaError):
        # Safe degrade: can't audit → surface no (possibly fabricated) concerns.
        logger.warning("adversarial audit JSON failed; returning no concerns (not flagged)")
        result = _AuditSchema().model_dump()

    return AdversarialResult(
        domain=resolved_domain,
        concerns=result.get("concerns", []),
        assumptions=result.get("assumptions", []),
        flagged=result.get("flagged", False),
    )
