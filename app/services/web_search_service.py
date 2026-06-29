"""Web search service with pluggable providers."""

import logging
from typing import Optional
from urllib.parse import quote_plus

import requests

from config.settings import WEB_SEARCH_API_KEY, WEB_SEARCH_MAX_RESULTS, WEB_SEARCH_PROVIDER
from models.schemas import WebSearchResult

logger = logging.getLogger(__name__)


class WebSearchService:
    """Search the web when questions need current information."""

    def __init__(self):
        self.provider = WEB_SEARCH_PROVIDER
        self.api_key = WEB_SEARCH_API_KEY

    def should_search(self, question: str) -> bool:
        """Quick check if web search might be useful."""
        lower = question.lower()
        triggers = (
            "latest", "today", "current", "recent", "news", "weather",
            "stock", "score", "who won", "2025", "2026", "now",
        )
        return any(t in lower for t in triggers)

    def search(self, query: str) -> list[WebSearchResult]:
        if self.provider == "tavily" and self.api_key:
            return self._search_tavily(query)
        return self._search_duckduckgo(query)

    def _search_tavily(self, query: str) -> list[WebSearchResult]:
        try:
            response = requests.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": self.api_key,
                    "query": query,
                    "max_results": WEB_SEARCH_MAX_RESULTS,
                },
                timeout=15,
            )
            response.raise_for_status()
            data = response.json()
            return [
                WebSearchResult(
                    title=r.get("title", ""),
                    snippet=r.get("content", r.get("snippet", "")),
                    url=r.get("url", ""),
                )
                for r in data.get("results", [])
            ]
        except Exception as exc:
            logger.warning("Tavily search failed: %s", exc)
            return self._search_duckduckgo(query)

    def _search_duckduckgo(self, query: str) -> list[WebSearchResult]:
        try:
            from duckduckgo_search import DDGS

            results: list[WebSearchResult] = []
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=WEB_SEARCH_MAX_RESULTS):
                    results.append(
                        WebSearchResult(
                            title=r.get("title", ""),
                            snippet=r.get("body", r.get("snippet", "")),
                            url=r.get("href", r.get("link", "")),
                        )
                    )
            return results
        except ImportError:
            logger.info("duckduckgo-search not installed; using HTML fallback.")
            return self._search_duckduckgo_html(query)
        except Exception as exc:
            logger.warning("DuckDuckGo search failed: %s", exc)
            return []

    def _search_duckduckgo_html(self, query: str) -> list[WebSearchResult]:
        """Minimal fallback when duckduckgo-search package is unavailable."""
        try:
            url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
            response = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            response.raise_for_status()
            from html.parser import HTMLParser

            class ResultParser(HTMLParser):
                def __init__(self):
                    super().__init__()
                    self.results: list[WebSearchResult] = []
                    self._in_result = False
                    self._in_snippet = False
                    self._title = ""
                    self._snippet = ""

                def handle_starttag(self, tag, attrs):
                    attrs_dict = dict(attrs)
                    cls = attrs_dict.get("class", "")
                    if tag == "a" and "result__a" in cls:
                        self._in_result = True
                        self._title = ""
                    if tag == "a" and "result__snippet" in cls:
                        self._in_snippet = True
                        self._snippet = ""

                def handle_endtag(self, tag):
                    if self._in_result and tag == "a":
                        self._in_result = False
                    if self._in_snippet and tag == "a":
                        self._in_snippet = False
                        if self._title:
                            self.results.append(
                                WebSearchResult(title=self._title.strip(), snippet=self._snippet.strip())
                            )

                def handle_data(self, data):
                    if self._in_result:
                        self._title += data
                    if self._in_snippet:
                        self._snippet += data

            parser = ResultParser()
            parser.feed(response.text)
            return parser.results[:WEB_SEARCH_MAX_RESULTS]
        except Exception as exc:
            logger.warning("HTML fallback search failed: %s", exc)
            return []
