# Voice2Claim demo video script (English)

Video: `out/demo/voice2claim_demo_en.mp4` — rebuild: `scripts/make_demo_video.py docs/product/video-scenes-en.json en`


## 🎬 VOICE2CLAIM

- **Caption:** Intelligent voice-driven claim assessment · VALSEA Hackathon 2026
- **Narration (VALSEA):** “Hello judges, and welcome. This is Voice 2 Claim — an insurance operations platform driven entirely by voice, built on the VALSEA Speech API. This video has two demos: first, an AI call center handling a real customer call; second, the platform that runs the whole case automatically after the call.”

### Scene 01 — Overview — the operations cockpit

- **Screen:** `out/demo/shots/test_dash.png`
- **Caption:** Real-time KPIs · AI Decision Feed: every AI decision is logged and explainable
- **Narration (VALSEA):** “This is the Overview screen. On the left, real-time operational numbers. In the middle, the Decision Feed — where the AI orchestrator logs every decision it makes: call routing, risk scoring, task assignments. Judges can audit every single step right here.”

## 🎬 DEMO 1 — THE AI CALL CENTER

- **Caption:** Outbound Agent Call · Workflow call center · Replay mode (real recording)
- **Narration (VALSEA):** “Demo one: the AI call center. We use Replay mode — replaying a real customer recording — so you can watch the entire pipeline without depending on a live phone line. Every voice step runs on VALSEA: listening, understanding, and speaking back.”

### Scene 03 — The Call page — Workflow call center + Replay

- **Screen:** `out/demo/shots/d1_00_idle.png`
- **Caption:** The 7-field intake form on the left will be filled automatically by AI during the conversation
- **Narration (VALSEA):** “Here is the call page. We select the workflow call center pack, choose Replay mode, and press Call. The intake form on the left is empty — the AI will fill it in while talking with the customer.”

### Scene 04 — AI verifies the caller and looks up the CRM

- **Screen:** `out/demo/shots/d1_02.png`
- **Caption:** Name + national ID digits → database match → reads back active policy and claims
- **Narration (VALSEA):** “First, the AI agent, Mai, asks for the caller's name and the last digits of their national ID. The system looks up the CRM, confirms the identity matches, then reads back the customer's active policy and existing claim.”

### Scene 05 — The customer talks freely — AI detects intent, fills the form

- **Screen:** `out/demo/shots/d1_04.png`
- **Caption:** Sub-millisecond intent router picks the 'New incident' workflow · local extraction fills each field with confidence
- **Narration (VALSEA):** “The customer says he was hit on Cong Hoa street. The intent router picks the right workflow — new incident intake — and everything he said is extracted into structured fields: location, time, damage description, injuries — each with a confidence score.”

### Scene 06 — AI only asks what's missing, then reads back to confirm

- **Screen:** `out/demo/shots/d1_06.png`
- **Caption:** Fields already captured from the story are skipped — shorter calls, accurate records
- **Narration (VALSEA):** “The AI only asks about the fields still empty, then reads the whole record back for confirmation. That keeps the call short while keeping the file accurate.”

### Scene 07 — Call ends: Ticket + PDF + Emails + Recording — fully automatic

- **Screen:** `out/demo/shots/d1_15_final.png`
- **Caption:** High-priority ticket · industry-standard PDF · emails to customer and staff · call recording stored
- **Narration (VALSEA):** “The call ends: the system creates a high-priority ticket, renders a PDF intake form, emails both the customer and the assigned staff, and stores the recording. Most importantly — a claim workflow has just been started by the AI in the background.”

## 🎬 DEMO 2 — THE OPERATIONS PLATFORM

- **Caption:** CRM 360 · Role-based inbox · Visual workflow engine · Self-improving flywheel
- **Narration (VALSEA):** “Demo two: the operations platform. That phone call has already created a claim in the CRM and triggered a workflow. Let's follow the case through each role: the field assessor, the director, and the platform's self-improvement loop.”

### Scene 09 — AI Decision Feed — the decision chain from that call

- **Screen:** `out/demo/shots/d2_01_dash.png`
- **Caption:** Route intent → open claim → risk score with reasons → assign the assessor — full audit trail
- **Narration (VALSEA):** “Back on the Overview: the Decision Feed shows the chain of decisions the AI just made — routing the call, opening the claim, scoring the risk with explicit plus and minus reasons, and assigning the field assessor.”

### Scene 10 — CRM — Customer 360

- **Screen:** `out/demo/shots/d2_02_crm.png`
- **Caption:** Policies · Claims · Interactions with call recordings · Full timeline — one SQLite source of truth
- **Narration (VALSEA):** “In the CRM, a three-sixty degree customer view: policies, claims, interaction history with call recordings, and a timeline of every change. The new claim from the call is right there, in received status.”

### Scene 11 — Workflow run — live progress on the diagram

- **Screen:** `out/demo/shots/d2_03_run_wait.png`
- **Caption:** Green nodes: done · amber node: waiting for the assessor's site visit
- **Narration (VALSEA):** “This is the claim workflow run, shown directly on the diagram: completed steps in green, and the waiting step in amber — the assessor needs to visit the scene, take photos and record the statement.”

### Scene 12 — Task inbox — the Assessor role

- **Screen:** `out/demo/shots/d2_04_task_assessor.png`
- **Caption:** AI-collected file ready · enter damage estimate · attach the field recording · flywheel star rating
- **Narration (VALSEA):** “In the assessor's inbox, everything the AI collected is ready. The assessor enters the damage estimate, attaches the field recording, rates the process quality, and clicks complete — the workflow instantly moves on.”

### Scene 13 — VALSEA transcribes the recording → Assessment report PDF

- **Screen:** `out/demo/shots/d2_05_run_transcribed.png`
- **Caption:** transcribe_media in under 5 seconds · auto-drafted report · update email to the customer
- **Narration (VALSEA):** “VALSEA transcribes the field recording in seconds. The system drafts the assessment report as a PDF, including the verbatim statement, emails an update to the customer, and sends the case up to the director.”

### Scene 14 — Director approval — one click

- **Screen:** `out/demo/shots/d2_06_task_director.png`
- **Caption:** Approve / Reject + amount + reason · every branch is already drawn in the workflow
- **Narration (VALSEA):** “The director sees the whole file and the report, enters the payout amount, and clicks approve. If they reject instead, the workflow automatically branches to an explanation letter — every path is drawn in the diagram.”

### Scene 15 — Payout + the AI automatically CALLS the customer

- **Screen:** `out/demo/shots/d2_07_run_done.png`
- **Caption:** auto_call node — VALSEA voice reads the right name, case ID and amount · claim → PAID
- **Narration (VALSEA):** “After approval, the claim moves to paid, the result email goes out, and the AI automatically calls the customer — speaking their name, the case ID and the exact amount, in the VALSEA voice.”

### Scene 16 — Workflows live in the database + quality flywheel per version

- **Screen:** `out/demo/shots/d2_08_wf.png`
- **Caption:** Node-edge diagram · v1 vs v2 comparison · customer stars · staff stars · Qwen judge · JSON editor
- **Narration (VALSEA):** “The entire process is configuration in the database — visible and editable. The flywheel table compares quality across versions: processing time, customer and staff ratings, plus a second opinion from the Qwen model. Edit the config and you get a new version; old versions stay immutable.”

### Scene 17 — Underneath: the Speech-to-Meaning engine

- **Screen:** `out/demo/shots/d2_09_pilot.png`
- **Caption:** Batch · Live mic · Review scoring — 10/10 gold scenarios, 86/86 fields, trigger under half a second
- **Narration (VALSEA):** “Under the platform sits the Speech-to-Meaning engine: batch audio processing, live microphone, and review scoring before submission — hitting ten out of ten gold scenarios with all eighty-six fields correct, and voice-trigger arming in under half a second.”

### Scene 18 — Second flow: Policy opening — voice prefill + e-signature

- **Screen:** `out/demo/shots/d2_10_contract.png`
- **Caption:** Speak your request → AI fills the form → risk assessment → contract PDF → e-sign by email → auto-call
- **Narration (VALSEA):** “The platform also runs a policy-opening flow: the customer describes what they need by voice, the AI fills the form and scores the risk — high-risk files branch to manual underwriting. The contract PDF is emailed for electronic signature.”

### Scene 19 — E-signature — a single-use email link

- **Screen:** `out/demo/shots/d2_11_sign.png`
- **Caption:** Single-use token · double-click safe · once signed, the policy is ACTIVE in the CRM + congratulation call
- **Narration (VALSEA):** “This is the signing page the customer receives by email — a single-use link, safe even if clicked twice. Once signed, the policy becomes active in the CRM immediately, and the AI calls to congratulate the customer.”

### Scene 20 — Knowledge base — business documents become workflows

- **Screen:** `out/demo/shots/d2_12_kb.png`
- **Caption:** Upload documents → Qwen extracts the process offline (17s) → promote to a 12-node draft workflow
- **Narration (VALSEA):** “Finally, the knowledge base: a company uploads its business documents, the AI extracts them into draft workflows — like this twelve-step assessment process — and an admin promotes them into production. That's how the platform scales to any business process.”

## 🎬 VOICE2CLAIM — From Voice to Action

- **Caption:** VALSEA ASR · Realtime · TTS + workflow engine + AI orchestrator + flywheel · Thank you!
- **Narration (VALSEA):** “Voice 2 Claim: from voice to action — an AI call center, a CRM, visual workflows and a self-improving loop, all running for real on the VALSEA Speech API. Thank you for watching.”