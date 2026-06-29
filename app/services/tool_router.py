"""Tool router for calculator and future tool integrations."""

import ast
import logging
import math
import operator
import re
from typing import Callable, Optional

logger = logging.getLogger(__name__)

SAFE_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


class ToolRouter:
    """Route requests to appropriate tools when needed."""

    def __init__(self):
        self._tools: dict[str, Callable[[str], Optional[str]]] = {
            "calculator": self._calculator,
        }

    def route(self, question: str, intent_needs_tools: bool = False) -> Optional[str]:
        if not intent_needs_tools and not self._looks_like_calculation(question):
            return None

        if self._looks_like_calculation(question):
            return self._calculator(question)

        for name, handler in self._tools.items():
            if name in question.lower():
                return handler(question)

        return None

    def _looks_like_calculation(self, question: str) -> bool:
        if re.search(r"[\d]+\s*[\+\-\*/\^]\s*[\d]+", question):
            return True
        calc_words = ("calculate", "compute", "what is", "evaluate", "solve")
        lower = question.lower()
        return any(w in lower for w in calc_words) and re.search(r"\d", question)

    def _calculator(self, question: str) -> Optional[str]:
        expr_match = re.search(r"([\d\s\+\-\*/\(\)\.\^]+)", question)
        if not expr_match:
            return None
        expr = expr_match.group(1).replace("^", "**").strip()
        try:
            result = self._safe_eval(expr)
            return f"{expr} = {result}"
        except Exception as exc:
            logger.debug("Calculator failed: %s", exc)
            return None

    def _safe_eval(self, expression: str) -> float:
        node = ast.parse(expression, mode="eval")

        def _eval(n):
            if isinstance(n, ast.Expression):
                return _eval(n.body)
            if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
                return n.value
            if isinstance(n, ast.BinOp):
                op = SAFE_OPERATORS.get(type(n.op))
                if op is None:
                    raise ValueError("Unsupported operator")
                return op(_eval(n.left), _eval(n.right))
            if isinstance(n, ast.UnaryOp):
                op = SAFE_OPERATORS.get(type(n.op))
                if op is None:
                    raise ValueError("Unsupported operator")
                return op(_eval(n.operand))
            raise ValueError("Unsupported expression")

        return _eval(node)
