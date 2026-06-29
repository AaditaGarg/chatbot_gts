"""Backward-compatible memory re-exports."""

from services.memory_service import LongTermMemory, ShortTermMemory

__all__ = ["LongTermMemory", "ShortTermMemory"]
