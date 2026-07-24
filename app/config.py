from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    litellm_model: str = "anthropic/claude-sonnet-4-6"
    litellm_embedding_model: str = "openai/text-embedding-3-small"
    # Model that runs the scoring judges. None = same as the target model
    # (behavior unchanged until set); set to a different model/provider to
    # break the self-judging circularity where the model grades itself.
    judge_model: str | None = None

    anthropic_api_key: str = ""
    openai_api_key: str = ""

    redis_url: str = "redis://localhost:6379"

    # Ceiling on upstream LLM completion calls per inbound request — one request
    # can fan out to ~11 (see eval/latency_harness.py); this caps cost/load
    # amplification from a malicious or buggy client. 0 disables the cap.
    max_llm_calls_per_request: int = 20

    # What to do when the counterfactual tier flags an answer as sycophantic.
    # observe (default): return the model's actual answer to the user's query and
    # disclose the detection via meta.sycophancy_flags — the human stays in the
    # executive seat. enforce: substitute the neutral-variant answer (opinionated
    # correction). See DESIGN.md "response to detected sycophancy". Env: GLOSS_MODE.
    gloss_mode: Literal["observe", "enforce"] = "observe"

    divergence_threshold: float = 0.15
    drift_threshold: float = 0.20        # embedding-distance pre-gate (0-2 cosine scale)
    drift_judge_threshold: float = 0.6   # LLM judge's subjective 0-1 drift score
    precommitment_consistency_threshold: float = 0.6

    tier_normalization: bool = True
    tier_assumption: bool = True
    tier_counterfactual: bool = True
    tier_precommitment: bool = True
    tier_disagreement: bool = True
    tier_temporal: bool = True

    @property
    def effective_judge_model(self) -> str:
        """The model to use for scoring judges — the dedicated judge model if
        configured, else the target model."""
        return self.judge_model or self.litellm_model


settings = Settings()
