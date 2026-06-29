"""Central chat orchestration for the hybrid AI assistant."""

import logging
import uuid
from dataclasses import dataclass, field
from typing import Iterator, Optional

from sqlalchemy.orm import Session

from models.schemas import ChatResponse, Intent, IntentResult, RetrievedChunk
from services.intent_classifier import IntentClassifier
from services.llm_service import LLMService
from services.memory_service import MemoryService
from services.prompt_builder import PromptBuilder
from services.rag_service import RAGService
from services.tool_router import ToolRouter
from services.web_search_service import WebSearchService

logger = logging.getLogger(__name__)


@dataclass
class ChatPipelineResult:
    answer: str = ""
    sources: list[str] = field(default_factory=list)
    intent: Optional[str] = None
    messages: list[dict] = field(default_factory=list)


class ChatService:
    """Orchestrate intent detection, routing, RAG, tools, and LLM generation."""

    def __init__(
        self,
        llm: LLMService,
        rag: RAGService,
        memory: MemoryService,
        intent_classifier: Optional[IntentClassifier] = None,
        prompt_builder: Optional[PromptBuilder] = None,
        web_search: Optional[WebSearchService] = None,
        tool_router: Optional[ToolRouter] = None,
    ):
        self.llm = llm
        self.rag = rag
        self.memory = memory
        self.intent_classifier = intent_classifier or IntentClassifier()
        self.prompt_builder = prompt_builder or PromptBuilder()
        self.web_search = web_search or WebSearchService()
        self.tool_router = tool_router or ToolRouter()

    def process_message(
        self,
        db: Session,
        user_id: str,
        session_id: str,
        question: str,
    ) -> ChatResponse:
        pipeline = self._prepare_pipeline(db, user_id, session_id, question)
        answer = self.llm.generate(pipeline.messages)
        return self._finalize(db, user_id, session_id, question, answer, pipeline)

    def stream_message(
        self,
        db: Session,
        user_id: str,
        session_id: str,
        question: str,
    ) -> tuple[Iterator[str], ChatPipelineResult]:
        pipeline = self._prepare_pipeline(db, user_id, session_id, question)

        def token_generator() -> Iterator[str]:
            tokens: list[str] = []
            for token in self.llm.stream(pipeline.messages):
                tokens.append(token)
                yield token
            pipeline.answer = "".join(tokens)

        return token_generator(), pipeline

    def finalize_stream(
        self,
        db: Session,
        user_id: str,
        session_id: str,
        question: str,
        pipeline: ChatPipelineResult,
    ) -> ChatResponse:
        return self._finalize(db, user_id, session_id, question, pipeline.answer, pipeline)

    def _prepare_pipeline(
        self,
        db: Session,
        user_id: str,
        session_id: str,
        question: str,
    ) -> ChatPipelineResult:
        user_uuid = uuid.UUID(user_id)
        session_uuid = uuid.UUID(session_id)

        conversation = self.memory.long_term.get_conversation(db, user_uuid, session_uuid)
        if not conversation:
            raise ValueError("Session not found for this user.")

        history = self.memory.load_history(db, user_id, session_id, user_uuid, session_uuid)
        intent_result = self.intent_classifier.classify(question, history)

        context_chunks = self._retrieve_context(question, intent_result, user_id, session_id)
        web_results = self._search_web(question, intent_result)
        tool_output = self.tool_router.route(question, intent_result.needs_tools)

        long_term_context = self.memory.long_term.build_long_term_context(db, user_uuid)
        messages = self.prompt_builder.build_messages(
            question=question,
            history=[{"role": m["role"], "content": m["content"]} for m in history],
            intent_result=intent_result,
            context_chunks=context_chunks,
            web_results=web_results,
            tool_output=tool_output,
            long_term_context=long_term_context,
        )

        sources = self._format_sources(context_chunks)
        return ChatPipelineResult(
            sources=sources,
            intent=intent_result.intent.value,
            messages=messages,
        )

    def _retrieve_context(
        self,
        question: str,
        intent_result: IntentResult,
        user_id: str,
        session_id: str,
    ) -> list[RetrievedChunk]:
        skip_intents = {
            Intent.GREETING,
            Intent.SMALL_TALK,
            Intent.CODING,
            Intent.CREATIVE_WRITING,
            Intent.MATHEMATICS,
            Intent.CURRENT_EVENTS,
        }
        if intent_result.intent in skip_intents and not intent_result.needs_documents:
            return []

        chunks = self.rag.search(question, user_id=user_id, session_id=session_id)
        if chunks:
            intent_result.needs_documents = True
        return chunks

    def _search_web(self, question: str, intent_result: IntentResult):
        if not intent_result.needs_web_search and not self.web_search.should_search(question):
            return []
        if intent_result.intent in (Intent.GREETING, Intent.SMALL_TALK, Intent.CODING):
            return []
        results = self.web_search.search(question)
        if results:
            intent_result.needs_web_search = True
        return results

    def _format_sources(self, chunks: list[RetrievedChunk]) -> list[str]:
        sources = []
        for chunk in chunks[:5]:
            preview = chunk.content[:120] + "..." if len(chunk.content) > 120 else chunk.content
            sources.append(preview)
        return sources

    def _finalize(
        self,
        db: Session,
        user_id: str,
        session_id: str,
        question: str,
        answer: str,
        pipeline: ChatPipelineResult,
    ) -> ChatResponse:
        user_uuid = uuid.UUID(user_id)
        session_uuid = uuid.UUID(session_id)
        history = self.memory.load_history(db, user_id, session_id, user_uuid, session_uuid)

        self.memory.save_turn(
            db=db,
            user_id=user_id,
            session_id=session_id,
            user_uuid=user_uuid,
            session_uuid=session_uuid,
            question=question,
            answer=answer,
            sources=pipeline.sources,
            history=[{"role": m["role"], "content": m["content"]} for m in history],
        )

        return ChatResponse(
            answer=answer,
            sources=pipeline.sources,
            session_id=session_id,
            user_id=user_id,
            intent=pipeline.intent,
        )
