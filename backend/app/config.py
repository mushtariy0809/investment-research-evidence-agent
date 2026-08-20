"""Application configuration.

Every tunable value comes from environment variables (or a local .env file),
loaded once into a typed Settings object. Nothing else in the codebase reads
os.environ directly, so there is exactly one place to see what the app needs.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LLM provider: "mock" (deterministic, no API key) or "anthropic"
    llm_provider: str = "mock"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5"

    # SEC fair-access policy requires a User-Agent identifying the app + contact.
    sec_user_agent_name: str = "InvestmentResearchEvidenceAgent"
    sec_contact_email: str = "you@example.com"

    database_url: str = "sqlite:///./data/app.db"

    log_level: str = "INFO"
    cors_origins: str = "http://localhost:5173"

    @property
    def sec_user_agent(self) -> str:
        return f"{self.sec_user_agent_name} {self.sec_contact_email}"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
