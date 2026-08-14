from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, model_validator


Provider = Literal["openai", "anthropic", "google", "openai-compatible"]
ThinkingLevel = Literal["off", "minimal", "low", "medium", "high"]


class AgentModelConfigRead(BaseModel):
    provider: Provider
    model: str
    base_url: str | None
    thinking_level: ThinkingLevel
    enabled: bool
    api_key_configured: bool


class AgentModelConfigUpdate(BaseModel):
    provider: Provider
    model: str = Field(min_length=1, max_length=160)
    base_url: HttpUrl | None = None
    api_key: str | None = Field(default=None, max_length=8192)
    thinking_level: ThinkingLevel = "medium"
    enabled: bool = True

    @model_validator(mode="after")
    def validate_provider(self) -> "AgentModelConfigUpdate":
        if self.provider == "openai-compatible" and self.base_url is None:
            raise ValueError("OpenAI-compatible 提供商必须配置 API 地址")
        return self


class AgentModelConfigInternal(BaseModel):
    provider: Provider
    model: str
    base_url: str | None
    api_key: str
    thinking_level: ThinkingLevel
    enabled: bool
