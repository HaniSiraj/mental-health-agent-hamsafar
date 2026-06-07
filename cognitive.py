# ==============================================================================
# COGNITIVE ENGINE - LANGGRAPH AGENT ORCHESTRATION & RUNTIME
# ==============================================================================

import os
import json
import logging
import asyncio
from datetime import datetime
from dotenv import load_dotenv
from groq import AsyncGroq
from pinecone import Pinecone
from sentence_transformers import SentenceTransformer

from prompts import (
    NORMALIZER_PROMPT,
    SAFETY_PROMPT,
    SUPERVISOR_PROMPT,
    PSYCHOED_PROMPT,
    REFLECTION_PROMPT,
    CULTURAL_PROMPT,
    REFERRAL_PROMPT,
    SYNTHESIS_PROMPT,
    ROMAN_URDU_TRANSLATOR
)

logger = logging.getLogger("cognitive")

load_dotenv()

# API Keys
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "mh-support")

# 1. Initialize Clients
groq_client = None
pinecone_index = None
embedding_model = None

def init_cognitive_clients():
    """Initializes Groq, Pinecone, and SentenceTransformers clients."""
    global groq_client, pinecone_index, embedding_model
    
    if not GROQ_API_KEY:
        logger.error("GROQ_API_KEY is not set in environment.")
        raise ValueError("GROQ_API_KEY is required.")
        
    groq_client = AsyncGroq(api_key=GROQ_API_KEY)
    logger.info("Asynchronous Groq client initialized.")
    
    if PINECONE_API_KEY:
        try:
            pc = Pinecone(api_key=PINECONE_API_KEY)
            pinecone_index = pc.Index(PINECONE_INDEX_NAME)
            logger.info(f"Connected to Pinecone index: '{PINECONE_INDEX_NAME}'")
        except Exception as e:
            logger.error(f"Failed to connect to Pinecone: {e}")
            pinecone_index = None
    else:
        logger.warning("PINECONE_API_KEY is not set. RAG retrieval will be disabled.")
        
    try:
        embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
        logger.info("Local SentenceTransformer all-MiniLM-L6-v2 loaded.")
    except Exception as e:
        logger.error(f"Failed to load embedding model: {e}")
        embedding_model = None

# Load CBT Exercises from json corpus
CBT_EXERCISES = {}
try:
    with open("data/cbt-protocols/exercises.json", "r", encoding="utf-8") as f:
        exercises_list = json.load(f)
        for ex in exercises_list:
            CBT_EXERCISES[ex["name"]] = ex
        logger.info(f"Loaded CBT protocols: {list(CBT_EXERCISES.keys())}")
except Exception as e:
    logger.error(f"Failed to load CBT protocols corpus: {e}")

# ----------------------------------------------------------------------------
# 2. HELPER UTILITIES
# ----------------------------------------------------------------------------

def get_query_embeddings(text: str) -> list:
    """Generates a 384-dimension vector embedding using the local sentence transformer."""
    if embedding_model is None:
        logger.warning("Embedding model not loaded. Returning dummy vector.")
        return [0.0] * 384
    return embedding_model.encode(text).tolist()

async def search_rag_context(text: str, domain: str, top_k: int = 3) -> str:
    """Queries Pinecone for semantic context filtered by domain."""
    if pinecone_index is None:
        logger.warning("Pinecone index not initialized. Skipping RAG search.")
        return "No clinical context available."
        
    try:
        vector = get_query_embeddings(text)
        query_response = pinecone_index.query(
            vector=vector,
            top_k=top_k,
            filter={"domain": {"$eq": domain}},
            include_metadata=True
        )
        
        matches = query_response.get("matches", [])
        if not matches:
            return "No specific database articles found for this topic."
            
        context_str = ""
        for match in matches:
            meta = match.get("metadata", {})
            context_str += f"Title: {meta.get('title', 'Article')}\nContent: {meta.get('text', '')}\n\n"
        return context_str.strip()
    except Exception as e:
        logger.error(f"RAG search failed for domain {domain}: {e}")
        return "Failed to fetch RAG database results."

def safe_parse_json(text: str) -> dict:
    """Robustly extracts JSON from an LLM response containing markdown blocks or prose."""
    # Find start and end of JSON boundaries
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        text = text[start:end + 1]
    try:
        return json.loads(text)
    except Exception as e:
        logger.error(f"JSON parsing error: {e} | Raw text: {text}")
        return {}

# ----------------------------------------------------------------------------
# 3. PIPELINE STAGES (NODES)
# ----------------------------------------------------------------------------

async def run_bilingual_normalizer(raw_message: str) -> dict:
    """Translates Roman Urdu or Urdu script into standard English, preserving intensity."""
    logger.info("Running Bilingual Normalizer...")
    try:
        response = await groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": NORMALIZER_PROMPT},
                {"role": "user", "content": raw_message}
            ],
            temperature=0.1,
            response_format={"type": "json_object"}
        )
        content = response.choices[0].message.content
        return safe_parse_json(content)
    except Exception as e:
        logger.error(f"Bilingual Normalizer failed: {e}")
        return {
            "detected_lang": "en",
            "normalized_text": raw_message,
            "preferred_reply_lang": "en"
        }

async def run_safety_guardian(normalized_message: str) -> dict:
    """Always-On safety check. Classifies user text into Tiers 1-5."""
    logger.info("Running Always-On Safety Guardian...")
    try:
        response = await groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": SAFETY_PROMPT},
                {"role": "user", "content": normalized_message}
            ],
            temperature=0.0,
            response_format={"type": "json_object"}
        )
        content = response.choices[0].message.content
        return safe_parse_json(content)
    except Exception as e:
        logger.error(f"Safety Guardian failed: {e}")
        return {
            "tier": 3,
            "signals": ["connection_error"],
            "reasoning": "Fallback to moderate distress on system error."
        }

async def generate_crisis_acknowledgment(normalized_message: str) -> str:
    """Generates a warm 1-sentence acknowledgment for crisis states (Tier 1/2)."""
    try:
        response = await groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "user", "content": f"Generate a single, short, compassionate sentence acknowledging the painful feelings the user just shared. Do not give advice. Do not ask any questions. Keep it under 15 words.\n\nUser distress message: {normalized_message}"}
            ],
            temperature=0.2,
            max_tokens=50
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Crisis acknowledgment generation failed: {e}")
        return "I hear how incredibly difficult things are for you right now."

async def run_supervisor(normalized_message: str, summary: str, active_turns: list) -> dict:
    """Supervisor router node. Decides which specialists to trigger (up to 2)."""
    logger.info("Running Supervisor Router...")
    
    # Construct history context
    history_str = f"History Summary: {summary or 'None'}\n\n"
    for turn in active_turns[-4:]:
        history_str += f"{turn['role'].capitalize()}: {turn['content']}\n"
        
    user_input = f"{history_str}\nCurrent user message to route: {normalized_message}"
    
    try:
        response = await groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": SUPERVISOR_PROMPT},
                {"role": "user", "content": user_input}
            ],
            temperature=0.2,
            response_format={"type": "json_object"}
        )
        content = response.choices[0].message.content
        return safe_parse_json(content)
    except Exception as e:
        logger.error(f"Supervisor Router failed: {e}")
        return {
            "agents": ["reflection"],
            "reasoning": "Fallback routing to Reflection on router error.",
            "user_intent": "vent"
        }

# ----------------------------------------------------------------------------
# 4. CBT PROTOCOL STATE MACHINE ENGINE
# ----------------------------------------------------------------------------

async def advance_cbt_protocol(session: dict, user_input: str) -> str:
    """Advances the state machine of the active CBT protocol."""
    active = session.get("active_protocol")
    if not active:
        return "No active CBT session found."
        
    p_name = active["name"]
    curr_state_str = active["current_state"] # e.g. "step_0_of_6"
    data = active.get("data", {})
    
    protocol = CBT_EXERCISES.get(p_name)
    if not protocol:
        logger.error(f"CBT protocol '{p_name}' schema missing!")
        session["active_protocol"] = None
        return "I had a system issue tracking our exercise. Let's restart if you'd like."
        
    states = protocol["states"]
    
    # 1. Parse current state number
    try:
        curr_step = int(curr_state_str.split("_")[1])
    except Exception:
        curr_step = 0
        
    # 2. Record the user's input for the CURRENT step field
    curr_field = states[str(curr_step)]["field"]
    data[curr_field] = user_input
    active["data"] = data
    
    # 3. Increment state
    next_step = curr_step + 1
    next_state_key = str(next_step)
    
    if next_state_key in states:
        # Move to next state
        active["current_state"] = f"step_{next_step}_of_{protocol['steps']}"
        session["active_protocol"] = active
        return states[next_state_key]["prompt"]
    else:
        # Protocol Completed! Summarize results
        summary_prompt = (
            f"Write a warm, supportive closing summary (~80 words) for the user who just completed their CBT {protocol['title']} exercise. "
            f"Here is the collected data from their exercise:\n"
            f"{json.dumps(data, indent=2)}\n\n"
            "Praise their hard work, highlight the reframed thought if present, and give one gentle closing encouragement. Output only the summary."
        )
        
        try:
            response = await groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": summary_prompt}],
                temperature=0.3
            )
            closing_text = response.choices[0].message.content.strip()
        except Exception:
            closing_text = f"Wonderful work completing this {protocol['title']} exercise! You took a very positive step today."
            
        # Reset active protocol
        session["active_protocol"] = None
        return closing_text

# ----------------------------------------------------------------------------
# 5. INTEGRATED COGNITIVE PIPELINE RUNNER
# ----------------------------------------------------------------------------

async def run_cognitive_pipeline(session_id: str, raw_message: str, session: dict) -> tuple:
    """Orchestrates the entire Multi-Agent routing, safety, and synthesis pipeline."""
    if groq_client is None:
        init_cognitive_clients()

    cognitive_trace = {
        "timestamp": datetime.utcnow().isoformat(),
        "input_message": raw_message,
        "normalization": {},
        "safety": {},
        "routing": {},
        "specialists": {},
        "synthesis": {}
    }

    # -- STAGE 1: Bilingual Normalization --
    normalizer_res = await run_bilingual_normalizer(raw_message)
    cognitive_trace["normalization"] = normalizer_res
    normalized_text = normalizer_res.get("normalized_text", raw_message)
    preferred_lang = normalizer_res.get("preferred_reply_lang", "en")
    
    # Save user preferred language
    session["preferred_language"] = preferred_lang

    # -- STAGE 2: Always-On Safety Guardian --
    safety_res = await run_safety_guardian(normalized_text)
    cognitive_trace["safety"] = safety_res
    tier = safety_res.get("tier", 3)

    # -- TIER 1 & 2: Emergency Short-Circuit --
    if tier in [1, 2]:
        logger.warning(f"Safety Guardian triggered Tier {tier} escalation!")
        ack_sentence = await generate_crisis_acknowledgment(normalized_text)
        
        # Load locked templates
        if tier == 1:
            locked_response = (
                f"{ack_sentence}\n\n"
                "It sounds like you are going through an incredibly difficult time right now, but please know that you do not have to carry this alone. There are professional helplines in Pakistan with clinical teams ready to listen and support you:\n\n"
                "• Umang Pakistan: Call or WhatsApp 0311-7786264 (Free, 24/7, Urdu/English support)\n"
                "• Taskeen Helpline: Call 0316-8275336 (Free, 11 AM - 11 PM Mon-Sat)\n"
                "• Rozan Helpline: Call 0800-22444 (Toll-Free, 10 AM - 6 PM Mon-Sat)\n\n"
                "Please reach out to one of these services, or contact a family member, friend, or doctor you trust. "
                "I am here and I want to make sure you are safe. If you feel comfortable, please keep chatting with me, or take a moment to reach out to one of the helplines above. Your life is valuable."
            )
        else: # Tier 2
            locked_response = (
                f"{ack_sentence}\n\n"
                "Let's take a deep breath together to ground ourselves in this moment. If you can, try to focus on your physical surroundings:\n"
                "- Name 3 things you can see around you.\n"
                "- Name 2 things you can physically feel (like your feet on the floor).\n"
                "- Name 1 sound you can hear.\n\n"
                "While we take this pause, please consider reaching out to these professional networks in Pakistan who can guide you through this difficult moment:\n\n"
                "• Taskeen Helpline: 0316-8275336 (For emotional support & referrals)\n"
                "• Karwan-e-Hayat: 021-32202008 (For professional psychiatric and therapeutic care)\n"
                "• Pakistan Association for Mental Health: 021-35384152 (For outpatient clinical consultations)\n\n"
                "Please remember that I am an AI psychoeducation assistant and cannot provide clinical diagnosis or treatment. Talking to a professional is the best way to get the care you deserve. I am here to continue supporting you in a safe space."
            )
            
        cognitive_trace["routing"] = {"action": f"Emergency locked Tier {tier} response"}
        
        # Translate to Roman Urdu if preferred language matches
        if preferred_lang == "ur":
            try:
                trans_res = await groq_client.chat.completions.create(
                    model="llama-3.1-8b-instant",
                    messages=[
                        {"role": "system", "content": ROMAN_URDU_TRANSLATOR},
                        {"role": "user", "content": locked_response}
                    ],
                    temperature=0.2
                )
                final_response = trans_res.choices[0].message.content.strip()
            except Exception:
                final_response = locked_response
        else:
            final_response = locked_response
            
        return final_response, cognitive_trace, session

    # -- TIER 5: Scope Guard --
    if tier == 5:
        cognitive_trace["routing"] = {"action": "Polite redirect (Tier 5 out-of-scope)"}
        out_of_scope_reply = (
            "I'm here to support your emotional well-being and provide self-help strategies, but medical prescriptions, "
            "legal counseling, and financial decisions are out of my scope. "
            "If you are feeling stressed or anxious due to these difficulties, we can absolutely discuss grounding tips or CBT techniques. "
            "Otherwise, I encourage you to contact a licensed professional, family elder, or financial advisor in your area."
        )
        if preferred_lang == "ur":
            try:
                trans_res = await groq_client.chat.completions.create(
                    model="llama-3.1-8b-instant",
                    messages=[
                        {"role": "system", "content": ROMAN_URDU_TRANSLATOR},
                        {"role": "user", "content": out_of_scope_reply}
                    ],
                    temperature=0.2
                )
                final_response = trans_res.choices[0].message.content.strip()
            except Exception:
                final_response = out_of_scope_reply
        else:
            final_response = out_of_scope_reply
            
        return final_response, cognitive_trace, session

    # -- TIER 3 & 4: Cognitive Brain Orchestration --
    active_protocol = session.get("active_protocol")
    
    # SAFEGUARD OVERRIDE: If mid-CBT exercise, supervisor is bypassed completely!
    if active_protocol:
        logger.info(f"User is mid-CBT protocol: '{active_protocol['name']}'. Bypassing supervisor.")
        cognitive_trace["routing"] = {
            "active_cbt_override": True,
            "cbt_protocol": active_protocol["name"],
            "current_state": active_protocol["current_state"]
        }
        
        cbt_output = await advance_cbt_protocol(session, normalized_text)
        cognitive_trace["specialists"] = {"cbt": cbt_output}
        
        # Synthesis LLM simply formats the CBT question with correct language
        synthesis_prompt = (
            f"The user is currently going through a structured mental health CBT exercise: {active_protocol['name']}.\n"
            f"The CBT specialist generated this next prompt: \"{cbt_output}\"\n\n"
            f"Format this response into a warm, natural message of ~60 words. "
            f"If the preferred language is 'ur', translate it into warm Roman Urdu. Otherwise, keep it in English. "
            f"Output only the final text."
        )
        
        try:
            response = await groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": synthesis_prompt}],
                temperature=0.2
            )
            final_response = response.choices[0].message.content.strip()
        except Exception:
            final_response = cbt_output
            
        # Append standard disclaimer footer
        final_response += "\n\n---\n*Disclaimer: I am an AI psychoeducation prototype, not a clinic. For emergencies, contact Umang at 0311-7786264.*"
        
        return final_response, cognitive_trace, session

    # -- STAGE 3: Supervisor Routing --
    supervisor_res = await run_supervisor(
        normalized_message=normalized_text,
        summary=session.get("rolling_summary", ""),
        active_turns=session.get("turns", [])
    )
    cognitive_trace["routing"] = supervisor_res
    selected_agents = supervisor_res.get("agents", ["reflection"])
    
    # Enforce upper bound of 2 specialists to prevent context flooding
    selected_agents = selected_agents[:2]

    # -- STAGE 4: Specialist Parallel Execution (Fan-Out) --
    specialist_tasks = []
    
    for agent in selected_agents:
        if agent == "psychoed":
            async def run_psychoed():
                context = await search_rag_context(normalized_text, "psychoed")
                res = await groq_client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[
                        {"role": "system", "content": PSYCHOED_PROMPT.format(context=context)},
                        {"role": "user", "content": normalized_text}
                    ],
                    temperature=0.4
                )
                return "psychoed", res.choices[0].message.content.strip()
            specialist_tasks.append(run_psychoed())
            
        elif agent == "reflection":
            async def run_reflection():
                res = await groq_client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[
                        {"role": "system", "content": REFLECTION_PROMPT},
                        {"role": "user", "content": normalized_text}
                    ],
                    temperature=0.5
                )
                return "reflection", res.choices[0].message.content.strip()
            specialist_tasks.append(run_reflection())
            
        elif agent == "cultural":
            async def run_cultural():
                context = await search_rag_context(normalized_text, "cultural")
                res = await groq_client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[
                        {"role": "system", "content": CULTURAL_PROMPT.format(context=context)},
                        {"role": "user", "content": normalized_text}
                    ],
                    temperature=0.3
                )
                return "cultural", res.choices[0].message.content.strip()
            specialist_tasks.append(run_cultural())
            
        elif agent == "referral":
            async def run_referral():
                context = await search_rag_context(normalized_text, "resource")
                res = await groq_client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[
                        {"role": "system", "content": REFERRAL_PROMPT.format(context=context)},
                        {"role": "user", "content": normalized_text}
                    ],
                    temperature=0.2
                )
                return "referral", res.choices[0].message.content.strip()
            specialist_tasks.append(run_referral())
            
        elif agent == "cbt":
            # If supervisor selects CBT but no protocol is active, we suggest initiating one
            async def run_cbt_suggestion():
                return "cbt", "I would be happy to walk you through a structured Thought Record exercise step-by-step to help analyze and reframe this automatic thought. Would you like to start that?"
            specialist_tasks.append(run_cbt_suggestion())

    # Wait for all parallel specialist tasks to complete
    specialist_results = await asyncio.gather(*specialist_tasks)
    specialist_outputs_str = ""
    
    for agent_name, output in specialist_results:
        cognitive_trace["specialists"][agent_name] = output
        specialist_outputs_str += f"### {agent_name.capitalize()} Specialist:\n{output}\n\n"

    # -- STAGE 5: Synthesis / Merge (Fan-In) --
    logger.info("Running Synthesis Merge...")
    try:
        response = await groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": SYNTHESIS_PROMPT.format(
                    user_message=normalized_text,
                    preferred_lang=preferred_lang,
                    specialist_outputs=specialist_outputs_str
                )},
                {"role": "user", "content": "Compose the final, single synthesized response now."}
            ],
            temperature=0.4
        )
        final_response = response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Synthesis Merge failed: {e}")
        # Simplest fallback: return reflection or first specialist output
        final_response = list(cognitive_trace["specialists"].values())[0]

    # Append standard disclaimer footer
    final_response += "\n\n---\n*Disclaimer: I am an AI psychoeducation prototype, not a clinic. For emergencies, contact Umang at 0311-7786264.*"
    cognitive_trace["synthesis"] = {"response_length_chars": len(final_response)}

    return final_response, cognitive_trace, session
