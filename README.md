AI-Powered RAG Chatbot
An intelligent Retrieval-Augmented Generation (RAG) chatbot built using FastAPI, FAISS, ChromaDB, and Large Language Models (LLMs). The chatbot enables users to query custom documents and receive context-aware responses by combining semantic search with generative AI.
Features
User-friendly chatbot interface
FastAPI backend for efficient API handling
Retrieval-Augmented Generation (RAG) pipeline
Document ingestion and preprocessing
Semantic search using vector embeddings
FAISS and ChromaDB integration for vector storage
Context-aware response generation
Support for custom knowledge bases
Scalable and modular architecture
Project Architecture
Documents are uploaded and processed.
Text is split into smaller chunks.
Embeddings are generated for each chunk.
Embeddings are stored in a vector database (FAISS/ChromaDB).
User queries are converted into embeddings.
Relevant document chunks are retrieved using similarity search.
Retrieved context is passed to the LLM.
The chatbot generates an accurate and context-aware response.

Tech Stack
Backend
Python
FastAPI
Uvicorn
AI & Machine Learning
Retrieval-Augmented Generation (RAG)
Embedding Models
Large Language Models (LLMs)
Vector Databases
FAISS
ChromaDB
Frontend
HTML
CSS
JavaScript
Project Structure
app/
├── main.py                 # FastAPI application
├── data_ingest.py          # Document ingestion pipeline
├── utils.py                # Helper functions
├── docs/                   # Knowledge base documents
├── static/                 # Frontend files
├── chroma_db/              # ChromaDB storage
├── faiss_index.idx         # FAISS vector index
└── requirements.txt        # Dependencies
