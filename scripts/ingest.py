# ==============================================================================
# INGESTION SCRIPT - PINECONE VECTOR STORE LOADER
# ==============================================================================

import os
import json
import logging
from dotenv import load_dotenv
from pinecone import Pinecone, ServerlessSpec
from sentence_transformers import SentenceTransformer

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("ingestion")

# Load environment variables
load_dotenv()

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "mh-support")

# 1. Initialize SentenceTransformer (384 dimensions)
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
logger.info(f"Loading local SentenceTransformer model: {EMBEDDING_MODEL_NAME}...")
try:
    embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    logger.info("SentenceTransformer model loaded successfully.")
except Exception as e:
    logger.error(f"Failed to load embedding model: {e}")
    raise e

def create_pinecone_index(pc: Pinecone):
    """Checks if the Pinecone index exists; if not, creates a Serverless Index."""
    logger.info(f"Checking Pinecone index '{PINECONE_INDEX_NAME}'...")
    
    # Get current index list
    current_indexes = [idx.name for idx in pc.list_indexes()]
    
    if PINECONE_INDEX_NAME not in current_indexes:
        logger.info(f"Index '{PINECONE_INDEX_NAME}' not found. Creating serverless index...")
        try:
            pc.create_index(
                name=PINECONE_INDEX_NAME,
                dimension=384,  # Match all-MiniLM-L6-v2 output dimension
                metric="cosine",
                spec=ServerlessSpec(
                    cloud="aws",
                    region="us-east-1"
                )
            )
            logger.info(f"Successfully created Pinecone index: '{PINECONE_INDEX_NAME}'.")
        except Exception as e:
            logger.error(f"Failed to create Pinecone index: {e}")
            raise e
    else:
        logger.info(f"Pinecone index '{PINECONE_INDEX_NAME}' already exists.")

def load_json_corpus(file_path: str) -> list:
    """Safely loads a JSON corpus file."""
    if not os.path.exists(file_path):
        logger.warning(f"Corpus file not found: {file_path}")
        return []
    
    with open(file_path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
            logger.info(f"Loaded {len(data)} items from {file_path}.")
            return data
        except Exception as e:
            logger.error(f"Failed to parse JSON file {file_path}: {e}")
            return []

def main():
    if not PINECONE_API_KEY:
        logger.error("PINECONE_API_KEY is not set. Ingestion aborted.")
        print("\n[ERROR] PINECONE_API_KEY environment variable is missing. Set it in .env before running.\n")
        return

    # Initialize Pinecone Client
    pc = Pinecone(api_key=PINECONE_API_KEY)
    
    # Establish Index
    create_pinecone_index(pc)
    
    # Connect to Index
    index = pc.Index(PINECONE_INDEX_NAME)

    # 2. Gather documents from different domains
    documents = []
    
    # Load Psychoeducation articles
    psychoed_articles = load_json_corpus("data/psychoed/articles.json")
    for art in psychoed_articles:
        documents.append({
            "id": art["id"],
            "text": art["text"],
            "metadata": {
                "id": art["id"],
                "domain": art["domain"],
                "topic": art["topic"],
                "audience": art["audience"],
                "language": art["language"],
                "title": art["title"],
                "text": art["text"]  # Save plain text in metadata for RAG retrieval reference
            }
        })

    # Load Cultural framing articles
    cultural_articles = load_json_corpus("data/cultural/articles.json")
    for art in cultural_articles:
        documents.append({
            "id": art["id"],
            "text": art["text"],
            "metadata": {
                "id": art["id"],
                "domain": art["domain"],
                "topic": art["topic"],
                "audience": art["audience"],
                "language": art["language"],
                "title": art["title"],
                "text": art["text"]
            }
        })
        
    # Load Helpline Resources (as searchable chunks for Referral Agent)
    resources = load_json_corpus("data/resources.json")
    for res in resources:
        text_content = f"{res['name']} ({res['type']}) is contactable via {', '.join(res['modes'])} at {res['contact']}. Hours: {res['hours']}. Languages: {', '.join(res['languages'])}. Cost: {res['cost']}. Description: {res['description']}"
        documents.append({
            "id": f"resource-{res['id']}",
            "text": text_content,
            "metadata": {
                "id": f"resource-{res['id']}",
                "domain": "resource",
                "topic": "helpline",
                "audience": "general",
                "language": "both",
                "title": res["name"],
                "text": text_content
            }
        })

    if not documents:
        logger.error("No documents loaded. Ingestion aborted.")
        return

    logger.info(f"Generating embeddings for {len(documents)} document chunks...")
    
    # 3. Vectorize and Ingest in Batch
    vectors_to_upsert = []
    for doc in documents:
        try:
            # Generate embedding vector
            embedding = embedding_model.encode(doc["text"]).tolist()
            
            vectors_to_upsert.append({
                "id": doc["id"],
                "values": embedding,
                "metadata": doc["metadata"]
            })
        except Exception as e:
            logger.error(f"Failed to encode document {doc['id']}: {e}")

    # Upsert to Pinecone
    logger.info(f"Upserting {len(vectors_to_upsert)} vectors to Pinecone...")
    try:
        # Upsert in batches of 100
        batch_size = 100
        for i in range(0, len(vectors_to_upsert), batch_size):
            batch = vectors_to_upsert[i:i + batch_size]
            index.upsert(vectors=batch)
            logger.info(f"Upserted batch {i // batch_size + 1} ({len(batch)} vectors).")
        logger.info("Ingestion completed successfully!")
    except Exception as e:
        logger.error(f"Pinecone upsert failed: {e}")

if __name__ == "__main__":
    main()
