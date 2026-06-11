Manual test cases

1. No index present
   - Run `python main.py` or call /chat -> should return 400 with message to run ingest.

2. Ingest docs
   - Put a text file into `docs/faq.txt` with some Q/A and run `python data_ingest.py`. Ensure index is created.

3. Chat
   - Start server: `uvicorn main:app --reload --port 8000`
   - POST to http://localhost:8000/chat with JSON {"question":"How do I reset my password?", "k":3}
   - Response should contain answer and sources array.
