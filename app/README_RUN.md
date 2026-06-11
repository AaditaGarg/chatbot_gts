Run instructions for macOS (zsh)

1. Create virtual env and install deps

   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt

2. Copy env and set key

   cp .env.example .env
   # edit .env and set OPENAI_API_KEY

3. Ingest docs

   python data_ingest.py

4. Run server

   uvicorn main:app --reload --port 8000

5. Query

   curl -X POST "http://localhost:8000/chat" -H "Content-Type: application/json" -d '{"question":"How do I reset my password?", "k":2}'
