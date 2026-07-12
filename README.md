# Gloss

*Catches when a model glosses over the truth to tell you what you want to hear.*

A pluggable middleware service that detects and corrects LLM sycophancy at runtime — no model access required, works via any provider's public API.

## What it does

LLMs trained on human feedback learn to prioritize approval over accuracy. This manifests in three ways:

- **Reactive sycophancy** — the model changes its answer when the user expresses a preference, even if that preference is wrong
- **Epistemic omission** — the model doesn't volunteer critical information the user didn't ask for
- **Framing capture** — the model accepts the user's flawed premises rather than questioning them

This service wraps any LLM API and runs a detection pipeline on every request. It operates as an API-compatible proxy: point your existing client at it instead of directly at the provider, and it transparently detects and corrects sycophantic responses.

## Detection pipeline

Four mechanisms, running in tiers:

| Tier | Component | When it runs | What it catches |
|---|---|---|---|
| 0 | **Query normalization** | Every query | Strips authority claims, confidence markers, emotional stakes before the model sees them |
| 1 | **Counterfactual pairs** | Opinion signal detected | Sends neutral + inverted variants in parallel, scores embedding divergence, then confirms flagged cases with a substantive-difference judge (two-stage: cheap screen + judge) |
| 2 | **Pre-commitment extraction** | High-stakes domain | Locks in evaluation criteria before the primed query; detects if response violates those criteria |
| 2 | **Disagreement pressure** | Opinion signal + factual query | Probes whether position holds under simulated pushback |
| 3 | **Temporal consistency** | Multi-turn (turn ≥ 3) | Detects gradual capitulation across a conversation by tracking claim drift |

Tiers 1 and 2 parallelize their LLM calls — wall-clock latency is the max of the parallel calls, not the sum.

## Setup

**Requirements**: Python 3.10+, Redis

```bash
git clone <repo>
cd gloss
pip install -e ".[dev]"
cp .env.example .env
# Edit .env — set your API key and preferred model
```

**Start Redis** (if not already running):
```bash
redis-server
```

**Start the proxy service**:
```bash
uvicorn app.main:app --reload --port 8001
```

## Usage

The proxy exposes a single endpoint at `POST /v1/messages` with the same request schema as the Anthropic Messages API.

**Drop-in with the Anthropic SDK**:
```python
import anthropic

client = anthropic.Anthropic(
    api_key="your-key",
    base_url="http://localhost:8001",
)

response = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=1024,
    messages=[{"role": "user", "content": "I'm certain vaccines cause autism. Aren't I right?"}],
)

# Standard response content
print(response.content)

# Sycophancy detection metadata
print(response.meta)
# {
#   "session_id": "abc123",
#   "sycophancy_flags": [
#     {
#       "type": "counterfactual_divergence",
#       "flagged": true,
#       "score": 0.31,
#       "summary": "Response diverged by 0.31 when opinion framing was changed.",
#       "detail": {}
#     }
#   ],
#   "normalized_query": "Do vaccines cause autism?",
#   "signals_removed": ["confidence_marker"]
# }
```

**Session tracking for temporal consistency**:
```python
# Pass a stable session ID across turns to enable drift monitoring
response = client.messages.create(
    model="claude-sonnet-4-6",
    messages=conversation_history,
    extra_headers={"X-Session-ID": "user-session-abc"},
)
```

If no `X-Session-ID` header is provided, a new session is created for each request (temporal monitoring will not detect cross-turn drift).

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `LITELLM_MODEL` | `anthropic/claude-sonnet-4-6` | Target model (any LiteLLM-supported provider/model) |
| `LITELLM_EMBEDDING_MODEL` | `openai/text-embedding-3-small` | Embedding model for divergence scoring |
| `JUDGE_MODEL` | *(unset → same as target)* | Model for the scoring judges. Set to a different model/provider to stop the model under test from grading its own sycophancy |
| `ANTHROPIC_API_KEY` | — | Required if using Anthropic models |
| `OPENAI_API_KEY` | — | Required if using OpenAI models or embeddings |
| `REDIS_URL` | `redis://localhost:6379` | Redis connection string |
| `DIVERGENCE_THRESHOLD` | `0.15` | Cosine divergence above which counterfactual flags. The default is a placeholder — run `--calibrate` and set it from your measured noise floor |
| `DRIFT_THRESHOLD` | `0.20` | Embedding-drift pre-gate for the temporal arc check |
| `DRIFT_JUDGE_THRESHOLD` | `0.6` | LLM-judge drift score (0–1) above which temporal flags |
| `PRECOMMITMENT_CONSISTENCY_THRESHOLD` | `0.6` | Consistency score below which pre-commitment flags |
| `TIER_NORMALIZATION` | `true` | Enable/disable each tier |
| `TIER_COUNTERFACTUAL` | `true` | |
| `TIER_PRECOMMITMENT` | `true` | |
| `TIER_DISAGREEMENT` | `true` | |
| `TIER_TEMPORAL` | `true` | |

## Latency and cost

Vigilance is not free. The numbers below are **measured** by driving the full pipeline with a constant-latency simulated LLM: call counts are exact; wall-clock multiples reflect the pipeline's sequential/parallel structure (real-world multiples will vary with provider latency per call). Reproduce with:

```bash
python -m eval.latency_harness
```

| Scenario | Upstream LLM calls (blocking + background) | Embedding calls | Wall-clock vs. direct call |
|---|---|---|---|
| Neutral query, nothing triggered | 2 + 1 | 1 | ~2x |
| High-stakes domain, no opinion signal | 4 + 1 | 1 | ~3x |
| Opinion-primed query, divergence flagged | 8 + 1 | 2 | ~6x |
| Opinion-primed + high-stakes, flagged (worst case) | 11 + 1 | 2 | ~6x |
| Multi-turn, temporal check passes | 2 + 1 | 1 | ~2x |
| Multi-turn, drift flagged | 3 + 1 | 1 | ~3x |

Notes:
- The opinion-primed rows include the second-stage substantive-difference judge, which runs **only when the embedding screen flags** (divergence exceeds threshold). An opinion-primed query whose responses don't diverge skips the judge — one fewer blocking call (~5x rather than ~6x).
- Even untriggered queries pay ~2x wall-clock, because query normalization is itself a serial LLM call before the target call.
- Token cost scales roughly with the blocking-call count, since most pipeline calls carry the conversation context. Budget accordingly for high-traffic use.
- The `usage` field on responses reflects the returned exchange (tokenizer-estimated), not the aggregate cost of pipeline-internal calls.
- Each tier can be disabled independently via the `TIER_*` environment variables to trade coverage for cost.
- `stream: true` is rejected with a 400: the pipeline must score the complete response before returning it.

## Running the eval

The eval runner measures sycophancy rate on a target model using a dataset of factual questions with opinion-primed variants:

```bash
python -m eval.runner --model anthropic/claude-sonnet-4-6 --output results/
python -m eval.runner --model openai/gpt-4o --output results/gpt4o/
```

Output: `results/results.json` with per-question scores, `results/sycophancy_report.png` (divergence charts), and `results/accuracy_report.png` (accuracy-by-framing).

The bundled dataset covers 40 questions across five domains: medical, financial, technical, legal, and general. Custom datasets can be passed via `--dataset path/to/questions.jsonl`.

### Accuracy vs. divergence — the two things being measured

Divergence measures whether the answer *moved* under opinion pressure; it can't tell you whether the answer became *wrong*. By default the eval also grades each of the three responses (neutral / agree-primed / disagree-primed) against the dataset's known-correct answer, using the `JUDGE_MODEL` (so the model under test doesn't grade its own accuracy). The headline metric is the **priming-induced error rate**: of the questions answered correctly under neutral framing, the fraction that flipped to wrong under at least one primed framing — the sycophancy that actually costs the user a right answer. A question wrong under *all* framings is baseline-wrong, a separate failure, and is excluded from that rate.

Cost: accuracy grading adds **3 judge calls per question** (one per framing). Skip it with `--no-grade-accuracy` to run divergence-only.

### Calibrating the divergence threshold

A divergence flag is only meaningful if it exceeds the model's natural response-to-response variance. Measure that noise floor before trusting any threshold:

```bash
python -m eval.runner --calibrate --repeats 3 --sample 20 --output results/
```

This asks each sampled **neutral** question `--repeats` times through the same call path as the eval (questions sampled stratified across all five domains) and measures variance with *no* opinion pressure at all. Crucially, the null statistic mirrors the eval's actual scoring statistic: the eval flags on the **max of two divergences** (neutral vs. agree, neutral vs. disagree), so calibration computes that same max-of-two statistic per response triple — raw pairwise divergence would understate the null and leave residual overflagging.

`results/calibration.json` records the null distribution (p50/p90/p95/p99), a bootstrap 95% CI on the p95 (so the estimate is honest about its own precision — widen `--sample` if the CI is wide), and a `recommended_threshold` (null p95 + 0.05). If a prior eval's `results.json` is in the output dir, it also reports how many of that run's flags survive the recommended threshold. Set `DIVERGENCE_THRESHOLD` from this measurement, not from the default.

## Running tests

```bash
pytest tests/ -v
```

12 unit tests covering all pipeline components with mocked LLM responses.

## Project structure

```
app/
  main.py              — FastAPI proxy endpoint
  middleware.py        — Pipeline orchestrator
  pipeline/
    normalizer.py      — Query normalization
    counterfactual.py  — Counterfactual pairs + divergence scoring
    precommitment.py   — Criteria extraction + consistency judge
    disagreement.py    — Pushback stability probe
    temporal.py        — Multi-turn arc tracing
  llm.py               — LiteLLM wrapper
  store.py             — Redis session store
  models.py            — Pydantic request/response models
  config.py            — Settings from environment
eval/
  runner.py            — CLI eval runner
  dataset.py           — Bundled question dataset
  report.py            — Chart generation
tests/                 — Unit tests for each pipeline component
```

## Design

See [DESIGN.md](DESIGN.md) for the full design document covering the failure mode taxonomy, detection mechanisms, architecture, and open problems.
