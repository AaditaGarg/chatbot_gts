import os
from dotenv import load_dotenv

load_dotenv()

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")
PERSIST_DIRECTORY = os.getenv("PERSIST_DIRECTORY", "chroma_db")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "chatbot_docs")
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "5"))

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_TTL_SECONDS = int(os.getenv("REDIS_TTL_SECONDS", "86400"))
REDIS_MAX_MESSAGES = int(os.getenv("REDIS_MAX_MESSAGES", "50"))
REDIS_KEY_PREFIX = os.getenv("REDIS_KEY_PREFIX", "chatbot")

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://chatbot:chatbot@localhost:5432/chatbot_db",
)

SYSTEM_PROMPT = """You are a helpful customer support assistant for GTS (Global Tech Solutions).
Answer questions clearly and concisely using ONLY the provided context when available.
If the context does not contain enough information, say so honestly and offer to connect the user with human support.
Never invent policies, prices, or features that are not in the context.
Keep responses friendly, professional, and under 200 words unless more detail is needed."""
