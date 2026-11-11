"""AI adviser request and response contracts."""

from typing import Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    language: Literal["en", "bn"] = "en"


class ChatResponse(BaseModel):
    answer: str
    language: Literal["en", "bn"]


class WeeklySummaryResponse(BaseModel):
    summary: str
    language: Literal["en", "bn"]
    readings_count: int


class AIStatus(BaseModel):
    configured: bool
    model: str
    provider: Literal["groq", "gemini"] | None = None
