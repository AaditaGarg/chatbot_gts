import os
import chromadb
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sentence_transformers import SentenceTransformer
from tqdm import tqdm

# --- Configuration ---
DOCS_DIR = "docs"  # Directory containing your text files
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
PERSIST_DIRECTORY = "chroma_db"
COLLECTION_NAME = "chatbot_docs"

# --- ChromaDB Client ---
# Using a persistent client that saves to disk
client = chromadb.PersistentClient(path=PERSIST_DIRECTORY)

# --- Main Ingestion Logic ---
def data_ingest():
    """
    Ingests data from the DOCS_DIR, processes it, and stores it in ChromaDB.
    """
    print("--- Starting Data Ingestion ---")

    # 1. Load Documents
    documents = []
    if not os.path.exists(DOCS_DIR):
        print(f"ERROR: The directory '{DOCS_DIR}' was not found.")
        return

    for filename in os.listdir(DOCS_DIR):
        if filename.endswith(".txt"):
            filepath = os.path.join(DOCS_DIR, filename)
            with open(filepath, 'r', encoding='utf-8') as f:
                documents.append(f.read())
    
    if not documents:
        print("No .txt documents found to process.")
        return
    print(f"Found {len(documents)} documents to process.")

    # 2. Split Documents into Chunks
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP
    )
    all_splits = text_splitter.create_documents(documents)
    print(f"Created {len(all_splits)} text chunks.")

    # 3. Get or Create ChromaDB Collection (reset on re-ingest)
    print(f"Preparing ChromaDB collection: '{COLLECTION_NAME}'")
    try:
        client.delete_collection(name=COLLECTION_NAME)
        print("Removed existing collection for fresh ingest.")
    except Exception:
        pass
    collection = client.get_or_create_collection(name=COLLECTION_NAME)

    # 4. Generate Embeddings and Store in ChromaDB
    print(f"Loading embedding model: {EMBEDDING_MODEL}")
    try:
        model = SentenceTransformer(EMBEDDING_MODEL)
    except Exception as e:
        print(f"Error loading SentenceTransformer model: {e}")
        return

    # Prepare data for ChromaDB
    ids = [f"chunk_{i}" for i in range(len(all_splits))]
    docs_to_add = [doc.page_content for doc in all_splits]
    
    # Add to collection in batches to avoid overwhelming memory
    batch_size = 100
    print(f"Adding {len(docs_to_add)} documents to ChromaDB in batches of {batch_size}...")
    for i in tqdm(range(0, len(docs_to_add), batch_size)):
        batch_docs = docs_to_add[i:i+batch_size]
        batch_ids = ids[i:i+batch_size]
        
        # Generate embeddings for the batch
        embeddings = model.encode(batch_docs, show_progress_bar=False).tolist()
        
        collection.add(
            embeddings=embeddings,
            documents=batch_docs,
            ids=batch_ids
        )

    print("\n--- Data Ingestion Complete ---")
    print(f"Total documents added to collection '{COLLECTION_NAME}': {collection.count()}")

if __name__ == "__main__":
    data_ingest()
