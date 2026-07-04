from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    litellm_model: str = "anthropic/claude-sonnet-4-6"
    litellm_embedding_model: str = "openai/text-embedding-3-small"

    anthropic_api_key: str = ""
    openai_api_key: str = ""

    redis_url: str = "redis://localhost:6379"

    divergence_threshold: float = 0.15
    drift_threshold: float = 0.20
    precommitment_consistency_threshold: float = 0.6

    tier_normalization: bool = True
    tier_counterfactual: bool = True
    tier_precommitment: bool = True
    tier_disagreement: bool = True
    tier_temporal: bool = True


settings = Settings()
