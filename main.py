# ==============================================================================
# FASTAPI APPLICATION GATEWAY & ROUTES
# ==============================================================================

import os
import logging
from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

from memory import init_redis, get_session, save_session, manage_memory_budget
from cognitive import init_cognitive_clients, run_cognitive_pipeline, groq_client

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("main")

app = FastAPI(
    title="Multi-Agent Mental Health Support System",
    description="A production-grade stateful agentic AI backend with custom safety filters and CBT state machines.",
    version="1.0.0"
)

# Enable CORS for local and cross-origin frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------------------------------------------------------------
# 1. REQUEST & RESPONSE SCHEMAS
# ----------------------------------------------------------------------------

class ChatRequest(BaseModel):
    session_id: str = Field(..., description="Unique session identifier (UUID or phone number)")
    message: str = Field(..., description="Raw text input message from the user")

class ChatResponse(BaseModel):
    reply: str = Field(..., description="Synthesized counseling reply")
    cognitive_trace: Dict[str, Any] = Field(..., description="Internal pipeline execution details")

class ConsentRequest(BaseModel):
    memory: bool = Field(True, description="Consent to persist chat turns")
    mood_logging: bool = Field(False, description="Consent to log mood scores")

class MoodLogRequest(BaseModel):
    score: int = Field(..., ge=1, le=10, description="Mood score from 1 to 10")
    note: Optional[str] = Field(None, description="Optional brief context note")

# ----------------------------------------------------------------------------
# 2. LIFECYCLE HOOKS
# ----------------------------------------------------------------------------

@app.on_event("startup")
async def startup_event():
    """Validates connectivity to Redis, Pinecone, and Groq during startup."""
    logger.info("Initializing system backing integrations...")
    try:
        await init_redis()
        init_cognitive_clients()
        logger.info("All backend systems connected successfully.")
    except Exception as e:
        logger.critical(f"System startup failure: {e}")
        # We don't crash, allowing developer to adjust settings while container runs
        pass

# ----------------------------------------------------------------------------
# 3. ENDPOINTS
# ----------------------------------------------------------------------------

@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(payload: ChatRequest):
    """Processes chat input through bilingual translation, safety filtering, multi-agent RAG, and synthesis."""
    session_id = payload.session_id
    message_text = payload.message.strip()
    
    if not message_text:
        raise HTTPException(status_code=400, detail="Message content cannot be empty.")
        
    try:
        # 1. Load session from Redis
        session = await get_session(session_id)
        
        # 2. INTERCEPT: Check if user is starting a CBT protocol explicitly
        lower_msg = message_text.lower()
        if "start thought record" in lower_msg or "thought record" in lower_msg and not session.get("active_protocol"):
            session["active_protocol"] = {
                "name": "thought_record",
                "current_state": "step_0_of_6",
                "data": {}
            }
            logger.info(f"Initialized CBT 'thought_record' protocol for session: {session_id}")
            
        elif "worry postponement" in lower_msg and not session.get("active_protocol"):
            session["active_protocol"] = {
                "name": "worry_postponement",
                "current_state": "step_0_of_2",
                "data": {}
            }
            logger.info(f"Initialized CBT 'worry_postponement' protocol for session: {session_id}")
            
        elif "behavioral activation" in lower_msg or "activity scheduling" in lower_msg and not session.get("active_protocol"):
            session["active_protocol"] = {
                "name": "activity_scheduling",
                "current_state": "step_0_of_4",
                "data": {}
            }
            logger.info(f"Initialized CBT 'activity_scheduling' protocol for session: {session_id}")

        # 3. Execute the Cognitive Pipeline
        reply, trace, updated_session = await run_cognitive_pipeline(
            session_id=session_id,
            raw_message=message_text,
            session=session
        )
        
        # 4. Save Chat Turn in Memory (Only if user consented to memory)
        if updated_session.get("consent", {}).get("memory", True):
            updated_session["turns"].append({
                "role": "user",
                "content": message_text,
                "timestamp": trace["timestamp"]
            })
            updated_session["turns"].append({
                "role": "assistant",
                "content": reply,
                "timestamp": trace["timestamp"]
            })
            
            # 5. Manage history memory token budgets (compression)
            updated_session = await manage_memory_budget(updated_session, groq_client)
            
        # 6. Save updated session to Redis
        await save_session(session_id, updated_session)
        
        return ChatResponse(reply=reply, cognitive_trace=trace)
        
    except Exception as e:
        logger.error(f"Error handling chat in session {session_id}: {e}")
        # Standard production recovery output
        fallback_reply = (
            "I'm sorry, I encountered a brief technical delay in my reasoning core. "
            "If you are in distress, please contact Umang Pakistan at 0311-7786264 (Free, 24/7). "
            "Otherwise, please try sending your message again. I am here for you."
        )
        return ChatResponse(
            reply=fallback_reply,
            cognitive_trace={"error": str(e), "status": "failed"}
        )

@app.get("/api/session/{session_id}")
async def get_session_endpoint(session_id: str):
    """Retrieves the full active state and history of a session."""
    try:
        session = await get_session(session_id)
        return session
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/consent/{session_id}")
async def update_consent_endpoint(session_id: str, consent: ConsentRequest):
    """Updates user consent settings for tracking and profile logging."""
    try:
        session = await get_session(session_id)
        session["consent"] = consent.dict()
        await save_session(session_id, session)
        return {"status": "success", "consent": session["consent"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/log_mood/{session_id}")
async def log_mood_endpoint(session_id: str, payload: MoodLogRequest):
    """Appends a mood rating score to the user's longitudinal timeline (requires consent)."""
    try:
        session = await get_session(session_id)
        if not session.get("consent", {}).get("mood_logging", False):
            raise HTTPException(
                status_code=403, 
                detail="User has not consented to mood logging. Enable consent in profile."
            )
            
        session["mood_log"].append({
            "timestamp": logger.name, # Use actual time in production
            "score": payload.score,
            "note": payload.note
        })
        await save_session(session_id, session)
        return {"status": "success", "mood_log": session["mood_log"]}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/reset/{session_id}")
async def reset_session_endpoint(session_id: str):
    """Resets all session parameters and clears chat logs."""
    try:
        key = f"session:{session_id}"
        await init_redis()
        # Delete from Redis
        await init_redis()
        await init_redis()
        import redis.asyncio as aioredis
        if await get_session(session_id):
            await redis_client.delete(key)
        return {"status": "success", "message": f"Session {session_id} successfully cleared."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ----------------------------------------------------------------------------
# 4. STATIC FILE SERVING FOR PREMIUM WEB UI
# ----------------------------------------------------------------------------
# Mount the web/ folder to serve static frontend (index.html, styles.css, app.js)
web_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)), "web")
if os.path.exists(web_dir):
    app.mount("/", StaticFiles(directory=web_dir, html=True), name="static")
    logger.info("Served static Web UI folder under root directory '/'.")
else:
    logger.warning("Web folder not found. Root directory static serving disabled.")
