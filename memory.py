# ==============================================================================
# REDIS MEMORY MANAGER - STATE & PERSISTENCE LAYER
# ==============================================================================

import os
import json
import logging
from datetime import datetime
import redis.asyncio as aioredis
from dotenv import load_dotenv

# Setup logging
logger = logging.getLogger("memory")

load_dotenv()

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)
REDIS_URL = os.getenv("REDIS_URL", None)  # Upstash provides rediss:// URLs

# Sanitize REDIS_HOST: strip scheme prefixes and quotes that break the connection
if REDIS_HOST:
    REDIS_HOST = REDIS_HOST.strip('"').strip("'")
    for prefix in ["https://", "http://", "rediss://", "redis://"]:
        if REDIS_HOST.startswith(prefix):
            REDIS_HOST = REDIS_HOST[len(prefix):]
    REDIS_HOST = REDIS_HOST.rstrip("/")

# Auto-detect if TLS is needed (Upstash always requires TLS on port 6380)
REDIS_USE_TLS = "upstash.io" in (REDIS_HOST or "") or REDIS_PORT == 6380

# Shared Redis pool
redis_client = None

# Fallback in-memory store if Redis is unavailable
_in_memory_store = {}
_use_in_memory = False

async def init_redis():
    """Initializes the asynchronous Redis connection pool."""
    global redis_client, _use_in_memory
    if redis_client is None and not _use_in_memory:
        logger.info(f"Connecting to Redis at {REDIS_HOST}:{REDIS_PORT} (TLS={REDIS_USE_TLS})...")
        try:
            # Support Upstash REDIS_URL (rediss://...) if provided
            if REDIS_URL:
                redis_client = aioredis.from_url(
                    REDIS_URL,
                    decode_responses=True,
                    socket_timeout=3.0,
                    socket_connect_timeout=3.0
                )
            else:
                redis_client = aioredis.Redis(
                    host=REDIS_HOST,
                    port=REDIS_PORT,
                    password=REDIS_PASSWORD,
                    decode_responses=True,
                    ssl=REDIS_USE_TLS,
                    socket_timeout=3.0,
                    socket_connect_timeout=3.0
                )
            # Test ping
            await redis_client.ping()
            logger.info("Successfully connected to Redis.")
        except Exception as e:
            logger.warning(f"Failed to connect to Redis: {e}. Falling back to in-memory storage (Not suitable for production!).")
            _use_in_memory = True
            redis_client = None

async def get_session(session_id: str) -> dict:
    """Loads a user session state from Redis. Creates a default session if not found."""
    if not redis_client and not _use_in_memory:
        await init_redis()
        
    key = f"session:{session_id}"
    
    if _use_in_memory:
        data = _in_memory_store.get(key)
        if data:
            return json.loads(data)
    else:
        data = await redis_client.get(key)
        if data:
            try:
                return json.loads(data)
            except Exception as e:
                logger.error(f"Failed to parse session data for {session_id}: {e}")
            
    # Default Session Template
    default_session = {
        "session_id": session_id,
        "preferred_language": "en",
        "consent": {
            "memory": True,
            "mood_logging": False
        },
        "turns": [],
        "rolling_summary": "",
        "active_protocol": None,  # Will hold { "name": "...", "current_state": "...", "data": {...} }
        "mood_log": []
    }
    await save_session(session_id, default_session)
    return default_session

async def save_session(session_id: str, session_data: dict, ttl_days: int = 7):
    """Saves the user session state back to Redis with a TTL."""
    if not redis_client and not _use_in_memory:
        await init_redis()
        
    key = f"session:{session_id}"
    try:
        serialized = json.dumps(session_data, default=str)
        if _use_in_memory:
            _in_memory_store[key] = serialized
        else:
            await redis_client.set(key, serialized, ex=ttl_days * 24 * 60 * 60)
    except Exception as e:
        logger.error(f"Failed to save session data for {session_id}: {e}")

async def summarize_history(turns: list, existing_summary: str, groq_client) -> str:
    """Uses Groq (8B model) to compress oldest turns into the rolling summary."""
    try:
        # Extract the oldest 4 turns (2 user-assistant pairs)
        turns_to_summarize = turns[:4]
        history_text = ""
        for t in turns_to_summarize:
            history_text += f"{t['role'].capitalize()}: {t['content']}\n"
            
        prompt = (
            "You are a memory compressor for a mental health assistant. "
            "Compress the following conversation snippets into a single, concise summary "
            "capturing key concerns, emotions, and topics discussed. "
            "Combine this with the existing summary below if provided.\n\n"
            f"Existing Summary:\n{existing_summary or 'None'}\n\n"
            f"New turns to merge:\n{history_text}\n\n"
            "Output only the updated summary under 80 words. Do not write intros or explanations."
        )
        
        response = await groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=150
        )
        
        new_summary = response.choices[0].message.content.strip()
        logger.info("Successfully compressed oldest chat turns into rolling summary.")
        return new_summary
    except Exception as e:
        logger.error(f"Failed to summarize chat history: {e}")
        return existing_summary  # Return old summary as fallback

async def manage_memory_budget(session_data: dict, groq_client) -> dict:
    """Checks token budget / turn count and compresses oldest turns if turns > 8."""
    turns = session_data.get("turns", [])
    if len(turns) > 8:
        logger.info(f"Session {session_data['session_id']} exceeded 8 turns. Triggering memory compression...")
        # Summarize oldest 4 turns
        updated_summary = await summarize_history(
            turns=turns,
            existing_summary=session_data.get("rolling_summary", ""),
            groq_client=groq_client
        )
        session_data["rolling_summary"] = updated_summary
        
        # Keep the latest turns
        session_data["turns"] = turns[4:]
        logger.info(f"Compressed session down to {len(session_data['turns'])} active turns.")
    return session_data
