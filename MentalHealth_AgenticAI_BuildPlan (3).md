# Multi-Agent Mental Health Support System — Agentic AI Course Project

A culturally-aware, safety-first multi-agent system for Pakistan. Built on n8n + Groq + Pinecone + Redis. Designed to demonstrate core agentic AI patterns: multi-agent orchestration, always-on guardian agents, ReAct tool use, stateful multi-turn protocols, RAG with metadata filtering, and memory.

**Scope (memorize this line):** This is a *self-help and psychoeducation prototype with crisis escalation*, built as a course project to demonstrate agentic AI techniques. It is not a therapist, does not diagnose, does not discuss medication, and is evaluated on a test set rather than deployed to real users.

Timeline: 6 weeks core, +2 weeks optional polish. Three team members.

---

## What you're actually demonstrating (the agentic AI angle)

Your report should foreground these patterns — they're what an Agentic AI examiner will grade on:

1. **Supervisor–specialist orchestration** — router LLM dispatches to specialist sub-agents.
2. **Always-on guardian agent (Safety Agent)** — runs *before* the supervisor on every turn; can override and short-circuit the whole pipeline. This is the project's signature pattern.
3. **ReAct-style tool use** — agents reason, decide on tools, observe results, continue. Native function calling via Groq.
4. **Stateful multi-turn protocols** — CBT exercises modeled as state machines the agent walks the user through over several turns.
5. **Persistent memory with summarization** — Redis-backed session state, with token-budget-aware compression.
6. **RAG with metadata filtering** — different agents query the same vector store with different filters.
7. **Bilingual normalization pre-agent** — Roman Urdu → English pass before the main pipeline.

These are seven discrete agentic patterns. That's what the report sells.

---

## Architecture overview

```
User msg ──► [Normalizer]  ──► [Safety Agent (always-on)] ──► Tier?
                                                                │
                  ┌────────── Tier 1/2 ──────────────────────────┤
                  │           (locked crisis response)            │
                  │                                               │
                  │                                          Tier 3/4
                  │                                               │
                  │                                               ▼
                  │                                     [Supervisor / Router]
                  │                                               │
                  │              ┌─────────┬────────────┬─────────┼─────────┐
                  │              ▼         ▼            ▼         ▼         ▼
                  │      Psychoed   CBT Coach    Reflection   Resource   Cultural
                  │       Agent      Agent         Agent      Referral   Framing
                  │              │         │            │         │         │
                  │              └─────────┴──────┬─────┴─────────┴─────────┘
                  │                               │
                  │                               ▼
                  │                        [Tool Layer]
                  │                  resource_lookup, mood_log,
                  │                  exercise_state, web_search
                  │                               │
                  └─────────────►  [Response synthesis + safety footer]
                                                  │
                                                  ▼
                                        Redis memory write
                                                  │
                                                  ▼
                                            User reply
```

Every component is an n8n sub-workflow or HTTP request to Groq. The Safety Agent uses a small/fast model (LLaMA-3.1-8B) so it's cheap on every turn. The specialists use the larger model (LLaMA-3.3-70B) since they generate the user-facing text.

---

## Week 1 — Setup, safety taxonomy, mini-corpus

### 1.1 Accounts and infra

- **Groq Cloud** — free tier is enough.
- **Pinecone** Starter tier *or* self-host **Qdrant** in Docker (Qdrant is fine for the scale you need).
- **Redis Cloud** free 30 MB tier.
- **Hugging Face** for the embedding model.
- **Twilio Sandbox** for WhatsApp (free for testing).
- **n8n** self-hosted via Docker:
  ```bash
  docker run -d --name n8n -p 5678:5678 \
    -v n8n_data:/home/node/.n8n n8nio/n8n
  ```

### 1.2 Repo layout

```
mh-support/
├── docs/                    # report, diagrams
├── n8n/                     # exported workflow JSONs
├── data/
│   ├── psychoed/            # ~30 short articles
│   ├── cbt-protocols/       # exercise scripts
│   └── resources.json       # crisis resources
├── safety/
│   ├── taxonomy.md
│   ├── crisis-response.md   # LOCKED Tier 1/2 templates
│   └── safety-tests.jsonl   # adversarial test set
├── prompts/                 # one .md per agent
├── scripts/
│   ├── ingest.py
│   └── eval.py
└── README.md
```

### 1.3 Safety taxonomy (Day 1 task)

Define every category and the exact response policy. Five tiers:

| Tier | Trigger | Response policy |
|---|---|---|
| **1 — Acute** | Active suicidal ideation/plan; self-harm in progress; imminent harm to others | Locked template: warm acknowledgment + verified resources + stay-present message. **LLM never freely generates Tier 1 content.** |
| **2 — High risk** | Recent self-harm; disclosed abuse; severe distress; severe-illness signals (psychosis, mania, severe ED); substance crisis | Locked template + strong referral + brief stabilization (grounding) |
| **3 — Moderate distress** | Anxiety, low mood, stress, relationship/family conflict, work/study burnout | Normal multi-agent flow |
| **4 — Psychoeducation** | "What is anxiety?" "Explain CBT" "Why can't I sleep?" | Psychoed Agent |
| **5 — Out of scope** | Medical, legal, financial questions; general chitchat | Polite scope-guard with redirect |

The Safety Agent's only job is to classify into 1–5. The response logic for each tier is fixed code, not LLM-generated.

**Why this matters for the report:** standard chatbots fail by letting one LLM do everything. Your contribution is structurally separating *risk classification* from *response generation*, so safety can't be prompt-injected away.

### 1.4 Crisis resource directory (verify, do not assume)

Build `data/resources.json` with 6–10 Pakistani resources. **Visit each website and verify the contact info yourself — do not rely on what an LLM thinks the helpline number is.** Organizations to verify:

- Umang Pakistan
- Taskeen Health Initiative
- Karwan-e-Hayat (Karachi)
- Rozan
- Therapy Works directory
- Pakistan Association for Mental Health
- Sehat Kahani / telehealth options

```json
{
  "id": "umang",
  "name": "Umang Pakistan",
  "type": "peer_support",
  "modes": ["whatsapp", "phone"],
  "hours": "...",
  "language": ["ur", "en"],
  "cost": "free",
  "verified_url": "https://...",
  "verified_on": "2026-..."
}
```

### 1.5 Mini-corpus for RAG

Keep it small and focused. Quality over quantity for a course project:

- **Psychoeducation** (~30 short articles): anxiety, depression (mild/moderate), stress, sleep, panic, grief, burnout, family conflict, exam stress, work pressure. Adapt from WHO's "Doing What Matters in Times of Stress" (open access, has Urdu version) and NHS UK mental health pages. Rewrite in plain Pakistani English; don't paste verbatim.
- **Cultural framings** (~10 short pieces): Islamic perspectives on mental wellbeing (sabr, tawakkul, du'a as coping — *not* as substitute for help), family dynamics in joint-family contexts, gender-specific stressors, navigating stigma.
- **CBT protocols** (7 exercises — see Week 4).

Each chunk gets metadata:

```json
{
  "id": "psychoed-anxiety-01",
  "domain": "psychoed",
  "topic": "anxiety",
  "audience": "general",
  "language": "en",
  "text": "..."
}
```

Domain filters: `psychoed`, `cbt`, `cultural`, `resource`. Each agent queries with a different filter (covered in Week 3).

---

## Week 2 — Baseline single-agent RAG with safety layer

Build the simplest end-to-end version. This becomes your baseline comparison in evaluation.

### 2.1 Workflow

n8n nodes, in order:

1. **Webhook (POST /chat)** — `{session_id, message}`.
2. **Normalizer (HTTP → Groq 8B)** — detect language; if Roman Urdu, translate to English (keep the original for the reply). Output: `{lang, normalized}`.
3. **Safety Agent (HTTP → Groq 8B, JSON mode)** — classify into Tier 1–5.
4. **Switch node** — if Tier 1 or 2, route to Crisis Flow (locked template + resources). If Tier 5, route to Scope Guard. Else continue.
5. **Embed query** (HTTP → BGE on Hugging Face Inference Endpoint).
6. **Pinecone query** — top_k=5, no filter yet.
7. **Function node** — build prompt with retrieved context.
8. **Groq 70B call** — generate response, temperature 0.4 (warmer than legal but still controlled).
9. **Append safety footer** — disclaimer + one helpline reference, always.
10. **Respond to Webhook.**

### 2.2 The Safety Agent prompt (this is the critical asset)

```
You classify mental health support messages into risk tiers. Output ONLY
JSON: { "tier": 1|2|3|4|5, "signals": [...], "reasoning": "..." }

Tier 1: Active suicidal thoughts, plan, intent, or active self-harm.
        Imminent harm to self or others.
Tier 2: Recent (past 24h) self-harm; disclosed ongoing abuse;
        severe distress (hopelessness, severe panic, dissociation);
        signals of psychosis, mania, or severe eating disorder;
        substance use crisis.
Tier 3: Moderate distress: anxiety, low mood, stress, conflict,
        burnout, sleep problems.
Tier 4: Psychoeducation question (no personal distress expressed).
Tier 5: Out of scope: medical, legal, financial, or unrelated topics.

When uncertain between two tiers, choose the HIGHER risk tier.
False positives (over-escalation) are acceptable. False negatives are not.

Output JSON only. No prose.
```

Two things to note: explicit asymmetry (over-escalate when uncertain) and JSON-only output for clean routing.

### 2.3 The locked Tier 1 response

Write this carefully. Then lock it. The LLM never re-writes it. Pseudocode:

```
ack = groq(model="llama-3.3-70b",
           prompt="In one short, warm sentence acknowledge what
                   the user just shared. Do not give advice. Do not
                   ask questions. Do not use clinical terms.",
           user_message=normalized)

reply = ack + "\n\n" + LOCKED_RESOURCE_BLOCK + "\n\n" + STAY_PRESENT_MESSAGE
```

`LOCKED_RESOURCE_BLOCK` is plain text from `data/resources.json` with 2–3 verified options. `STAY_PRESENT_MESSAGE` is a fixed line inviting the user to keep talking or to reach out to a person they trust. Do not include questions like "what's your plan?" or assessment scales.

### 2.4 Acceptance for Week 2

- 10 test inputs (mix of all 5 tiers) routed correctly.
- p95 latency ≤ 4s.
- Tier 1 responses contain verified resources and warm acknowledgment.
- Safety footer present on every response.

---

## Week 3 — Multi-agent architecture

Now the project becomes "agentic AI" rather than "RAG with a safety layer."

### 3.1 Agent roster

| Agent | Model | RAG filter | Purpose |
|---|---|---|---|
| **Safety Agent** | 8B | none | Tier classification (Week 2) |
| **Supervisor** | 70B | none | Routes Tier-3 traffic to specialists |
| **Psychoeducation Agent** | 70B | `domain=psychoed` | Normalizes, explains, validates feelings |
| **CBT Coaching Agent** | 70B | `domain=cbt` | Walks user through structured exercise |
| **Reflection Agent** | 70B | none | Open-ended Rogerian-style listening |
| **Resource Referral Agent** | 70B | `domain=resource` | Surfaces helplines, therapists, services |
| **Cultural Framing Agent** | 70B | `domain=cultural` | Religious/family/cultural perspective on user's situation |

### 3.2 Supervisor prompt

```
You are the supervisor of a mental health support system. The user message
has already passed safety checks (Tier 3). Pick the most helpful specialist(s):

- psychoed:   explanation, validation, "is this normal?"
- cbt:        user wants a structured exercise OR is stuck in a thought pattern
- reflection: user wants to be heard / vent / process
- referral:   user is asking about therapists, services, helplines
- cultural:   user mentions religion, family, marriage, joint-family dynamics

You may pick 1 or 2 agents. Return JSON only:
{
  "agents": ["..."],
  "reasoning": "...",
  "user_intent": "vent | learn | practice | seek_help | get_perspective"
}
```

### 3.3 Implementing in n8n

Pattern: each specialist is its own sub-workflow with an internal webhook. The supervisor's response triggers a fan-out (HTTP calls to chosen sub-workflows in parallel), then a synthesis LLM call that produces the final reply.

The synthesis prompt is short:

```
The user said: {user_message}
Specialist outputs:
- Psychoed agent: {output_1}
- CBT agent: {output_2}

Compose ONE warm, coherent reply (~120 words) that integrates these.
Don't list "agent 1 says" — write naturally. End with one gentle open question.
```

### 3.4 Acceptance for Week 3

- Supervisor routes 18/20 Tier-3 test cases to the right agent.
- Multi-agent calls (where 2 specialists fire) produce coherent merged replies.
- Each specialist's RAG filter is verified (you can prove it never pulls out-of-domain chunks).

---

## Week 4 — Memory + tools + stateful protocols

This is where the "stateful agent" pattern shows up — the showcase piece for the report.

### 4.1 Redis memory

```
Key: session:{session_id}
Value: {
  "turns": [{"role": "user|assistant", "content": "...", "ts": "..."}],
  "summary": "string — generated when turns > 8",
  "active_protocol": null | {
    "name": "thought_record",
    "state": "step_3_of_5",
    "data": {"automatic_thought": "...", "evidence_for": "..."}
  },
  "mood_log": [{"ts": "...", "score": 1-10, "note": "..."}],
  "consent": {"memory": true, "mood_logging": false}
}
TTL: 7 days
```

Memory injection: at the start of every turn, load this object and pass relevant fields into the prompt. If `turns > 8`, replace the oldest turns with the rolling summary.

### 4.2 Stateful CBT protocols (the showcase)

Build CBT exercises as state machines. Example: **thought record**, 5 states.

```
State 0: trigger        — "Tell me about the situation that bothered you."
State 1: emotion        — "What feeling came up, and how intense (0–10)?"
State 2: hot_thought    — "What thought went through your mind?"
State 3: evidence       — "What evidence supports it? What evidence pushes back?"
State 4: reframe        — "Given both sides, what's a more balanced thought?"
State 5: outcome        — "How do you feel now (0–10)? What's one small next step?"
```

The CBT Agent's prompt receives the current state and the user's last answer, advances state, stores the data in Redis, and asks the next question. When state 5 completes, it summarizes the exercise back to the user.

Build at least these 5 exercises:
- Thought record (5 states)
- Behavioral activation / activity scheduling (4 states)
- Worry postponement (2 states)
- Grounding 5-4-3-2-1 (1 state, scripted)
- Sleep hygiene checklist (3 states)

**This is your strongest demo piece.** A multi-turn structured CBT exercise that resumes correctly even if the user gets distracted mid-protocol is exactly the kind of "agentic" behavior the course is looking for.

### 4.3 Tools (ReAct-style)

Three tools the agents can call via Groq function-calling:

| Tool | Purpose |
|---|---|
| `lookup_resources(topic, city?, language?)` | Returns matching entries from `resources.json` |
| `start_protocol(name)` | Initializes a CBT exercise state machine |
| `log_mood(score, note?)` | Appends to user's `mood_log` (only if consented) |

Optionally: `web_search(query)` via SerpAPI for general info questions. Disabled by default for course scope.

### 4.4 Acceptance for Week 4

- Memory persists across turns; summary kicks in after 8 turns.
- Thought record completes end-to-end across 5 turns, with data captured in Redis.
- User can pause mid-exercise and resume on next message ("Let's keep going with where we left off...").

---

## Week 5 — Bilingual + channel

### 5.1 Bilingual normalization

The normalizer node from Week 2 expands. Cases to handle:

- **English** → pass through.
- **Roman Urdu** ("mujhe bohot tension ho rahi hai") → translate to English, preserve original.
- **Mixed / code-switched** → translate the Urdu parts.
- **Urdu script** → translate.

Reply language matches the user's input language. Add a state field to the session: `preferred_language`.

Note: LLaMA-3.3 handles Urdu reasonably for everyday language; clinical/CBT terminology in Urdu is harder. For your prototype, English-language CBT is acceptable with Urdu explanations. Document this limitation.

### 5.2 Channel

Pick **one** for the course project — don't try to do all three:

- **Web UI** (simplest): plain HTML + JS fetch, hosted statically. Most demo-friendly.
- **WhatsApp** (most impressive): Twilio Sandbox, n8n Twilio node. Bigger wow factor.
- **REST only** (lazy): demo with Postman.

If you go WhatsApp: session_id = hash of phone number. Make sure consent and disclaimers fire on first message.

### 5.3 Onboarding flow

First-ever message in a session triggers a fixed onboarding sequence:

1. What this is and isn't (the scope statement at the top of this doc).
2. Crisis resources displayed up-front.
3. Consent question: memory yes/no, mood-logging yes/no.
4. Then proceed to normal flow.

---

## Week 6 — Evaluation, demo, report

### 6.1 Test set construction

Build `eval/test_set.jsonl` with ~60 items split as:

- **Safety set (25 items)** — Tier 1/2 cases including direct, indirect, metaphorical, and ambiguous expressions. Include adversarial cases (e.g., user asking "hypothetically, what's a painless way to..." — must classify as Tier 1, must not answer).
- **Routing set (20 items)** — Tier 3 cases with gold-standard specialist assignments.
- **RAG set (10 items)** — Tier 4 psychoeducation questions with reference content.
- **Scope set (5 items)** — Tier 5 out-of-scope queries.

### 6.2 Metrics

| Metric | Target | How |
|---|---|---|
| **Tier 1/2 recall** | 100% | Of all Tier 1/2 cases in test set, all must classify as 1 or 2 (false negatives = 0) |
| **Tier 1/2 precision** | report value, target ≥ 0.7 | Over-classification is acceptable but should be documented |
| **Routing accuracy (Tier 3)** | ≥ 85% | Supervisor's specialist choice matches gold |
| **RAG precision@5** | ≥ 80% | Correct chunks in top 5 |
| **Protocol completion rate** | ≥ 90% | Sessions that start the thought-record protocol complete it |
| **Latency p50 / p95** | ≤ 2s / ≤ 5s | Wall-clock |
| **Disclaimer compliance** | 100% | Every response includes the safety footer |

### 6.3 Baseline comparison

Run the same 60 items through three pipelines:

1. **Plain Groq** (no safety, no RAG, no agents).
2. **Safety + RAG single-agent** (Week 2 baseline).
3. **Full system** (Week 5 final).

The Tier 1/2 recall difference between #1 and #2/#3 is the single most important chart in your report. Plain LLMs miss a meaningful share of veiled distress signals — your guardian-agent pattern is the fix.

### 6.4 Demo (3 minutes max)

Script three scenarios, in this order:

1. **Tier 3 → Multi-agent**: User says "I keep arguing with my mom about marriage, I can't sleep" → routes to Cultural + Reflection → coherent merged reply.
2. **CBT protocol**: User asks for help with a worrying thought → CBT Agent walks them through a thought record over 5 messages → final reframe.
3. **Tier 1 safety**: A veiled distress signal that a plain LLM would miss → your Safety Agent catches it → locked crisis response with verified Pakistani resource → stay-present message.

Record this. The Tier 1 demo, in particular, is what differentiates this project from every other "I built a mental health chatbot" submission.

### 6.5 Report structure (10–15 pages)

1. Abstract
2. Introduction — the access gap in Pakistan; the limits of single-agent chatbots
3. Related work — Wysa, Woebot, Youper; what they do and what they miss in low-resource non-Western contexts; agentic AI literature (ReAct, supervisor patterns)
4. **System design — the 7 agentic patterns** (this is the meat)
   - Always-on guardian agent
   - Supervisor–specialist orchestration
   - Stateful multi-turn protocols
   - ReAct tool use
   - Memory with summarization
   - RAG with metadata filtering
   - Bilingual normalization
5. Safety architecture — taxonomy, locked templates, why structural separation matters
6. Implementation — n8n workflows, Groq integration, Redis schema
7. Evaluation — the table + the baseline comparison chart
8. Limitations — no real-user deployment, English-dominant CBT, small corpus, no clinical review
9. Future work — clinical advisor partnership, Urdu CBT content, longitudinal study
10. Conclusion

---

## Risk register

| Risk | Mitigation |
|---|---|
| LLM generates harmful Tier 1 response | Tier 1/2 responses are **template-locked code**, not LLM output. LLM only generates the acknowledgment sentence. |
| Safety Agent misses a veiled crisis | Adversarial Tier 1/2 test set; "over-escalate when uncertain" rule; mandatory disclaimers on every response. |
| Prompt injection bypasses safety | Safety Agent runs *before* any user-controllable context is added to a prompt; it sees only the raw normalized message. |
| User shares identifying info → privacy risk | Redis TTL 7 days; encryption at rest; no PII in logs; consent question at session start. |
| Cultural/religious content gets framing wrong | Cultural Framing Agent is conservative — offers perspective only if user mentions religion/family first; never inserts religious framing unsolicited. |
| Roman Urdu translation drops nuance (especially distress signals) | Safety Agent sees *both* original and normalized text. Translation is for processing, not for safety classification. |
| Examiner asks "can a real user use this?" | Be honest: no. This is a prototype demonstrating agentic patterns. Real deployment would require clinical advisory, IRB, longitudinal user study. Document this clearly. |

---

## What makes this an A-grade Agentic AI project

- The seven agentic patterns are explicit and individually demonstrated, not implied.
- The always-on guardian agent is a novel teaching example most courses don't show.
- The CBT state machines prove you understand multi-turn stateful agents, not just single-turn ReAct.
- The structural separation of risk-classification from response-generation is an architectural insight worth a slide of its own.
- The Tier 1 safety demo, with the baseline comparison, is the moment that wins the grade.

---

## Honest notes

- **Build the baseline first.** The Phase-2 → Phase-3/4 comparison is your evidence that multi-agent helps. Without it, you have a demo, not a result.
- **The safety test set is more important than the code.** Spend disproportionate time crafting adversarial cases. That file is what makes the project trustworthy.
- **Don't over-claim.** Frame as "research prototype demonstrating agentic patterns." Examiners punish overclaim. They reward clear-eyed limitation analysis.
- **Prompts are version-controlled code.** All agent prompts go in `prompts/` as `.md` files in git. Treat them with the same discipline as Python.
