"""Pydantic schemas for API requests and internal service types."""

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class Intent(str, Enum):
    GREETING = "greeting"
    SMALL_TALK = "small_talk"
    GENERAL_CONVERSATION = "general_conversation"
    CODING = "coding"
    MATHEMATICS = "mathematics"
    GENERAL_KNOWLEDGE = "general_knowledge"
    CREATIVE_WRITING = "creative_writing"
    DOCUMENT_QUESTION = "document_question"
    FOLLOW_UP = "follow_up"
    PERSONAL_ASSISTANT = "personal_assistant"
    CURRENT_EVENTS = "current_events"
    TOOL_REQUEST = "tool_request"


class IntentResult(BaseModel):
    intent: Intent
    needs_documents: bool = False
    needs_web_search: bool = False
    needs_tools: bool = False
    confidence: float = 1.0
    reasoning: str = ""


class RetrievedChunk(BaseModel):
    content: str
    score: float
    document_id: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class WebSearchResult(BaseModel):
    title: str
    snippet: str
    url: str = ""


class ChatMessage(BaseModel):
    role: str
    content: str


# --- API schemas ---

class UserCreateRequest(BaseModel):
    display_name: str = Field(default="Guest", max_length=120)


class UserResponse(BaseModel):
    user_id: str
    display_name: str


class SessionCreateRequest(BaseModel):
    user_id: str
    title: str = "New Conversation"


class SessionResponse(BaseModel):
    session_id: str
    user_id: str
    title: str


class ChatRequest(BaseModel):
    user_id: str
    session_id: str
    question: str = Field(min_length=1, max_length=4000)


class ChatResponse(BaseModel):
    answer: str
    sources: list[str] = []
    session_id: str
    user_id: str
    intent: Optional[str] = None


class HistoryMessage(BaseModel):
    role: str
    content: str
    sources: list[str] = []
    created_at: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    redis: bool
    postgres: bool
    chromadb: bool
    ollama_model: str
    llm_provider: str = "ollama"


class DocumentUploadResponse(BaseModel):
    document_id: str
    filename: str
    chunk_count: int
    message: str
