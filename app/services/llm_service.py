"""LLM abstraction layer supporting Ollama and future providers."""

import logging
from abc import ABC, abstractmethod
from typing import AsyncIterator, Iterator, Optional

import ollama

from config.settings import (
    LLM_MAX_HISTORY_MESSAGES,
    LLM_PROVIDER,
    LLM_TIMEOUT_SECONDS,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
)

logger = logging.getLogger(__name__)


class BaseLLMProvider(ABC):
    @abstractmethod
    def generate(self, messages: list[dict]) -> str:
        pass

    @abstractmethod
    def stream(self, messages: list[dict]) -> Iterator[str]:
        pass


class OllamaProvider(BaseLLMProvider):
    def __init__(self, model: str = OLLAMA_MODEL, base_url: str = OLLAMA_BASE_URL):
        self.model = model
        self.client = ollama.Client(host=base_url)

    def generate(self, messages: list[dict]) -> str:
        trimmed = self._trim_messages(messages)
        response = self.client.chat(model=self.model, messages=trimmed)
        return response["message"]["content"]

    def stream(self, messages: list[dict]) -> Iterator[str]:
        trimmed = self._trim_messages(messages)
        stream = self.client.chat(model=self.model, messages=trimmed, stream=True)
        for chunk in stream:
            content = chunk.get("message", {}).get("content", "")
            if content:
                yield content

    def _trim_messages(self, messages: list[dict]) -> list[dict]:
        system = [m for m in messages if m["role"] == "system"]
        non_system = [m for m in messages if m["role"] != "system"]
        trimmed_non_system = non_system[-LLM_MAX_HISTORY_MESSAGES:]
        return system + trimmed_non_system


class OpenAIProvider(BaseLLMProvider):
    """Placeholder for future OpenAI integration."""

    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model

    def generate(self, messages: list[dict]) -> str:
        raise NotImplementedError("OpenAI provider not yet configured. Set LLM_PROVIDER=ollama.")

    def stream(self, messages: list[dict]) -> Iterator[str]:
        raise NotImplementedError("OpenAI provider not yet configured. Set LLM_PROVIDER=ollama.")


class LLMService:
    """Centralized LLM service with provider switching via configuration."""

    def __init__(self):
        self._provider: Optional[BaseLLMProvider] = None

    def init(self) -> bool:
        try:
            if LLM_PROVIDER == "ollama":
                self._provider = OllamaProvider()
            elif LLM_PROVIDER == "openai":
                from config.settings import OPENAI_API_KEY, OPENAI_MODEL
                self._provider = OpenAIProvider(api_key=OPENAI_API_KEY, model=OPENAI_MODEL)
            else:
                logger.warning("Unknown LLM provider '%s', falling back to Ollama.", LLM_PROVIDER)
                self._provider = OllamaProvider()
            return True
        except Exception as exc:
            logger.error("LLM service init failed: %s", exc)
            return False

    @property
    def is_ready(self) -> bool:
        return self._provider is not None

    @property
    def model_name(self) -> str:
        if isinstance(self._provider, OllamaProvider):
            return self._provider.model
        return LLM_PROVIDER

    def generate(self, messages: list[dict]) -> str:
        if not self._provider:
            raise RuntimeError("LLM service not initialized.")
        return self._provider.generate(messages)

    def stream(self, messages: list[dict]) -> Iterator[str]:
        if not self._provider:
            raise RuntimeError("LLM service not initialized.")
        yield from self._provider.stream(messages)

    async def stream_async(self, messages: list[dict]) -> AsyncIterator[str]:
        """Async wrapper for streaming (runs sync stream in thread pool if needed)."""
        for token in self.stream(messages):
            yield token
