# Locked Crisis Response Templates

These templates are hardcoded within the system logic. If a session is classified as Tier 1 or Tier 2 by the Always-On Safety Guardian, the LLM will **never** freely generate a response. Instead, these safe, verified, and pre-approved clinical response patterns are triggered.

---

## Tier 1 — Acute Crisis Response Pattern

### 1. Warm Acknowledgment Prompt (Groq LLaMA-3.3-70B)
The system invokes a heavily constrained LLM call to generate a single warm, human sentence acknowledging the distress without diagnosing or offering advice.
* **Prompt:**
  ```text
  Generate a single, short, compassionate sentence acknowledging the painful feelings the user just shared. 
  Do not give advice. Do not ask any questions. Do not use clinical or diagnostic terms. Keep it under 15 words.
  ```

### 2. Locked Resource Block (Hardcoded)
```text
It sounds like you are going through an incredibly difficult time right now, but please know that you do not have to carry this alone. There are professional helplines in Pakistan with clinical teams ready to listen and support you:

• Umang Pakistan: Call or WhatsApp 0311-7786264 (Free, 24/7, bilingual support)
• Taskeen Helpline: Call 0316-8275336 (Free, 11 AM - 11 PM Mon-Sat)
• Rozan Helpline: Call 0800-22444 (Toll-Free, 10 AM - 6 PM Mon-Sat)

Please reach out to one of these services, or contact a family member, friend, or doctor you trust.
```

### 3. Stay-Present Invitation (Hardcoded)
```text
I am here and I want to make sure you are safe. If you feel comfortable, please keep chatting with me, or take a moment to reach out to one of the helplines above. Your life is valuable.
```

---

## Tier 2 — High Risk Response Pattern

### 1. Brief Grounding Exercise (Hardcoded)
To help stabilize the user during severe panic, dissociation, or acute distress:
```text
I hear how overwhelming things feel right now. Let's take a deep breath together. 
If you can, try to focus on your physical surroundings for a quick grounding exercise:
- Name 3 things you can see around you.
- Name 2 things you can physically feel (like your feet on the floor or the seat beneath you).
- Name 1 sound you can hear.
```

### 2. Strong Referral Block (Hardcoded)
```text
While we take this pause, please consider reaching out to these professional networks in Pakistan who can guide you through this difficult moment:

• Taskeen Helpline: 0316-8275336 (For emotional support & referrals)
• Karwan-e-Hayat: 021-32202008 (For professional psychiatric and therapeutic care)
• Pakistan Association for Mental Health: 021-35384152 (For outpatient clinical consultations)
```

### 3. Safety Disclaimer (Hardcoded)
```text
Please remember that I am an AI psychoeducation assistant and cannot provide clinical diagnosis or treatment. Talking to a professional is the best way to get the care you deserve. I am here to continue supporting you in a safe space.
```
