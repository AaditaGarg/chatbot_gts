# GTS Hybrid AI Assistant

An intelligent multi-user AI assistant with hybrid routing — general conversation, document intelligence (RAG), web search, and tool support. Built with FastAPI, Ollama, ChromaDB, Redis, and PostgreSQL.

## Architecture

```mermaid
flowchart TD
    User[User / Web / Mobile / Voice] --> API[FastAPI Transport Layer]
    API --> CS[ChatService]

    CS --> IC[IntentClassifier]
    IC --> Route{Hybrid Router}

    Route -->|Greeting / Chat / Coding| LLM[LLMService]
    Route -->|Document Question| RAG[RAGService]
    Route -->|Current Events| WS[WebSearchService]
    Route -->|Calculation| TR[ToolRouter]

    RAG --> ChromaDB[(ChromaDB)]
    WS --> Internet[Web APIs]
    TR --> Calc[Calculator / Future Tools]

    RAG --> PB[PromptBuilder]
    WS --> PB
    TR --> PB
    PB --> LLM

    LLM --> Ollama[Ollama / OpenAI / etc.]

    CS --> Mem[MemoryService]
    Mem --> Redis[(Redis - Session)]
    Mem --> PG[(PostgreSQL - Persistent)]

    API --> DocSvc[DocumentService]
    DocSvc --> ChromaDB
    DocSvc --> PG
```

### Hybrid Routing Flow

```
User Question
    ↓
Intent Detection (IntentClassifier)
    ↓
Need Documents?  ──YES──► ChromaDB Search (with similarity threshold)
    │ NO
    ↓
Need Internet?   ──YES──► Web Search (DuckDuckGo / Tavily)
    │ NO
    ↓
Need Tools?      ──YES──► Tool Router (Calculator, etc.)
    │ NO
    ↓
Prompt Builder (dynamic — context only when relevant)
    ↓
LLM Service (Ollama / configurable provider)
    ↓
Response (streaming or JSON)
```

## Quick Start

```bash
docker compose up -d
cd app && python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp ../.env.example .env
python data_ingest.py   # optional
ollama pull llama3 && ollama serve
uvicorn main:app --reload --port 8000
```

Open http://localhost:8000

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/chat` | POST | Send message (JSON) |
| `/chat/stream` | POST | Send message (SSE streaming) |
| `/documents/upload` | POST | Upload PDF/DOCX/TXT/CSV |
| `/documents/{user_id}` | GET | List uploaded documents |
| `/users`, `/session`, `/history`, `/clear`, `/health` | | Unchanged |

See `.env.example` for all configuration options.
