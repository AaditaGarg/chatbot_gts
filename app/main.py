import json
import threading
import uuid
from typing import Optional

import chromadb
import ollama
import redis
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sentence_transformers import SentenceTransformer
from sqlalchemy.orm import Session

from config import (
    COLLECTION_NAME,
    EMBEDDING_MODEL,
    OLLAMA_MODEL,
    PERSIST_DIRECTORY,
    RAG_TOP_K,
    REDIS_HOST,
    REDIS_PORT,
    SYSTEM_PROMPT,
)
from database import check_db_connection, get_db, init_db
from memory import LongTermMemory, ShortTermMemory

app = FastAPI(title="GTS Multi-User Chatbot", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

embedding_model = None
chroma_client = None
collection = None
redis_client = None
short_term: Optional[ShortTermMemory] = None
long_term = LongTermMemory()

_session_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _get_session_lock(user_id: str, session_id: str) -> threading.Lock:
    key = f"{user_id}:{session_id}"
    with _locks_guard:
        if key not in _session_locks:
            _session_locks[key] = threading.Lock()
        return _session_locks[key]


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
    question: str = Field(min_length=1, max_length=2000)


class ChatResponse(BaseModel):
    answer: str
    sources: list[str] = []
    session_id: str
    user_id: str


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


@app.on_event("startup")
def startup_event():
    global embedding_model, chroma_client, collection, redis_client, short_term
    print("--- Server Startup ---")

    try:
        init_db()
        print("PostgreSQL tables ready.")
    except Exception as e:
        print(f"WARN: PostgreSQL init failed. Long-term memory disabled. {e}")

    try:
        redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
        redis_client.ping()
        short_term = ShortTermMemory(redis_client)
        print("Redis connection successful.")
    except Exception as e:
        print(f"WARN: Redis unavailable. Short-term memory disabled. {e}")
        redis_client = None
        short_term = None

    try:
        embedding_model = SentenceTransformer(EMBEDDING_MODEL)
        print("Embedding model loaded.")
    except Exception as e:
        print(f"ERROR: Failed to load embedding model. {e}")
        return

    try:
        chroma_client = chromadb.PersistentClient(path=PERSIST_DIRECTORY)
        collection = chroma_client.get_collection(name=COLLECTION_NAME)
        print(f"ChromaDB ready with {collection.count()} documents.")
    except Exception as e:
        print(f"WARN: ChromaDB unavailable. RAG disabled. {e}")
        collection = None

    print("--- Startup Complete ---")


def get_redis():
    if not redis_client:
        raise HTTPException(status_code=503, detail="Redis is not available. Start Redis to use chat memory.")
    return redis_client


def find_relevant_chunks(question: str) -> list[str]:
    if not collection or not embedding_model:
        return []

    query_embedding = embedding_model.encode([question]).tolist()
    results = collection.query(query_embeddings=query_embedding, n_results=RAG_TOP_K)
    if not results or not results.get("documents"):
        return []
    return [doc for doc in results["documents"][0] if doc]


def build_rag_prompt(question: str, context_chunks: list[str], long_term_context: str = "") -> str:
    parts = [SYSTEM_PROMPT]

    if long_term_context:
        parts.append(long_term_context)

    if context_chunks:
        context = "\n\n---\n\n".join(context_chunks)
        parts.append(f"Relevant knowledge base context:\n{context}")
        parts.append(
            f"User question: {question}\n\n"
            "Answer using the context above. If the context does not answer the question, "
            "say you don't have that information and suggest contacting support@example.com."
        )
    else:
        parts.append(
            f"User question: {question}\n\n"
            "No knowledge base context was found. Politely explain you don't have specific "
            "information and suggest contacting support@example.com."
        )

    return "\n\n".join(parts)


def call_ollama(history: list[dict], prompt: str) -> str:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for msg in history[-10:]:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": prompt})

    response = ollama.chat(model=OLLAMA_MODEL, messages=messages)
    return response["message"]["content"]


app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def read_index():
    return FileResponse("static/index.html")


@app.get("/health", response_model=HealthResponse)
async def health_check():
    chroma_ok = collection is not None
    redis_ok = False
    if redis_client:
        try:
            redis_ok = redis_client.ping()
        except Exception:
            redis_ok = False
    return HealthResponse(
        status="ok" if chroma_ok and redis_ok else "degraded",
        redis=redis_ok,
        postgres=check_db_connection(),
        chromadb=chroma_ok,
        ollama_model=OLLAMA_MODEL,
    )


@app.post("/users", response_model=UserResponse)
async def create_user(request: UserCreateRequest, db: Session = Depends(get_db)):
    try:
        user = long_term.create_user(db, display_name=request.display_name.strip() or "Guest")
        return UserResponse(user_id=str(user.user_id), display_name=user.display_name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not create user: {e}")


@app.get("/users/{user_id}", response_model=UserResponse)
async def get_user(user_id: str, db: Session = Depends(get_db)):
    user = long_term.get_user(db, uuid.UUID(user_id))
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    return UserResponse(user_id=str(user.user_id), display_name=user.display_name)


@app.post("/session", response_model=SessionResponse)
async def create_session(request: SessionCreateRequest, db: Session = Depends(get_db)):
    try:
        user_uuid = uuid.UUID(request.user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user_id format.")

    user = long_term.get_user(db, user_uuid)
    if not user:
        raise HTTPException(status_code=404, detail="User not found. Create a user first.")

    conversation = long_term.create_conversation(db, user_uuid, title=request.title)
    session_id = str(conversation.conversation_id)

    if short_term:
        short_term.set_active_session(request.user_id, session_id)
        short_term.save_history(request.user_id, session_id, [])

    return SessionResponse(session_id=session_id, user_id=request.user_id, title=conversation.title)


@app.get("/sessions/{user_id}")
async def list_sessions(user_id: str, db: Session = Depends(get_db)):
    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user_id format.")

    conversations = long_term.list_conversations(db, user_uuid)
    return {
        "sessions": [
            {
                "session_id": str(c.conversation_id),
                "title": c.title,
                "updated_at": c.updated_at.isoformat() if c.updated_at else None,
            }
            for c in conversations
        ]
    }


@app.get("/history/{user_id}/{session_id}")
async def get_history(
    user_id: str,
    session_id: str,
    db: Session = Depends(get_db),
    redis_conn=Depends(get_redis),
):
    lock = _get_session_lock(user_id, session_id)
    with lock:
        if short_term:
            redis_history = short_term.get_history(user_id, session_id)
            if redis_history:
                return {"messages": redis_history}

        try:
            user_uuid = uuid.UUID(user_id)
            session_uuid = uuid.UUID(session_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid UUID format.")

        messages = long_term.get_messages(db, user_uuid, session_uuid)
        history = []
        for msg in messages:
            sources = json.loads(msg.sources) if msg.sources else []
            history.append(
                {
                    "role": msg.role,
                    "content": msg.content,
                    "sources": sources,
                    "created_at": msg.created_at.isoformat() if msg.created_at else None,
                }
            )

        if short_term and history:
            short_term.save_history(user_id, session_id, [{"role": m["role"], "content": m["content"]} for m in history])

        return {"messages": history}


@app.post("/clear/{user_id}/{session_id}")
async def clear_history(
    user_id: str,
    session_id: str,
    db: Session = Depends(get_db),
    redis_conn=Depends(get_redis),
):
    lock = _get_session_lock(user_id, session_id)
    with lock:
        try:
            user_uuid = uuid.UUID(user_id)
            session_uuid = uuid.UUID(session_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid UUID format.")

        if short_term:
            short_term.clear_history(user_id, session_id)

        long_term.clear_conversation(db, user_uuid, session_uuid)
        return {"message": "Conversation cleared."}


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, db: Session = Depends(get_db), redis_conn=Depends(get_redis)):
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    lock = _get_session_lock(request.user_id, request.session_id)
    with lock:
        try:
            user_uuid = uuid.UUID(request.user_id)
            session_uuid = uuid.UUID(request.session_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid UUID format.")

print("request.user_id =", request.user_id)
print("request.session_id =", request.session_id)
print("user_uuid =", user_uuid)
print("session_uuid =", session_uuid)

        conversation = long_term.get_conversation(db, user_uuid, session_uuid)
print("conversation =", conversation)
        if not conversation:
            raise HTTPException(status_code=404, detail="Session not found for this user.")

        history = short_term.get_history(request.user_id, request.session_id) if short_term else []
        if not history:
            db_messages = long_term.get_messages(db, user_uuid, session_uuid)
            history = [{"role": m.role, "content": m.content} for m in db_messages]

        relevant_chunks = find_relevant_chunks(question)
        long_term_context = long_term.build_long_term_context(db, user_uuid)
        prompt = build_rag_prompt(question, relevant_chunks, long_term_context)

        try:
            answer = call_ollama(history, prompt)
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"LLM unavailable. Ensure Ollama is running with model '{OLLAMA_MODEL}'. Error: {e}")

        sources = [chunk[:120] + "..." if len(chunk) > 120 else chunk for chunk in relevant_chunks]

        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": answer})
        if short_term:
            short_term.save_history(request.user_id, request.session_id, history)

        try:
            long_term.save_message(db, user_uuid, session_uuid, "user", question)
            long_term.save_message(db, user_uuid, session_uuid, "assistant", answer, sources=sources)
        except Exception as e:
            print(f"WARN: Could not persist to PostgreSQL: {e}")

        return ChatResponse(
            answer=answer,
            sources=sources,
            session_id=request.session_id,
            user_id=request.user_id,
        )
