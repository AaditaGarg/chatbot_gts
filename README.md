# GTS Multi-User RAG Chatbot

An intelligent multi-user chatbot with Retrieval-Augmented Generation (RAG), built for internship demonstration. Supports unique user UUIDs, Redis short-term memory, PostgreSQL long-term persistence, and a modern chat UI.

## Architecture

```
User (UUID) ──► Session (UUID) ──► Redis (active chat history, 24h TTL)
                              └──► PostgreSQL (users, conversations, messages, long-term memory)
User Query ──► ChromaDB (RAG) ──► Ollama LLM ──► Response + Sources
```

### Multi-User Design

- Each user gets a unique `user_id` (UUID) — stored in browser localStorage
- Each user can have multiple conversations (`session_id` per conversation)
- Redis stores active session history per `user_id:session_id` (fast, isolated)
- PostgreSQL persists all messages with `user_id` foreign keys (no cross-user data leaks)
- Per-session locking prevents concurrent write conflicts on the same conversation

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI, Python 3.10+ |
| LLM | Ollama (`llama3`) |
| Embeddings | sentence-transformers (`all-MiniLM-L6-v2`) |
| Vector DB | ChromaDB |
| Short-term memory | Redis |
| Long-term memory | PostgreSQL |
| Frontend | HTML, CSS, JavaScript |

## Quick Start

### 1. Start infrastructure

```bash
docker compose up -d
```

### 2. Set up Python environment

```bash
cd app
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp ../.env.example .env
```

### 3. Ingest knowledge base

```bash
python data_ingest.py
```

### 4. Start Ollama (if not running)

```bash
ollama pull llama3
ollama serve
```

### 5. Run the server

```bash
uvicorn main:app --reload --port 8000
```

Open http://localhost:8000 in your browser.

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/users` | POST | Create a new user (returns `user_id`) |
| `/users/{user_id}` | GET | Get user info |
| `/session` | POST | Create conversation for a user |
| `/sessions/{user_id}` | GET | List user's conversations |
| `/history/{user_id}/{session_id}` | GET | Load chat history |
| `/chat` | POST | Send a message |
| `/clear/{user_id}/{session_id}` | POST | Clear a conversation |
| `/health` | GET | System health check |

### Chat request example

```json
{
  "user_id": "uuid-here",
  "session_id": "uuid-here",
  "question": "How do I reset my password?"
}
```

## Project Structure

```
app/
├── main.py           # FastAPI app and API routes
├── config.py         # Environment configuration
├── database.py       # PostgreSQL models (SQLAlchemy)
├── memory.py         # Redis + PostgreSQL memory layer
├── data_ingest.py    # Knowledge base ingestion
├── docs/             # FAQ knowledge base
├── static/           # Frontend (HTML, CSS, JS)
├── chroma_db/        # ChromaDB vector store
└── requirements.txt
docker-compose.yml    # PostgreSQL + Redis
.env.example          # Environment template
```

## Environment Variables

See `.env.example` for all options. Key variables:

- `DATABASE_URL` — PostgreSQL connection string
- `REDIS_HOST` / `REDIS_PORT` — Redis connection
- `OLLAMA_MODEL` — LLM model name (default: `llama3`)
