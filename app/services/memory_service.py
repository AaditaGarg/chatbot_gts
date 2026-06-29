"""Memory service wrapping Redis session memory and PostgreSQL persistence."""

import json
import logging
import uuid
from typing import Optional

from sqlalchemy.orm import Session

from config.settings import REDIS_KEY_PREFIX, REDIS_MAX_MESSAGES, REDIS_TTL_SECONDS
from database.postgres import Conversation, Message, User, UserMemory, utcnow

logger = logging.getLogger(__name__)


class ShortTermMemory:
    """Redis-backed session memory for active conversations."""

    def __init__(self, redis_client):
        self.redis = redis_client

    def _history_key(self, user_id: str, session_id: str) -> str:
        return f"{REDIS_KEY_PREFIX}:user:{user_id}:session:{session_id}:history"

    def get_history(self, user_id: str, session_id: str) -> list[dict]:
        raw = self.redis.get(self._history_key(user_id, session_id))
        if not raw:
            return []
        return json.loads(raw)

    def save_history(self, user_id: str, session_id: str, history: list[dict]) -> None:
        trimmed = history[-REDIS_MAX_MESSAGES:]
        key = self._history_key(user_id, session_id)
        self.redis.setex(key, REDIS_TTL_SECONDS, json.dumps(trimmed))

    def clear_history(self, user_id: str, session_id: str) -> None:
        self.redis.delete(self._history_key(user_id, session_id))

    def set_active_session(self, user_id: str, session_id: str) -> None:
        key = f"{REDIS_KEY_PREFIX}:user:{user_id}:active_session"
        self.redis.setex(key, REDIS_TTL_SECONDS, session_id)


class LongTermMemory:
    """PostgreSQL-backed persistence for users, conversations, and documents."""

    def create_user(self, db: Session, display_name: str = "Guest") -> User:
        user = User(display_name=display_name)
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    def get_user(self, db: Session, user_id: uuid.UUID) -> Optional[User]:
        return db.get(User, user_id)

    def create_conversation(self, db: Session, user_id: uuid.UUID, title: str = "New Conversation") -> Conversation:
        conversation = Conversation(user_id=user_id, title=title)
        db.add(conversation)
        db.commit()
        db.refresh(conversation)
        return conversation

    def get_conversation(self, db: Session, user_id: uuid.UUID, session_id: uuid.UUID) -> Optional[Conversation]:
        from sqlalchemy import select

        stmt = select(Conversation).where(
            Conversation.conversation_id == session_id,
            Conversation.user_id == user_id,
        )
        return db.execute(stmt).scalar_one_or_none()

    def list_conversations(self, db: Session, user_id: uuid.UUID) -> list[Conversation]:
        from sqlalchemy import select

        stmt = (
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .order_by(Conversation.updated_at.desc())
        )
        return list(db.execute(stmt).scalars().all())

    def save_message(
        self,
        db: Session,
        user_id: uuid.UUID,
        session_id: uuid.UUID,
        role: str,
        content: str,
        sources: Optional[list[str]] = None,
    ) -> Message:
        conversation = self.get_conversation(db, user_id, session_id)
        if not conversation:
            raise ValueError("Conversation not found for this user.")

        conversation.version += 1
        conversation.updated_at = utcnow()
        if role == "user" and conversation.title == "New Conversation":
            conversation.title = content[:80] + ("..." if len(content) > 80 else "")

        message = Message(
            conversation_id=session_id,
            user_id=user_id,
            role=role,
            content=content,
            sources=json.dumps(sources) if sources else None,
        )
        db.add(message)
        db.commit()
        db.refresh(message)
        return message

    def get_messages(self, db: Session, user_id: uuid.UUID, session_id: uuid.UUID) -> list[Message]:
        from sqlalchemy import select

        conversation = self.get_conversation(db, user_id, session_id)
        if not conversation:
            return []
        stmt = (
            select(Message)
            .where(Message.conversation_id == session_id, Message.user_id == user_id)
            .order_by(Message.created_at.asc())
        )
        return list(db.execute(stmt).scalars().all())

    def clear_conversation(self, db: Session, user_id: uuid.UUID, session_id: uuid.UUID) -> bool:
        conversation = self.get_conversation(db, user_id, session_id)
        if not conversation:
            return False
        for message in list(conversation.messages):
            db.delete(message)
        conversation.version += 1
        conversation.updated_at = utcnow()
        db.commit()
        return True

    def upsert_user_memory(
        self,
        db: Session,
        user_id: uuid.UUID,
        memory_key: str,
        memory_value: str,
        expected_version: Optional[int] = None,
    ) -> UserMemory:
        from sqlalchemy import select

        stmt = select(UserMemory).where(
            UserMemory.user_id == user_id,
            UserMemory.memory_key == memory_key,
        )
        memory = db.execute(stmt).scalar_one_or_none()

        if memory:
            if expected_version is not None and memory.version != expected_version:
                raise ValueError("Memory conflict: another update happened first. Please retry.")
            memory.memory_value = memory_value
            memory.version += 1
            memory.updated_at = utcnow()
        else:
            memory = UserMemory(
                user_id=user_id,
                memory_key=memory_key,
                memory_value=memory_value,
            )
            db.add(memory)

        db.commit()
        db.refresh(memory)
        return memory

    def get_user_memories(self, db: Session, user_id: uuid.UUID) -> list[UserMemory]:
        from sqlalchemy import select

        stmt = select(UserMemory).where(UserMemory.user_id == user_id).order_by(UserMemory.updated_at.desc())
        return list(db.execute(stmt).scalars().all())

    def build_long_term_context(self, db: Session, user_id: uuid.UUID) -> str:
        memories = self.get_user_memories(db, user_id)
        if not memories:
            return ""
        lines = [f"- {m.memory_key}: {m.memory_value}" for m in memories[:10]]
        return "Known facts about this user:\n" + "\n".join(lines)


class MemoryService:
    """Unified memory interface for chat orchestration."""

    def __init__(self, redis_client=None):
        self.short_term = ShortTermMemory(redis_client) if redis_client else None
        self.long_term = LongTermMemory()

    def load_history(
        self,
        db: Session,
        user_id: str,
        session_id: str,
        user_uuid: uuid.UUID,
        session_uuid: uuid.UUID,
    ) -> list[dict]:
        if self.short_term:
            history = self.short_term.get_history(user_id, session_id)
            if history:
                return history

        db_messages = self.long_term.get_messages(db, user_uuid, session_uuid)
        return [{"role": m.role, "content": m.content, "sources": json.loads(m.sources) if m.sources else []} for m in db_messages]

    def save_turn(
        self,
        db: Session,
        user_id: str,
        session_id: str,
        user_uuid: uuid.UUID,
        session_uuid: uuid.UUID,
        question: str,
        answer: str,
        sources: list[str],
        history: list[dict],
    ) -> None:
        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": answer, "sources": sources})

        if self.short_term:
            self.short_term.save_history(user_id, session_id, history)

        try:
            self.long_term.save_message(db, user_uuid, session_uuid, "user", question)
            self.long_term.save_message(db, user_uuid, session_uuid, "assistant", answer, sources=sources)
        except Exception as exc:
            logger.warning("Could not persist to PostgreSQL: %s", exc)
