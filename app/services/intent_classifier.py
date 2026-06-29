"""Intent classification for hybrid routing."""

import re
from typing import Optional

from models.schemas import Intent, IntentResult

GREETING_PATTERNS = re.compile(
    r"^(hi|hello|hey|good\s+(morning|afternoon|evening|night)|howdy|greetings|what'?s\s+up|sup)[\s!.?]*$",
    re.IGNORECASE,
)

SMALL_TALK_PATTERNS = re.compile(
    r"\b(joke|fun fact|how are you|how'?s it going|thank you|thanks|bye|goodbye|see you)\b",
    re.IGNORECASE,
)

DOCUMENT_PATTERNS = re.compile(
    r"\b("
    r"my (pdf|document|file|upload|resume|policy|contract|report|csv|docx)|"
    r"uploaded|in the document|from the file|knowledge base|company policy|hr policy|"
    r"summarize (this|my|the)|compare (these|my|the)|what does (page|section)|"
    r"inside my|what is in my|according to (the|my|our)"
    r")\b",
    re.IGNORECASE,
)

WEB_SEARCH_PATTERNS = re.compile(
    r"\b("
    r"latest|today|current|recent|now|this week|this month|202[4-9]|"
    r"weather|stock market|news|headlines|who won|score|live|"
    r"current affairs|breaking|trending"
    r")\b",
    re.IGNORECASE,
)

CODING_PATTERNS = re.compile(
    r"\b("
    r"code|program|function|class|algorithm|debug|implement|refactor|"
    r"python|javascript|typescript|java|c\+\+|rust|sql|api|fastapi|react|"
    r"binary search|data structure|regex|compile"
    r")\b",
    re.IGNORECASE,
)

MATH_PATTERNS = re.compile(
    r"\b(calculate|compute|solve|equation|integral|derivative|math|algebra|geometry)\b|"
    r"[\d]+\s*[\+\-\*/\^]\s*[\d]+",
    re.IGNORECASE,
)

CREATIVE_PATTERNS = re.compile(
    r"\b(write|poem|story|essay|creative|brainstorm|draft|compose|song|script)\b",
    re.IGNORECASE,
)

TOOL_PATTERNS = re.compile(
    r"\b(calculator|convert|currency|unit|schedule|calendar|email|sql query)\b",
    re.IGNORECASE,
)

FOLLOW_UP_PATTERNS = re.compile(
    r"^(yes|no|ok|okay|sure|continue|go on|tell me more|explain (more|further|that)|"
    r"give me (an? )?(easier|another|more) example|what about|and also|can you elaborate|"
    r"why|how so|what do you mean|clarify|simpler|shorter|in simpler terms)",
    re.IGNORECASE,
)


class IntentClassifier:
    """Rule-based intent classifier with conversation context awareness."""

    def classify(
        self,
        question: str,
        history: Optional[list[dict]] = None,
    ) -> IntentResult:
        text = question.strip()
        lower = text.lower()
        history = history or []

        if GREETING_PATTERNS.match(lower):
            return IntentResult(
                intent=Intent.GREETING,
                reasoning="Matched greeting pattern",
            )

        if SMALL_TALK_PATTERNS.search(lower) and len(text.split()) < 12:
            return IntentResult(
                intent=Intent.SMALL_TALK,
                reasoning="Matched small talk pattern",
            )

        if DOCUMENT_PATTERNS.search(lower):
            return IntentResult(
                intent=Intent.DOCUMENT_QUESTION,
                needs_documents=True,
                reasoning="User references uploaded or stored documents",
            )

        if WEB_SEARCH_PATTERNS.search(lower):
            return IntentResult(
                intent=Intent.CURRENT_EVENTS,
                needs_web_search=True,
                reasoning="Question requires current or live information",
            )

        if TOOL_PATTERNS.search(lower):
            return IntentResult(
                intent=Intent.TOOL_REQUEST,
                needs_tools=True,
                reasoning="User may need a tool",
            )

        if MATH_PATTERNS.search(lower):
            return IntentResult(
                intent=Intent.MATHEMATICS,
                needs_tools=True,
                reasoning="Mathematical computation detected",
            )

        if CODING_PATTERNS.search(lower):
            return IntentResult(
                intent=Intent.CODING,
                reasoning="Coding-related question",
            )

        if CREATIVE_PATTERNS.search(lower):
            return IntentResult(
                intent=Intent.CREATIVE_WRITING,
                reasoning="Creative writing request",
            )

        if FOLLOW_UP_PATTERNS.match(lower) and history:
            return IntentResult(
                intent=Intent.FOLLOW_UP,
                needs_documents=self._last_turn_used_documents(history),
                reasoning="Follow-up to previous conversation turn",
            )

        if self._is_general_knowledge(lower):
            return IntentResult(
                intent=Intent.GENERAL_KNOWLEDGE,
                reasoning="General knowledge question",
            )

        if len(history) >= 2:
            return IntentResult(
                intent=Intent.FOLLOW_UP,
                reasoning="Continuing conversation",
            )

        return IntentResult(
            intent=Intent.GENERAL_CONVERSATION,
            reasoning="Default general conversation",
        )

    def _last_turn_used_documents(self, history: list[dict]) -> bool:
        for msg in reversed(history):
            if msg.get("role") == "assistant" and msg.get("sources"):
                return True
        return False

    def _is_general_knowledge(self, lower: str) -> bool:
        starters = ("who is", "what is", "what are", "where is", "when did", "why does", "how does")
        return any(lower.startswith(s) for s in starters)
