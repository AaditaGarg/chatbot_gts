"""FastAPI application — transport layer for the hybrid AI assistant."""

import json
import logging
import threading
import uuid
from typing import Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from config.settings import LLM_PROVIDER, OLLAMA_MODEL
from database.chroma_store import get_collection, init_chroma
from database.postgres import get_db, init_db, check_db_connection
from database.redis_client import check_redis_connection, get_redis_client
from models.schemas import (
    ChatRequest,
    ChatResponse,
    DocumentUploadResponse,
    HealthResponse,
    SessionCreateRequest,
    SessionResponse,
    UserCreateRequest,
    UserResponse,
)
from services.chat_service import ChatService
from services.document_service import DocumentService
from services.llm_service import LLMService
from services.memory_service import MemoryService
from services.rag_service import RAGService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="GTS Hybrid AI Assistant", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Shared services (initialized at startup) ---
llm_service = LLMService()
rag_service = RAGService()
memory_service: Optional[MemoryService] = None
chat_service: Optional[ChatService] = None
document_service: Optional[DocumentService] = None

_session_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _get_session_lock(user_id: str, session_id: str) -> threading.Lock:
    key = f"{user_id}:{session_id}"
    with _locks_guard:
        if key not in _session_locks:
            _session_locks[key] = threading.Lock()
        return _session_locks[key]


def get_redis():
    client = get_redis_client()
    if not client:
        raise HTTPException(status_code=503, detail="Redis is not available. Start Redis to use chat memory.")
    return client


def _friendly_error(status: int, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail=message)


@app.on_event("startup")
def startup_event():
    global memory_service, chat_service, document_service
    logger.info("--- Server Startup ---")

    try:
        init_db()
        logger.info("PostgreSQL tables ready.")
    except Exception as exc:
        logger.warning("PostgreSQL init failed: %s", exc)

    redis_client = get_redis_client()
    memory_service = MemoryService(redis_client)

    rag_service.init_embedding_model()
    init_chroma()
    llm_service.init()

    chat_service = ChatService(llm=llm_service, rag=rag_service, memory=memory_service)
    document_service = DocumentService(rag_service)

    logger.info("--- Startup Complete ---")


app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def read_index():
    return FileResponse("static/index.html")


@app.get("/health", response_model=HealthResponse)
async def health_check():
    chroma_ok = get_collection() is not None
    return HealthResponse(
        status="ok" if chroma_ok and check_redis_connection() else "degraded",
        redis=check_redis_connection(),
        postgres=check_db_connection(),
        chromadb=chroma_ok,
        ollama_model=OLLAMA_MODEL,
        llm_provider=LLM_PROVIDER,
    )


@app.post("/users", response_model=UserResponse)
async def create_user(request: UserCreateRequest, db: Session = Depends(get_db)):
    try:
        user = memory_service.long_term.create_user(db, display_name=request.display_name.strip() or "Guest")
        return UserResponse(user_id=str(user.user_id), display_name=user.display_name)
    except Exception:
        raise _friendly_error(500, "Could not create user. Please try again.")


@app.get("/users/{user_id}", response_model=UserResponse)
async def get_user(user_id: str, db: Session = Depends(get_db)):
    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        raise _friendly_error(400, "Invalid user ID format.")
    user = memory_service.long_term.get_user(db, user_uuid)
    if not user:
        raise _friendly_error(404, "User not found.")
    return UserResponse(user_id=str(user.user_id), display_name=user.display_name)


@app.post("/session", response_model=SessionResponse)
async def create_session(request: SessionCreateRequest, db: Session = Depends(get_db)):
    try:
        user_uuid = uuid.UUID(request.user_id)
    except ValueError:
        raise _friendly_error(400, "Invalid user ID format.")

    user = memory_service.long_term.get_user(db, user_uuid)
    if not user:
        raise _friendly_error(404, "User not found. Create a user first.")

    conversation = memory_service.long_term.create_conversation(db, user_uuid, title=request.title)
    session_id = str(conversation.conversation_id)

    if memory_service.short_term:
        memory_service.short_term.set_active_session(request.user_id, session_id)
        memory_service.short_term.save_history(request.user_id, session_id, [])

    return SessionResponse(session_id=session_id, user_id=request.user_id, title=conversation.title)


@app.get("/sessions/{user_id}")
async def list_sessions(user_id: str, db: Session = Depends(get_db)):
    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        raise _friendly_error(400, "Invalid user ID format.")

    conversations = memory_service.long_term.list_conversations(db, user_uuid)
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
        try:
            user_uuid = uuid.UUID(user_id)
            session_uuid = uuid.UUID(session_id)
        except ValueError:
            raise _friendly_error(400, "Invalid session ID format.")

        history = memory_service.load_history(db, user_id, session_id, user_uuid, session_uuid)
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
            raise _friendly_error(400, "Invalid session ID format.")

        if memory_service.short_term:
            memory_service.short_term.clear_history(user_id, session_id)
        memory_service.long_term.clear_conversation(db, user_uuid, session_uuid)
        return {"message": "Conversation cleared."}


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, db: Session = Depends(get_db), redis_conn=Depends(get_redis)):
    question = request.question.strip()
    if not question:
        raise _friendly_error(400, "Question cannot be empty.")

    lock = _get_session_lock(request.user_id, request.session_id)
    with lock:
        try:
            return chat_service.process_message(db, request.user_id, request.session_id, question)
        except ValueError as exc:
            raise _friendly_error(404, str(exc))
        except RuntimeError as exc:
            raise _friendly_error(503, "The AI service is temporarily unavailable. Please try again shortly.")
        except Exception as exc:
            logger.exception("Chat error: %s", exc)
            raise _friendly_error(503, f"Could not generate a response. Ensure Ollama is running with model '{OLLAMA_MODEL}'.")


@app.post("/chat/stream")
async def chat_stream(request: ChatRequest, db: Session = Depends(get_db), redis_conn=Depends(get_redis)):
    """Stream tokens via Server-Sent Events."""
    question = request.question.strip()
    if not question:
        raise _friendly_error(400, "Question cannot be empty.")

    lock = _get_session_lock(request.user_id, request.session_id)

    def event_generator():
        with lock:
            try:
                token_gen, pipeline = chat_service.stream_message(
                    db, request.user_id, request.session_id, question
                )
                for token in token_gen:
                    yield f"data: {json.dumps({'token': token})}\n\n"

                result = chat_service.finalize_stream(
                    db, request.user_id, request.session_id, question, pipeline
                )
                yield f"data: {json.dumps({'done': True, 'sources': result.sources, 'intent': result.intent})}\n\n"
            except ValueError as exc:
                yield f"data: {json.dumps({'error': str(exc)})}\n\n"
            except Exception:
                yield f"data: {json.dumps({'error': 'Could not generate a response.'})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/documents/upload", response_model=DocumentUploadResponse)
async def upload_document(
    user_id: str = Form(...),
    session_id: Optional[str] = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Upload and index a document (PDF, DOCX, TXT, CSV)."""
    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        raise _friendly_error(400, "Invalid user ID format.")

    user = memory_service.long_term.get_user(db, user_uuid)
    if not user:
        raise _friendly_error(404, "User not found.")

    session_uuid = None
    if session_id:
        try:
            session_uuid = uuid.UUID(session_id)
        except ValueError:
            raise _friendly_error(400, "Invalid session ID format.")

    content = await file.read()
    if not content:
        raise _friendly_error(400, "Uploaded file is empty.")

    try:
        doc = document_service.ingest_file(
            db=db,
            user_id=user_uuid,
            session_id=session_uuid,
            filename=file.filename or "upload.txt",
            content=content,
        )
    except ValueError as exc:
        raise _friendly_error(400, str(exc))
    except RuntimeError as exc:
        raise _friendly_error(503, str(exc))
    except Exception as exc:
        logger.exception("Upload error: %s", exc)
        raise _friendly_error(500, "Could not process the uploaded file.")

    return DocumentUploadResponse(
        document_id=str(doc.document_id),
        filename=doc.filename,
        chunk_count=doc.chunk_count,
        message=f"Successfully indexed {doc.chunk_count} chunks from '{doc.filename}'.",
    )


@app.get("/documents/{user_id}")
async def list_documents(user_id: str, db: Session = Depends(get_db)):
    from sqlalchemy import select
    from database.postgres import Document

    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        raise _friendly_error(400, "Invalid user ID format.")

    stmt = select(Document).where(Document.user_id == user_uuid).order_by(Document.created_at.desc())
    docs = db.execute(stmt).scalars().all()
    return {
        "documents": [
            {
                "document_id": str(d.document_id),
                "filename": d.filename,
                "file_type": d.file_type,
                "chunk_count": d.chunk_count,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in docs
        ]
    }
