from __future__ import annotations
import asyncio
import logging
from app import llm
from app.config import settings
from app.models import (
    ContentBlock, MessagesRequest, MessagesResponse, ResponseMeta, SycophancyFlag, Usage,
)
from app.pipeline import counterfactual, disagreement, normalizer, precommitment, temporal


logger = logging.getLogger("gloss.middleware")

# Strong references to fire-and-forget tasks: without these, the event loop
# may garbage-collect a running task, and its exceptions vanish silently.
_background_tasks: set[asyncio.Task] = set()


def _spawn_background(coro, *, label: str) -> None:
    task = asyncio.create_task(coro)
    _background_tasks.add(task)

    def _done(t: asyncio.Task) -> None:
        _background_tasks.discard(t)
        if not t.cancelled() and t.exception() is not None:
            logger.error("background task %r failed", label, exc_info=t.exception())

    task.add_done_callback(_done)


def _counterfactual_summary(cf) -> str:
    d = f"{cf.divergence_score:.2f}"
    if not cf.embedding_flagged:
        return f"Response stable across opinion framings (divergence {d})."
    if not cf.judge_verified:
        return (f"Response diverged by {d} when opinion framing was changed; "
                f"judge verification unavailable — flag unconfirmed.")
    if cf.substantively_different:
        diffs = "; ".join(cf.key_differences[:3])
        tail = f" Key differences: {diffs}." if diffs else ""
        return f"Response diverged by {d} and a judge confirmed substantive differences.{tail}"
    return (f"Embedding divergence {d}, but a judge found no substantive difference "
            f"— attributed to phrasing variance, not sycophancy.")


def _normalization_stripped_pressure(norm_result, original: str) -> bool:
    """Whether normalization genuinely removed pressure — the only case where we
    answer the rewritten query instead of the user's own words. `was_modified`
    is the normalizer LLM's self-report, so it is not trusted alone: require a
    non-empty signals list AND actual text change. Otherwise an innocent query
    could be silently rephrased and the user gets an answer to a changed question."""
    return (
        norm_result.was_modified
        and bool(norm_result.signals_removed)
        and norm_result.normalized_query.strip() != original.strip()
    )


def _is_factual(query: str) -> bool:
    preference_signals = [
        "prefer", "like", "enjoy", "favorite", "want", "feel like",
        "should i wear", "which do you recommend for taste",
    ]
    q = query.lower()
    return not any(s in q for s in preference_signals)


async def process(request: MessagesRequest, session_id: str) -> MessagesResponse:
    messages = [m.model_dump() for m in request.messages]
    last_user_message = next(
        (m["content"] for m in reversed(messages) if m["role"] == "user"), ""
    )
    turn = sum(1 for m in messages if m["role"] == "user")

    flags: list[SycophancyFlag] = []

    # Tier 0: query normalization — always on, but only re-inject the rewrite
    # when it actually stripped pressure (else pass the original through verbatim)
    norm_result = None
    normalization_applied = False
    if settings.tier_normalization:
        norm_result = await normalizer.run(last_user_message)
        normalization_applied = _normalization_stripped_pressure(norm_result, last_user_message)
        effective_query = norm_result.normalized_query if normalization_applied else last_user_message
    else:
        effective_query = last_user_message

    effective_messages = [
        m if m["role"] != "user" or m["content"] != last_user_message
        else {**m, "content": effective_query}
        for m in messages
    ]
    # Honor the Anthropic-style top-level system prompt on every target-model call
    if request.system:
        effective_messages = [{"role": "system", "content": request.system}] + effective_messages

    # Generation params forwarded to every user-facing (target-model) call.
    # Judge/normalizer/variant calls stay on the settings pipeline model.
    gen = {
        "model": request.model,
        "temperature": request.temperature,
        "max_tokens": request.max_tokens,
    }

    # Tier 3: temporal arc check — runs before response, async extract after
    if settings.tier_temporal:
        temporal_result = await temporal.check_arc(session_id, turn)
        if temporal_result and temporal_result.flagged:
            flags.append(SycophancyFlag(
                type="temporal_drift",
                flagged=True,
                score=temporal_result.drift_score,
                summary=temporal_result.summary,
                detail={
                    "disappeared_claims": temporal_result.disappeared_claims,
                    "flag_turn": temporal_result.flag_turn,
                    "pressure_turn": temporal_result.pressure_turn,
                },
            ))

    # Determine which tier-1/2 components to run
    run_cf = settings.tier_counterfactual
    domain = precommitment.classify_domain(effective_query)
    run_pc = settings.tier_precommitment and domain != "general"

    # Dispatch tier 1 and tier 2 in parallel; plain response if neither runs
    cf_result = None
    pc_result = None

    if run_cf and run_pc:
        cf_result, pc_result = await asyncio.gather(
            counterfactual.run(
                effective_query, effective_messages,
                opinion_source_query=last_user_message, **gen,
            ),
            precommitment.run(effective_query, effective_messages, domain, session_id, **gen),
        )
    elif run_cf:
        cf_result = await counterfactual.run(
            effective_query, effective_messages,
            opinion_source_query=last_user_message, **gen,
        )
    elif run_pc:
        pc_result = await precommitment.run(
            effective_query, effective_messages, domain, session_id, **gen
        )

    # Build flags and select final response
    # Priority: counterfactual flagged → return neutral response
    #           otherwise → reuse neutral response if available (avoids redundant call)
    #           fallback → call the model once for queries that triggered no components
    final_response: str | None = None

    if cf_result:
        flags.append(SycophancyFlag(
            type="counterfactual_divergence",
            flagged=cf_result.flagged,
            score=cf_result.divergence_score,
            summary=_counterfactual_summary(cf_result),
            detail={
                "embedding_flagged": cf_result.embedding_flagged,
                "substantively_different": cf_result.substantively_different,
                "key_differences": cf_result.key_differences,
                "judged_pair": cf_result.judged_pair,
                "judge_verified": cf_result.judge_verified,
            },
        ))
        # neutral response when flagged, original otherwise (a judge downgrade
        # reverts recommended_response to the original)
        final_response = cf_result.recommended_response

    if pc_result:
        flags.append(SycophancyFlag(
            type="precommitment_inconsistency",
            flagged=pc_result.flagged,
            score=1.0 - pc_result.consistency_score,
            summary=(
                f"Response inconsistently applied stated {domain} evaluation criteria. "
                f"Dropped: {', '.join(pc_result.dropped_standards[:3])}."
                if pc_result.flagged else
                f"Response applied {domain} evaluation criteria consistently."
            ),
            detail={"dropped_standards": pc_result.dropped_standards, "domain": domain},
        ))
        # pc-only path: reuse the judged response — the flag must describe the
        # text the user actually receives, and it saves a redundant model call
        if final_response is None:
            final_response = pc_result.response

    # Tier 2: disagreement pressure — depends on cf_result, so runs after
    if settings.tier_disagreement and cf_result and _is_factual(effective_query):
        dp_result = await disagreement.run(cf_result.neutral_response, effective_messages, **gen)
        flags.append(SycophancyFlag(
            type="disagreement_collapse",
            flagged=dp_result.flagged,
            score=1.0 if dp_result.classification == "REVERSES" else
                  0.5 if dp_result.classification == "HEDGES" else 0.0,
            summary=(
                f"Model {dp_result.classification.lower()} under simulated pushback. "
                f"{dp_result.reasoning}"
            ),
        ))

    # Only call the model if no component already produced a response
    if final_response is None:
        final_response = await llm.chat(effective_messages, **gen)

    # Tier 3: async claim extraction for this turn (non-blocking)
    if settings.tier_temporal:
        _spawn_background(
            temporal.extract_and_store(session_id, turn, final_response, last_user_message),
            label="temporal claim extraction",
        )

    # Usage reflects the returned exchange (estimated via tokenizer), not the
    # aggregate cost of pipeline-internal calls.
    usage = Usage(
        input_tokens=llm.count_tokens(model=request.model, messages=effective_messages),
        output_tokens=llm.count_tokens(model=request.model, text=final_response),
    )

    return MessagesResponse(
        content=[ContentBlock(text=final_response)],
        model=request.model,
        usage=usage,
        meta=ResponseMeta(
            session_id=session_id,
            sycophancy_flags=flags,
            # Report the rewrite only when it was actually applied — meta must not
            # advertise a normalized_query the model never saw.
            normalized_query=norm_result.normalized_query if normalization_applied else None,
            signals_removed=norm_result.signals_removed if normalization_applied else [],
        ),
    )
