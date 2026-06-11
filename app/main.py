import os
import threading
import uuid
import json
import redis
import chromadb
from fastapi import FastAPI, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer
import ollama

# --- Configuration ---
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
OLLAMA_MODEL = "llama3"
PERSIST_DIRECTORY = "chroma_db"
COLLECTION_NAME = "chatbot_docs"
REDIS_HOST = "localhost"
REDIS_PORT = 6379

# --- FastAPI App Initialization ---
app = FastAPI()

# --- Global Variables & Clients ---
embedding_model = None
chroma_client = None
collection = None
redis_client = None

# --- Pydantic Models ---
class ChatRequest(BaseModel):
    question: str
    session_id: str

class SessionResponse(BaseModel):
    session_id: str

# --- Startup Logic ---
@app.on_event("startup")
def startup_event():
    global embedding_model, chroma_client, collection, redis_client
    print("--- Server Startup ---")

    # 1. Connect to Redis
    try:
        print(f"Connecting to Redis at {REDIS_HOST}:{REDIS_PORT}...")
        redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
        redis_client.ping()
        print("Redis connection successful.")
    except Exception as e:
        print(f"ERROR: Could not connect to Redis. Please ensure it is running. {e}")
        redis_client = None

    # 2. Load Embedding Model
    try:
        print(f"Loading embedding model: {EMBEDDING_MODEL}")
        embedding_model = SentenceTransformer(EMBEDDING_MODEL)
        print("Embedding model loaded successfully.")
    except Exception as e:
        print(f"ERROR: Failed to load embedding model. {e}")
        return

    # 3. Connect to ChromaDB
    try:
        print(f"Connecting to ChromaDB at '{PERSIST_DIRECTORY}'...")
        chroma_client = chromadb.PersistentClient(path=PERSIST_DIRECTORY)
        collection = chroma_client.get_collection(name=COLLECTION_NAME)
        print(f"Successfully connected to ChromaDB collection '{COLLECTION_NAME}'.")
        print(f"Collection contains {collection.count()} documents.")
    except Exception as e:
        print(f"WARN: Could not connect to ChromaDB collection. RAG will be disabled. {e}")
        print("Please run 'python data_ingest.py' to create the database.")
        collection = None
    
    print("--- Startup Complete ---")

# --- Helper Functions ---
def get_redis():
    if not redis_client:
        raise HTTPException(status_code=503, detail="Redis connection not available.")
    return redis_client

def get_conversation_history(session_id: str, redis_conn):
    history_json = redis_conn.get(session_id)
    if history_json:
        return json.loads(history_json)
    return []

def save_conversation_history(session_id: str, history: list, redis_conn):
    redis_conn.set(session_id, json.dumps(history))

def find_relevant_chunks(question: str):
    if not collection or not embedding_model:
        return []
    
    query_embedding = embedding_model.encode([question]).tolist()
    
    results = collection.query(
        query_embeddings=query_embedding,
        n_results=3  # Return top 3 most relevant chunks
    )
    
    return results['documents'][0] if results and results['documents'] else []

# --- API Endpoints ---
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def read_index():
    return FileResponse('static/index.html')

@app.post("/session", response_model=SessionResponse)
async def create_session():
    session_id = str(uuid.uuid4())
    return SessionResponse(session_id=session_id)

@app.post("/clear/{session_id}")
async def clear_history(session_id: str, redis_conn=Depends(get_redis)):
    redis_conn.delete(session_id)
    return {"message": "Conversation history cleared."}

@app.post("/chat")
async def chat(request: ChatRequest, redis_conn=Depends(get_redis)):
    try:
        history = get_conversation_history(request.session_id, redis_conn)
        
        # --- RAG Implementation ---
        context_str = ""
        if collection:
            relevant_chunks = find_relevant_chunks(request.question)
            if relevant_chunks:
                context_str = "\n\n".join(relevant_chunks)
                prompt = f"Based on the following context, answer the user's question.\n\nContext:\n{context_str}\n\nQuestion: {request.question}"
            else:
                prompt = request.question
        else:
            prompt = request.question

        # Add user's message to history for context
        history.append({"role": "user", "content": prompt})

        # --- Call Ollama ---
        response = ollama.chat(
            model=OLLAMA_MODEL,
            messages=history
        )
        answer = response['message']['content']

        # --- Save History ---
        # Add the actual user question (not the modified prompt)
        history[-1] = {"role": "user", "content": request.question} 
        history.append({"role": "assistant", "content": answer})
        save_conversation_history(request.session_id, history, redis_conn)

        return {"answer": answer}

    except Exception as e:
        print(f"ERROR in /chat endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))
