"""Knowledge base ingestion with metadata support."""

import os
import uuid

import chromadb
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sentence_transformers import SentenceTransformer
from tqdm import tqdm

from config.settings import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    COLLECTION_NAME,
    EMBEDDING_MODEL,
    PERSIST_DIRECTORY,
)

DOCS_DIR = os.getenv("DOCS_DIR", "docs")


def data_ingest(user_id: str = "system", session_id: str = ""):
    """Ingest documents from DOCS_DIR into ChromaDB with metadata."""
    print("--- Starting Data Ingestion ---")

    documents: list[tuple[str, str]] = []
    if not os.path.exists(DOCS_DIR):
        print(f"ERROR: The directory '{DOCS_DIR}' was not found.")
        return

    for filename in os.listdir(DOCS_DIR):
        if filename.endswith(".txt"):
            filepath = os.path.join(DOCS_DIR, filename)
            with open(filepath, "r", encoding="utf-8") as f:
                documents.append((filename, f.read()))

    if not documents:
        print("No .txt documents found to process.")
        return
    print(f"Found {len(documents)} documents to process.")

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
    )

    all_chunks: list[str] = []
    all_ids: list[str] = []
    all_metadatas: list[dict] = []

    doc_id = str(uuid.uuid4())
    for filename, text in documents:
        splits = text_splitter.split_text(text)
        for i, chunk in enumerate(splits):
            all_chunks.append(chunk)
            all_ids.append(f"{doc_id}_{filename}_{i}")
            all_metadatas.append(
                {
                    "user_id": user_id,
                    "document_id": doc_id,
                    "session_id": session_id,
                    "filename": filename,
                    "chunk_index": i,
                    "source": "data_ingest",
                }
            )

    print(f"Created {len(all_chunks)} text chunks.")

    client = chromadb.PersistentClient(path=PERSIST_DIRECTORY)
    try:
        client.delete_collection(name=COLLECTION_NAME)
        print("Removed existing collection for fresh ingest.")
    except Exception:
        pass

    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )

    print(f"Loading embedding model: {EMBEDDING_MODEL}")
    model = SentenceTransformer(EMBEDDING_MODEL)

    batch_size = 100
    print(f"Adding {len(all_chunks)} documents to ChromaDB in batches of {batch_size}...")
    for i in tqdm(range(0, len(all_chunks), batch_size)):
        batch_docs = all_chunks[i : i + batch_size]
        batch_ids = all_ids[i : i + batch_size]
        batch_meta = all_metadatas[i : i + batch_size]
        embeddings = model.encode(batch_docs, show_progress_bar=False).tolist()
        collection.add(
            embeddings=embeddings,
            documents=batch_docs,
            ids=batch_ids,
            metadatas=batch_meta,
        )

    print("\n--- Data Ingestion Complete ---")
    print(f"Total documents in collection '{COLLECTION_NAME}': {collection.count()}")


if __name__ == "__main__":
    data_ingest()
