

| Vietnam AI Innovation Challenge ENTERPRISE PROBLEM BRIEF *Submission Template for Partner Organisations* |
| :---: |

| *Instructions: Fill in all yellow-highlighted fields. Fields left blank or marked "N/A" may reduce the quality of solutions proposed by competing teams. Submission deadline: please confirm with the organising team.* |
| :---- |

| SECTION A — PARTNER INFORMATION |
| :---- |

| Organisation Name | *VALSEA*  |
| :---- | :---- |

| Industry / Sector | *Speech AI / Voice Infrastructure — Southeast Asian speech-to-meaning platform (Vietnamese, Singlish, Manglish, Bahasa Indonesia, Taglish, Thai). Horizontal infrastructure, not tied to one vertical.* |
| :---- | :---- |

| Primary Point of Contact | *Val — Founder & CEO* Available throughout the hackathon |
| :---- | :---- |

| Website / LinkedIn | *https://valsea.ai / LinkedIn: [https://www.linkedin.com/in/valencia-queck](https://www.linkedin.com/in/valencia-queck?utm_source=share_via&utm_content=profile&utm_medium=member_ios)* |
| :---- | :---- |

| SECTION B — CHALLENGE TRACK |
| :---- |

**Select the track that best fits your problem statement (choose one):**

|   🏥 Healthcare |   🎓 Education & Training |   🌪 Disaster Prevention | ✓ SELECTED — Innovation |
| :---- | :---- | :---- | :---- |

|   🏢 SME Productivity |   🏛 Smart Government |   🌾 Agriculture |   Other: \_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_ |
| :---- | :---- | :---- | :---- |

| Why this track? | *VALSEA is speech-to-meaning infrastructure for Southeast Asia, not a single-vertical product. This problem is deliberately open across verticals so teams can prove, live, where the ASR \+ semantic layer creates the most value first — and the strongest teams become the people we hire to build it.* |
| :---- | :---- |

| SECTION C — PROBLEM STATEMENT |
| :---- |

**C1. Problem Title**

*Keep it short and clear — this title will appear on the hackathon platform and in all communications*

| *Speech-to-Meaning, Not Speech-to-Text: Turning Vietnamese Voice into Workflow-Ready Action* *Từ Giọng Nói Đến Hành Động: Biến Tiếng Việt Thành Đầu Ra Sẵn Sàng Cho Quy Trình Làm Việc* |
| :---- |

**C2. Context & Problem Background**

*Describe the current situation: who is affected, how often it occurs, and the scale of impact. Minimum 150 words.*

| Current situation: Global and regional speech engines (Whisper, Google STT, Vietnamese cloud STT) breaks down on real Vietnamese speech — regional accents, intra-sentence code-switching with English, telephone/field-recorded audio, and domain jargon. Businesses still route voice into manual typing or unreliable transcripts, and that manual step is where accuracy, time, and compliance get lost. Who is affected? (target population): Frontline and back-office staff across any vertical who currently type up what was said on a call, in a meeting, or in the field — call center agents, clinic front-desk staff, extension officers, teachers, case workers, ops managers. Scale / frequency of the problem: Daily and continuous — voice is the default interface in Vietnamese business and government interactions, and almost none of it is captured as structured, usable data today. Existing solutions and their shortcomings: Global ASR handles standard, single-language, studio-quality audio reasonably well, but degrades sharply on Vietnamese accents, code-switched speech, and noisy real-world audio — and even accurate transcription is just a flat wall of text, not something a workflow can act on. How does your organisation handle this today? VALSEA is building the accent-aware ASR and semantic understanding layer specifically for this gap. This hackathon problem is deliberately open so teams can prove, live, which vertical and workflow gets the most value from that layer first. Why is now the right time to solve this with AI? Foundation-model ASR has commoditized 'good enough' transcription — the frontier has moved to the semantic and workflow layer on top of it, which is exactly where regional, code-switched speech needs the most work and where the biggest unsolved gap for Southeast Asia remains. |
| :---- |

**C3. Core Challenge Question**

*Frame the problem as a "How might we..." question to help teams focus on the right target*

| *How might we use VALSEA's Vietnamese-accent-aware ASR — and any other VALSEA endpoint — to turn a specific class of real Vietnamese speech into a workflow-ready output (a ticket, subtitles, a structured note, an action item) that plugs directly into a process a business already runs, in any vertical?* |
| :---- |

| SECTION D — EXPECTED OUTCOMES |
| :---- |

**D1. Success Criteria**

*What does a "good" solution look like? Be specific — avoid vague language*

A good solution correctly transcribes a real Vietnamese speech sample using VALSEA's ASR endpoint, then turns that transcript into a workflow-ready output — not just clean text — using at least one additional VALSEA endpoint or the team's own logic. It should work on messy, real input (accented, code-switched, or noisy audio), not a clean demo clip, and the team should be able to say exactly which vertical and workflow it targets and why that is valuable.

| \# | Outcome | Measurable by |
| :---- | :---- | :---- |
| 1 | *Cut manual transcription/note-taking time for a real Vietnamese speech workflow from hours to minutes* | *Live demo: time-to-output vs. a manual baseline, timed on stage* |
| 2 | *Handle at least one hard case class correctly — code-switched VN/EN speech, a regional accent, or noisy/telephony audio — that generic ASR mishandles* | *Side-by-side transcript comparison against raw/generic ASR output on the same clip* |
| 3 | *Produce a workflow-ready structured output, not a raw transcript, that a business could act on immediately* | *Working demo of the output populating a form, ticket, subtitle file, or note — not just printed text* |

**D2. Minimum Deliverables**

*What must a solution achieve after 48 hours to be eligible for judging?*

* ☑  Demoable prototype (live URL or video recording)

* ☑  Code repository (public GitHub)

* ☑  Explainable AI architecture

* ☑  Pilot / deployment roadmap (1–2 pages)

* ☐  Other: \_\_\_\_\_\_\_\_\_\_\_\_\_\_\_

**D3. Pilot Pathway Definition**

*If a team wins, what does real-world deployment at your organisation look like?*

| Pilot scale | *Not a traditional enterprise pilot — this track's reward is direct: the winning 'Best Use of VALSEA API' team is fast-tracked into a paid internship with the VALSEA founding team.*   |
| :---- | :---- |
| **Pilot duration** | *Internship track begins immediately after the hackathon; scope and duration discussed directly with the winning team.* |
| **Organisation's commitments** | *VALSEA provides live API access during the 48h, founder-level technical support via Discord, and a guaranteed internship interview for the winning team. (https://careers.valsea.ai)* |
| **Conditions to sign a pilot contract** | *Demonstrates real, working use of the VALSEA ASR endpoint at minimum (any additional VALSEA endpoint is a bonus); output must be workflow-ready, not just a transcript.* |

| SECTION E — DATA & RESOURCES |
| :---- |

**E1. Available Data**

*Describe in detail the data you will provide for teams to build their solution*

VALSEA will issue every team a sandbox API key covering the ASR endpoint (mandatory) and the semantic / workflow-output endpoint (optional), plus a small set of sample Vietnamese audio clips spanning code-switched, regional-accent, and noisy/telephony conditions for testing (see dataset table below).

|  Dataset name | Description | Format | How to access |
| :---- | :---- | :---- | :---- |
| VALSEA ASR API (mandatory) | Vietnamese-accent-aware speech-to-text endpoint — the required entry point for every team | *API* | *Sandbox API key provided at kickoff* |
| VALSEA Semantic / Workflow-Output API (optional) | Structures ASR output into meaning — entities, intent, summaries, subtitles, structured notes | *API* | *Sandbox API key provided at kickoff* |
| Sample Vietnamese speech clips | Small anonymised/synthetic audio set spanning code-switched, regional-accent, and noisy/telephony conditions, for testing | *Audio (WAV/MP3)* | *Downloadable link, shared at kickoff* |

**E2. Data Constraints**

| Constraints | *Can data be used after the hackathon? ☐ Yes   ☑ Hackathon period only   ☑  Requires NDA — production API access continues only for teams entering the internship track* |
| :---- | :---- |
|  | *Does data contain personally identifiable information (PII)? ☑ No   ☐ Yes, anonymised   ☐ Yes, agreement needed — sample audio is synthetic/anonymised* |
|  | *No additional security or compliance requirements for the hackathon sandbox; standard API terms apply.* |

**E3. Additional Resources**

* Internal APIs (name & endpoint): VALSEA ASR API — POST /v1/asr/transcribe (mandatory for all teams); VALSEA Semantic API — POST /v1/understand (optional). Full docs shared with sandbox key at kickoff.

* Business process documentation / SOPs: N/A — problem is intentionally vertical-agnostic; each team defines its own target workflow.

* Cloud credits budget for the winning team: N/A — VALSEA sandbox API access is free for the hackathon; no separate cloud credit budget allocated.

* Domain experts available during the 48h (name & area): Val — Founder, VALSEA (Southeast Asian speech AI / voice infrastructure), available remotely via Zalo/Discord throughout the event.

| SECTION F — CUSTOM JUDGING CRITERIA |
| :---- |

*The organising team's general rubric: Problem Relevance 20%, AI-Native Architecture 20%, Technical Execution 15%, Deployment 15%, Feasibility 15%, Startup Potential 15%. Use this section to add track-specific criteria.*

| Custom Criterion | Description | Weight (%) |
| :---- | :---- | :---- |
| Best Use of VALSEA API | Depth and correctness of VALSEA ASR usage, plus any additional VALSEA endpoint used to go from speech to a workflow-ready output | 15% |
| Workflow-Readiness | Output plugs directly into a real business process (ticket, form, subtitle file, structured note) rather than stopping at a raw transcript | 15% |
| **Total additional weight (must not exceed 30% of the general rubric)** |  | **30%** |

| SECTION H — TECHNICAL REQUIREMENTS |
| :---- |

*Only specify what is genuinely mandatory. Fewer constraints \= more creative solutions from teams.*

**H1. Language Requirements**

*Which languages must the solution support, and to what level?*

| Language | Requirement Level | Notes |
| :---- | :---- | :---- |
| Vietnamese | ☑ Mandatory  ☐ Preferred  ☐ Optional | *Must handle spoken and informal written Vietnamese, including regional accents (Northern/Central/Southern) and intra-sentence code-switching with English* |
| English | ☐ Mandatory  ☑ Preferred  ☐ Optional | Useful for code-switched terms and technical jargon embedded in Vietnamese speech |
| Other local language | ☐ Mandatory  ☐ Preferred  ☑ Optional | *E.g. Lao, Khmer, ethnic minority languages...* |
| Multilingual simultaneously | ☑  Mandatory  ☐ Preferred  ☐ Optional | *Bonus for correctly handling Vietnamese/English code-switching within a single utterance* |

**Any other specific language processing requirements:**

| *Must preserve tonal diacritics correctly; must not silently drop or garble code-switched English terms embedded in Vietnamese speech.*  |
| :---- |

**H2. Local Context Requirements**

*What local or Vietnam-specific knowledge must the solution incorporate to work correctly?*

| Context Requirement | Required | Specific Details |
| :---- | :---: | :---- |
| Understand local Vietnamese culture & communication norms | ☑ | *E.g. Polite registers, regional customs, tone of voice in Vietnamese interactions* |
| Comply with Vietnamese legal and regulatory requirements | ☐ | *E.g. data protection law, healthcare regulations — only if the team's chosen vertical requires it (e.g. healthcare/government)* |
| Understand Vietnamese administrative & geographical structure | ☐ | *Only if the team's chosen vertical requires it* |
| Handle Vietnamese data formats correctly | ☑ | *E.g. Vietnamese names, addresses, VND currency, phone numbers* |
| Integrate with existing Vietnamese government systems | ☐ | *Optional / bonus — not required to be eligible* |
| Other specific local context requirement | ☐ |  |

**H3. Infrastructure & Performance Requirements**

| Deployment environment | *☐ Cloud (AWS/GCP/Azure)  ☐ On-premise  ☐ Edge / device  ☑ No specific requirement* |
| :---- | :---- |
| **Internet connectivity** | *☐ Must have continuous internet  ☐ Must work offline  ☑ Both, depending on context* |
| **End-user device** | *☐ Web browser  ☐ Mobile app  ☐ Desktop  ☑ No specific requirement* |
| **Response speed requirement** | *No hard SLA for the hackathon demo; aim for near-real-time (a few seconds per utterance) — VALSEA's pitch is a live speech → meaning → action pipeline* |
| **Security & privacy requirements** | *No special requirement beyond standard API sandbox terms for the hackathon; disclose if any non-VALSEA speech API is used elsewhere in the pipeline* |
| **APIs / systems that must be integrated** | *Must call the VALSEA ASR endpoint for the speech-to-text step at minimum; any other VALSEA endpoint (semantic, workflow-output) is optional and scored under Best Use of VALSEA API* |
| **Programming language / framework** | *No requirement* |

| SECTION I — WHAT A GREAT SOLUTION LOOKS LIKE |
| :---- |

*This section communicates your vision to teams — not to constrain creativity, but to help them aim in the right direction. Be as specific as possible.*

**I1. Ideal Solution Description**

*What does a perfect solution look like after 48 hours? Describe it in the end user's language.*

| *"A support hotline in Vietnam takes a call in fast, informal Vietnamese mixed with English terms. VALSEA transcribes it accurately in real time, and within seconds the same pipeline turns it into a clean ticket with the customer's issue, sentiment, and next action already filled in — no one touches a keyboard."*  |
| :---- |

**I2. Solution Quality Tiers**

*Help teams understand what "good enough" looks like versus "outstanding"*

| Dimension | Basic | Good | Outstanding |
| :---- | ----- | ----- | ----- |
| **Language handling** | English only | Standard Vietnamese supported | Understands dialects, spoken language, local terminology |
| **AI accuracy** | Demoable, many errors | Works correctly \>70% of test cases | Accuracy \>90%, includes error detection mechanism |
| **Deployment** | Runs on local machine only | Live public URL, demoable | Deployed, stable, with basic monitoring |
| **Local context** | None | Partially addressed | Deeply integrates Vietnamese / sector-specific context |
| **Scalability** | Solves one narrow use case | Applicable to similar scenarios | Clear roadmap to scale nationally or regionally |

**I3. Anti-Patterns to Avoid**

*List solutions that would not score well even if technically impressive — helps teams avoid wasted effort*

☑  Solution only works with clean / ideal data; cannot handle real-world inputs

☑  Requires end users to have high technical skills to operate

☑  Entirely dependent on unstable or prohibitively expensive foreign APIs

☑  Demo is a mockup / slideshow with no real AI running behind it

☑  No realistic deployment plan — purely a proof of concept

☑  Completely ignores language and local context requirements

☑  Other (add your own): Uses VALSEA's ASR as a thin wrapper around a generic chatbot with no real workflow output

**I4. Inspirational Examples**

*Share 1–3 products or projects (local or global) that point in the right direction — not necessarily identical to what you need, but capturing the right spirit*

| Product / Project Name | What you like about it | Link (if available) |
| :---- | :---- | :---- |
| Otter.ai | Real-time meeting transcription that outputs structured notes and action items, not just a transcript | *https://otter.ai* |
| Deepgram | Developer-first ASR infrastructure — a model for exposing speech infra as clean, composable API endpoints | *https://deepgram.com* |
| FPT.AI Speech | Vietnamese-market ASR/TTS example — useful reference point for regional accent handling | *https://fpt.ai* |

| SECTION J — ADDITIONAL INFORMATION |
| :---- |

| Special prize from your organisation | *Winner of the 'Best Use of VALSEA API' criterion is fast-tracked directly into a paid internship interview with the VALSEA founding team, working on Southeast Asia's speech-to-meaning infrastructure.*  |
| :---- | :---- |

| Any other mandatory technical constraints | *Every team must use the VALSEA ASR endpoint for the speech-to-text step — no substituting a different ASR provider for that step. Everything downstream (semantic layer, workflow output, UI) is open.* |
| :---- | :---- |

| Intellectual property notes | *Team code and any non-VALSEA components belong to the team. VALSEA's API, models, and any sandbox data provided remain VALSEA's property; standard sandbox API terms apply during the event. \[Confirm final IP language with the organising team before submission.\]*  |
| :---- | :---- |

| Questions for the organising team | *How do we get in touch with all the teams using VALSEA API? Is there a list of their contact number via zalo/ linkedin/ discord/ telegram?* |
| :---- | :---- |

