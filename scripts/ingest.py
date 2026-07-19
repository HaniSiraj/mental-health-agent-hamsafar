# ==============================================================================
# UPGRADED INGESTION SCRIPT - JSON + PDF + TXT SUPPORT WITH CHUNKING
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

load_dotenv()

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "mh-support")

# Load embedding model
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
logger.info(f"Loading SentenceTransformer model: {EMBEDDING_MODEL_NAME}...")
embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME)
logger.info("SentenceTransformer model loaded successfully.")


# ------------------------------------------------------------------------------
# TEXT CHUNKING UTILITY
# ------------------------------------------------------------------------------

def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list:
    """
    Splits long text into overlapping chunks of ~chunk_size words.
    Overlap ensures context isn't lost at chunk boundaries.
    """
    words = text.split()
    if len(words) <= chunk_size:
        return [text]
    
    chunks = []
    start = 0
    while start < len(words):
        end = start + chunk_size
        chunk = " ".join(words[start:end])
        chunks.append(chunk)
        start = end - overlap  # Overlap for continuity
    
    return chunks


# ------------------------------------------------------------------------------
# FILE PARSERS
# ------------------------------------------------------------------------------

def parse_pdf(file_path: str) -> str:
    """Extracts all text from a PDF file."""
    try:
        from PyPDF2 import PdfReader
        reader = PdfReader(file_path)
        text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        return text.strip()
    except ImportError:
        logger.error("PyPDF2 not installed. Run: pip install PyPDF2")
        return ""
    except Exception as e:
        logger.error(f"Failed to parse PDF {file_path}: {e}")
        return ""


def parse_txt(file_path: str) -> str:
    """Reads a plain text file."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception as e:
        logger.error(f"Failed to read TXT {file_path}: {e}")
        return ""


# ------------------------------------------------------------------------------
# DOCUMENT LOADERS
# ------------------------------------------------------------------------------

def load_json_corpus(file_path: str) -> list:
    """Loads existing JSON articles (same as before)."""
    if not os.path.exists(file_path):
        logger.warning(f"Corpus file not found: {file_path}")
        return []
    with open(file_path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
            logger.info(f"Loaded {len(data)} items from {file_path}.")
            return data
        except Exception as e:
            logger.error(f"Failed to parse JSON {file_path}: {e}")
            return []


def load_files_from_folder(folder_path: str, domain: str) -> list:
    """
    Scans a folder for PDF and TXT files, extracts text, chunks it,
    and returns document dicts ready for embedding.
    """
    documents = []
    if not os.path.exists(folder_path):
        return documents
    
    for filename in os.listdir(folder_path):
        file_path = os.path.join(folder_path, filename)
        
        # Skip JSON files (handled separately by load_json_corpus)
        if filename.endswith(".json"):
            continue
        
        # Extract text based on file type
        raw_text = ""
        if filename.endswith(".pdf"):
            raw_text = parse_pdf(file_path)
        elif filename.endswith(".txt"):
            raw_text = parse_txt(file_path)
        else:
            continue  # Skip unsupported formats
        
        if not raw_text:
            logger.warning(f"No text extracted from {filename}, skipping.")
            continue
        
        # Chunk the text
        title = os.path.splitext(filename)[0].replace("_", " ").replace("-", " ").title()
        chunks = chunk_text(raw_text, chunk_size=500, overlap=50)
        logger.info(f"Chunked '{filename}' into {len(chunks)} pieces.")
        
        for i, chunk in enumerate(chunks):
            doc_id = f"{domain}-{os.path.splitext(filename)[0]}-chunk{i:03d}"
            documents.append({
                "id": doc_id,
                "text": chunk,
                "metadata": {
                    "id": doc_id,
                    "domain": domain,
                    "topic": "general",
                    "audience": "general",
                    "language": "en",
                    "title": f"{title} (Part {i+1})",
                    "text": chunk,
                    "source_file": filename
                }
            })
    
    return documents


# ------------------------------------------------------------------------------
# MAIN INGESTION
# ------------------------------------------------------------------------------

def main():
    if not PINECONE_API_KEY:
        logger.error("PINECONE_API_KEY is not set. Ingestion aborted.")
        return

    pc = Pinecone(api_key=PINECONE_API_KEY)
    
    # Create index if needed
    current_indexes = [idx.name for idx in pc.list_indexes()]
    if PINECONE_INDEX_NAME not in current_indexes:
        logger.info(f"Creating Pinecone index '{PINECONE_INDEX_NAME}'...")
        pc.create_index(
            name=PINECONE_INDEX_NAME,
            dimension=384,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1")
        )
    
    index = pc.Index(PINECONE_INDEX_NAME)
    documents = []

    # --- 1. Psychoeducation: JSON + PDFs/TXTs ---
    psychoed_articles = load_json_corpus("data/psychoed/articles.json")
    for art in psychoed_articles:
        documents.append({
            "id": art["id"],
            "text": art["text"],
            "metadata": {
                "id": art["id"], "domain": art["domain"], "topic": art["topic"],
                "audience": art["audience"], "language": art["language"],
                "title": art["title"], "text": art["text"]
            }
        })
    # Also scan for PDFs/TXTs in the psychoed folder
    documents.extend(load_files_from_folder("data/psychoed", "psychoed"))

    # --- 2. Cultural: JSON + PDFs/TXTs ---
    cultural_articles = load_json_corpus("data/cultural/articles.json")
    for art in cultural_articles:
        documents.append({
            "id": art["id"],
            "text": art["text"],
            "metadata": {
                "id": art["id"], "domain": art["domain"], "topic": art["topic"],
                "audience": art["audience"], "language": art["language"],
                "title": art["title"], "text": art["text"]
            }
        })
    documents.extend(load_files_from_folder("data/cultural", "cultural"))

    # --- 3. Resources ---
    resources = load_json_corpus("data/resources.json")
    for res in resources:
        text_content = (
            f"{res['name']} ({res['type']}) is contactable via {', '.join(res['modes'])} "
            f"at {res['contact']}. Hours: {res['hours']}. "
            f"Languages: {', '.join(res['languages'])}. Cost: {res['cost']}. "
            f"Description: {res['description']}"
        )
        documents.append({
            "id": f"resource-{res['id']}",
            "text": text_content,
            "metadata": {
                "id": f"resource-{res['id']}", "domain": "resource",
                "topic": "helpline", "audience": "general",
                "language": "both", "title": res["name"], "text": text_content
            }
        })

    if not documents:
        logger.error("No documents loaded. Ingestion aborted.")
        return

    # --- 4. Embed and Upsert ---
    logger.info(f"Generating embeddings for {len(documents)} document chunks...")
    vectors = []
    for doc in documents:
        try:
            embedding = embedding_model.encode(doc["text"]).tolist()
            vectors.append({
                "id": doc["id"],
                "values": embedding,
                "metadata": doc["metadata"]
            })
        except Exception as e:
            logger.error(f"Failed to encode {doc['id']}: {e}")

    logger.info(f"Upserting {len(vectors)} vectors to Pinecone...")
    batch_size = 100
    for i in range(0, len(vectors), batch_size):
        batch = vectors[i:i + batch_size]
        index.upsert(vectors=batch)
        logger.info(f"Upserted batch {i // batch_size + 1} ({len(batch)} vectors).")
    
    logger.info(f"Ingestion completed! Total vectors: {len(vectors)}")


if __name__ == "__main__":
    main()