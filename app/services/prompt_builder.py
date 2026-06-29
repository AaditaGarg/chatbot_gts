"""Dynamic prompt builder for hybrid assistant responses."""

from typing import Optional

from config.settings import SYSTEM_PROMPT
from models.schemas import Intent, IntentResult, RetrievedChunk, WebSearchResult


class PromptBuilder:
    """Build LLM message lists based on intent, context, and available sources."""

    def build_messages(
        self,
        question: str,
        history: list[dict],
        intent_result: IntentResult,
        context_chunks: Optional[list[RetrievedChunk]] = None,
        web_results: Optional[list[WebSearchResult]] = None,
        tool_output: Optional[str] = None,
        long_term_context: str = "",
    ) -> list[dict]:
        """Return OpenAI-style messages for the LLM."""
        messages: list[dict] = [{"role": "system", "content": self._build_system_content(intent_result)}]

        if long_term_context:
            messages.append(
                {
                    "role": "system",
                    "content": f"Known facts about this user (use naturally, do not recite verbatim):\n{long_term_context}",
                }
            )

        for msg in history:
            messages.append({"role": msg["role"], "content": msg["content"]})

        user_content = self._build_user_content(
            question=question,
            intent_result=intent_result,
            context_chunks=context_chunks or [],
            web_results=web_results or [],
            tool_output=tool_output,
        )
        messages.append({"role": "user", "content": user_content})
        return messages

    def _build_system_content(self, intent_result: IntentResult) -> str:
        extras: list[str] = []

        if intent_result.intent == Intent.GREETING:
            extras.append("The user is greeting you. Respond warmly and briefly.")
        elif intent_result.intent == Intent.SMALL_TALK:
            extras.append("Keep it light and friendly.")
        elif intent_result.intent == Intent.CODING:
            extras.append("Provide clean, well-commented code with brief explanations.")
        elif intent_result.intent == Intent.CREATIVE_WRITING:
            extras.append("Be creative and engaging.")
        elif intent_result.intent == Intent.FOLLOW_UP:
            extras.append("This is a follow-up — refer to the conversation history naturally.")
        elif intent_result.intent == Intent.DOCUMENT_QUESTION:
            extras.append(
                "Answer using ONLY the provided document context. "
                "If the context does not contain the answer, say so honestly."
            )

        if extras:
            return SYSTEM_PROMPT + "\n\n" + "\n".join(extras)
        return SYSTEM_PROMPT

    def _build_user_content(
        self,
        question: str,
        intent_result: IntentResult,
        context_chunks: list[RetrievedChunk],
        web_results: list[WebSearchResult],
        tool_output: Optional[str],
    ) -> str:
        parts: list[str] = []

        if context_chunks:
            ranked = sorted(context_chunks, key=lambda c: c.score, reverse=True)
            context_text = "\n\n---\n\n".join(
                f"[Source {i + 1} (relevance: {c.score:.2f})]\n{c.content}"
                for i, c in enumerate(ranked)
            )
            parts.append(f"Relevant document context:\n{context_text}")

        if web_results:
            web_text = "\n".join(
                f"- {r.title}: {r.snippet}" + (f" ({r.url})" if r.url else "")
                for r in web_results
            )
            parts.append(f"Recent web search results:\n{web_text}")

        if tool_output:
            parts.append(f"Tool computation result:\n{tool_output}")

        parts.append(f"User message: {question}")

        if intent_result.intent == Intent.DOCUMENT_QUESTION and not context_chunks:
            parts.append(
                "Note: No relevant documents were found. Let the user know and offer to help another way."
            )

        return "\n\n".join(parts)
