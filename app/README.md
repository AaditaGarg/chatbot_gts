Customer Support Chatbot

This project provides a lightweight customer-support chatbot using:
- Python + FastAPI
- OpenAI APIs (embeddings + chat completions)
- FAISS vector store for retrieval-augmented generation (RAG)

Quick start

1. Copy environment variables:

   cp .env.example .env
   (set OPENAI_API_KEY in .env)

2. Install dependencies:

   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt

3. Ingest your docs into the vectorstore (place plain text files under `docs/`):

   python data_ingest.py

4. Run the API server:

   uvicorn main:app --reload --port 8000

5. Send a POST to http://localhost:8000/chat with JSON {"question":"...", "k":4}

Notes

- This code uses the OpenAI API. Keep your API key private.
- The vector store is stored in `storage/` as a FAISS index and `storage/metadata.jsonl`.
- Tweak model names in `.env` if you want to use a different OpenAI model.
