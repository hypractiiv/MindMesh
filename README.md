# 🧠 MindMesh: Adaptive Learning Intelligence Platform

[![Python 3.10+](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue.svg)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.40+-FF4B4B.svg)](https://streamlit.io/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Neon%20Serverless-336791.svg)](https://neon.tech/)
[![SQLite](https://img.shields.io/badge/SQLite-Local%20Fallback-003B57.svg)](https://www.sqlite.org/)
[![Tests](https://img.shields.io/badge/pytest-78%20passed-brightgreen.svg)](tests/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## 🎯 The Vision in One Sentence
> *"Detect a confident-but-wrong answer, challenge lucky guesses, pause for the student, resolve the misconception, and schedule precision active recall before memory decays."*

**MindMesh** is an agentic, persistent learning-confidence tracking platform designed for computer science mastery. It bridges the critical gap between **superficial completion** (passing an autograder or guessing an MCQ) and **authentic conceptual retention**. 

By continuously correlating demonstrated correctness against calibrated self-confidence ratings (1–5 scale), MindMesh detects **Confidence-Knowledge Mismatches** (Dunning-Kruger blind spots) in real time. Rather than silently grading and moving on, the agent takes an adaptive backward step to demand reflection and targeted correction, persisting full audit trails across sessions and dispatching automated spaced-repetition review reminders.

---

## 🌟 Key Features

### 1. 🎯 Dual-Loop Agentic Verification
- **Loop A (Lucky Guess Elimination):** When a student answers a multiple-choice question correctly on the first attempt, the agent does not assume mastery. It prompts for a brief technical explanation justifying *why* the choice is correct and *why* distractors fail.
- **Loop B (Blind Spot Target Correction):** When a student submits an incorrect answer with high confidence ($\ge 4/5$), the agent intercepts the failure, flags the exact misconception objection, and prompts with a targeted follow-up question.

### 2. 🌐 Dynamic Topic Synthesis Engine
- **Curated Technical Catalog:** Hand-crafted, rubric-verified benchmark questions covering core computer science topics:
  - `recursion_base_case`: Base case additive vs multiplicative identity in list summation.
  - `binary_search_bounds`: Boundary inclusivity (`low <= high`) and integer overflow mitigation.
  - `db_acid_atomicity`: Transaction rollback guarantees in relational databases.
  - `python_gil_multiprocessing`: CPython GIL mutex tradeoffs and CPU parallelism.
  - `sql_where_vs_having`: Row-level filtering vs group-level aggregate filtering lifecycles.
- **AI-Powered Synthesis (OpenAI & Gemini):** Type *any* computer science concept (e.g. `OS Deadlocks`, `Dynamic Programming`, `B-Trees`, `OAuth2 PKCE`) to dynamically synthesize authentic 4-choice questions modeled after authoritative quiz platforms (GeeksforGeeks, Sanfoundry, LeetCode, Real Python).
- **Anti-Repetition Invariant:** Stores prior question prompts in the database and injects negative-constraint prompts into subsequent generation calls, guaranteeing students never receive repetitive questions on the same topic.
- **Resilient Fallback Chain:** `OpenAI (Primary)` $\to$ `Google Gemini (Fallback)` $\to$ `Wikipedia REST API` $\to$ `Offline Emergency Template`.

### 3. ⏳ Spaced Repetition & Decay Engine (`decay.py`)
- Calculates customized active recall review intervals based on demonstrated outcome and final confidence:
  - **First-Try Correct (Confidence 5):** $+7$ days (168h) — Long-term consolidation.
  - **First-Try Correct (Confidence 4):** $+5$ days (120h).
  - **First-Try Correct (Confidence 3):** $+3$ days (72h).
  - **Corrected on Follow-up:** $+48$ hours — Misconception reinforcement.
  - **Unresolved Attempt:** $+18$ to $+24$ hours — Urgent remediation.
  - **Skipped / Timed Out:** $+12$ hours — Accelerated resurfacing.
- **Debug Time-Travel:** `⏩ Fast-Forward Time (+72h)` button simulates the passage of days to instantly test decay schedules and trigger second encounters.

### 4. 📧 Automated Review Daemon & Live SMTP Notifications (`notifier.py`)
- **Background Daemon:** `ReviewSchedulerDaemon` background thread auto-polls the database every 120 seconds, identifying concepts that have reached their scheduled review window.
- **Dual Delivery Modes:**
  - **Live SMTP:** Full TLS/STARTTLS delivery to real inboxes (supports Gmail App Passwords, Brevo, SendGrid, Amazon SES, or custom SMTP).
  - **Simulated Mode:** Zero-crash fallback when SMTP credentials are unset; renders complete HTML Obsidian-dark templates in the UI for review.

### 5. 💾 Dual-Engine Persistence (`store.py`)
- **Primary:** Cloud-hosted **Neon Serverless PostgreSQL** with thread-safe connection pooling, TCP keepalives, and automatic pre-ping SSL recovery.
- **Fallback:** Zero-configuration **SQLite** (`mindmesh.db`) with append-only event logging, crash recovery, and instant local execution.

### 6. 👤 Multi-Student Authentication & Session Isolation
- Salted SHA-256 password hashing with dedicated user profiles.
- Strict data isolation: Multiple students can practice identical concepts with completely independent review schedules, metrics, and audit streams.
- Guest mode with automatic session flushing.

### 7. 📊 Topic-Wise vs All-Topics Analytics & Control
- **Scope Toggle:** Seamlessly switch between `🎯 Topic-Wise` (metrics isolated to the active concept) and `🌐 All Topics` (global historical mastery).
- **Recently Learned Topics:** Instant sidebar navigation displaying recently practiced concepts with color-coded accuracy indicators (🟢/🟡/🔴).
- **Sidebar Collapse Bridge:** Seamless client-side JavaScript DOM bridge to toggle Streamlit's sidebar.

---

## 🏗️ System Architecture

```
                                  ┌──────────────────────────────────────────────────────────┐
                                  │                  Student Web Interface                   │
                                  │                 (Streamlit / CLI Demo)                   │
                                  └────────────┬─────────────────────────────▲───────────────┘
                                               │ User Action                 │ State Updates
                                               ▼                             │
                                  ┌──────────────────────────────────────────┴───────────────┐
                                  │                flow.py (FlowSession)                     │
                                  │        Enforces 6 States & Legal Transitions             │
                                  └────────────┬─────────────────────────────▲───────────────┘
                                               │ Step Dispatch               │ Verified Verdict
                                               ▼                             │
                                  ┌────────────────────────┐    ┌────────────┴───────────────┐
                                  │        steps.py        │    │         llm.py             │
                                  │  Prompting, Answering, ├───▶│  Spend Limit: <= 4 Calls   │
                                  │  Checking, Follow-up,  │    │  OpenAI ➔ Gemini ➔ Rules   │
                                  │  Record, Skip          │    │  <STUDENT_ANSWER> Defense  │
                                  └────────────┬───────────┘    └────────────────────────────┘
                                               │
                                               ├─────────────────────────────┐
                                               ▼                             ▼
                                  ┌────────────────────────┐    ┌────────────────────────────┐
                                  │        store.py        │    │        notifier.py         │
                                  │ PostgreSQL (Neon Pool) │    │  ReviewSchedulerDaemon     │
                                  │        or SQLite       │    │  HTML/SMTP Review Alerts   │
                                  └────────────┬───────────┘    └────────────────────────────┘
                                               │
                                               ▼
                                  ┌────────────────────────┐
                                  │        decay.py        │
                                  │ Spaced Repetition Math │
                                  │ Next Review Timestamp  │
                                  └────────────────────────┘
```

---

## 🔄 The Six-State Machine Flow

```mermaid
stateDiagram-v2
    [*] --> Prompting
    Prompting --> Answering: Question Loaded (Curated or Dynamic)
    Answering --> Checking: Student submits Choice & 1-5 Confidence
    Answering --> Skipped: Timeout / User Skips
    Checking --> Waiting_for_followup: Mismatch (High Confidence >=4, Wrong Choice)
    Checking --> Waiting_for_followup: MCQ Correct on Attempt 1 (Explanation Verification)
    Checking --> Recorded: Answer passes OR 1 follow-up round exhausted
    Waiting_for_followup --> Checking: Student submits Follow-up / Explanation
    Waiting_for_followup --> Skipped: Timeout / User Skips
    Recorded --> [*]: Finished (Spaced Repetition Scheduled)
    Skipped --> [*]: Finished (12h Decay Accelerated)
```

- **Critical Transition:** `Checking` $\to$ `Waiting for follow-up` intercepts students before they leave with unaddressed blind spots.
- **Revision Limit:** Strictly capped at **1 follow-up round** per session, bounded by stored answer records.
- **Spend Limit:** Strictly capped at **4 model calls** per concept session via centralized circuit breaker.

---

## 🚀 Quick Start

### 1. Clone & Setup Environment
```powershell
# Clone the repository
git clone https://github.com/hypractiiv/MindMesh.git
cd MindMesh

# Create & activate virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1   # On Windows
# source .venv/bin/activate  # On macOS/Linux

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Copy `.env.example` to `.env`:
```powershell
cp .env.example .env
```

Edit `.env` with your preferred credentials:
```ini
# Primary LLM Generator & Grader (OpenAI or OpenRouter)
OPENAI_API_KEY=your_openai_api_key_here
# Fallback LLM Generator & Grader (Google Gemini)
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-3.1-flash-lite-preview

# Database Configuration (Leave unset to use zero-config local SQLite!)
DATABASE_URL=your_database_url_here

# Optional: Outgoing SMTP for Live Email Notifications
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASSWORD=your_16_char_google_app_password
SMTP_FROM=your_email@gmail.com
```

> **Note:** If `DATABASE_URL` is omitted, MindMesh automatically runs on zero-configuration local **SQLite** (`mindmesh.db`). If API keys are omitted, MindMesh uses curated benchmarks and deterministic rule-based evaluation.

---

### 3. Run Automated Unit & Integration Tests (78 Tests)
```powershell
.venv\Scripts\python -m pytest tests/ -v
```
*Executes all 78 tests covering state machine reachability, dual-loop verification, persistence, crash recovery, prompt injection defense, spend limits, PostgreSQL pooling, and email notifications.*

---

### 4. Run the 8-Beat Judge Demo (Automated Headless CLI)
```powershell
.venv\Scripts\python cli.py --demo
```
*Walks through the entire 8-beat sequence headlessly in ~10 seconds: establishing context, triggering a confidence mismatch, backward follow-up transition, live correction, persistence, time-travel, and the second encounter.*

---

### 5. Launch the Web Application
```powershell
.venv\Scripts\streamlit run app.py
```
Open **`http://localhost:8501`** in your browser.

---

### 6. Optional: Run Local PostgreSQL with Docker
If you want to run a local PostgreSQL instance matching Neon:
```powershell
docker compose up -d
```
Then set in `.env`:
```ini
DATABASE_URL=postgresql://postgres:password@localhost:5432/mindmesh
```

---

## 📂 Project Structure & Component Ownership

| Component | Responsibility | Primary File |
|---|---|---|
| **Presentation UI** | Streamlit cyber-intelligence dark theme, 5-stage stepper, 4-card metric ribbon, interactive emoji selector, email preview modal. | [`app.py`](file:///E:/Agentathon/MINDMESH/app.py) |
| **State Machine** | `FlowSession` runner, legal transition validation, session resumption from persistent audit logs. | [`flow.py`](file:///E:/Agentathon/MINDMESH/flow.py) |
| **Step Execution** | Contracts for prompting, answering, checking, follow-up, recording, and skipping. | [`steps.py`](file:///E:/Agentathon/MINDMESH/steps.py) |
| **Data Models** | Pydantic v2 schemas (`State`, `Outcome`, `Answer`, `Verdict`, `Question`, `ConceptRecord`, `SessionEvent`, `User`). | [`models.py`](file:///E:/Agentathon/MINDMESH/models.py) |
| **Persistence** | Dual-engine storage: `PostgresStore` (Threaded pool, keepalives, pre-ping) + `MindMeshStore` (SQLite). | [`store.py`](file:///E:/Agentathon/MINDMESH/store.py) |
| **Topic Engine** | Curated catalog, dynamic OpenAI & Gemini synthesis, negative-prompt anti-repetition, Wikipedia fallback. | [`fetcher.py`](file:///E:/Agentathon/MINDMESH/fetcher.py) |
| **Centralized LLM** | Single model boundary, 4-call spend limit, `<STUDENT_ANSWER>` sanitization, OpenAI $\to$ Gemini $\to$ Rules fallback. | [`llm.py`](file:///E:/Agentathon/MINDMESH/llm.py) |
| **Spaced Repetition** | Deterministic decay interval calculations ($12\text{h} \dots 7\text{d}$), $+72\text{h}$ debug time-travel. | [`decay.py`](file:///E:/Agentathon/MINDMESH/decay.py) |
| **Email Notifier** | Responsive HTML templates, live SMTP delivery, simulated mode, background `ReviewSchedulerDaemon`. | [`notifier.py`](file:///E:/Agentathon/MINDMESH/notifier.py) |
| **CLI & Demo** | 8-beat automated judge demo runner and interactive CLI terminal review. | [`cli.py`](file:///E:/Agentathon/MINDMESH/cli.py) |
| **Specifications** | Original spec, system documentation, and updated specification v2. | [`docs/spec_v2.md`](file:///E:/Agentathon/MINDMESH/docs/spec_v2.md) |

---

## 🛡️ Security & Boundary Guarantees

1. **Hard Spend Cap:** Enforces a strict circuit breaker of at most **4 LLM model calls** per concept session (`SpendLimitExceededError`). Curated questions evaluate deterministically at 0 LLM cost.
2. **Prompt Injection Defense:** Student submissions are wrapped within `<STUDENT_ANSWER>` tags and evaluated strictly as data, never as executable model instructions. Tested against adversarial escape attempts in `test_adversarial.py`.
3. **Revision Limit:** Bounded to **1 follow-up round** per session based directly on stored database records, preventing infinite retry loops.
4. **Crash Resumption:** Interrupted sessions can be resumed at any step directly from SQLite or PostgreSQL event logs without data loss.

---

## 🎤 Key Judge Questions & Answers

| Question | Answer |
|---|---|
| **Why is this agentic?** | MindMesh is not a linear question-answer pipeline. It maintains persistent state, evaluates incoming student answers against ground truth, and dynamically changes its execution path: when a confidence mismatch is detected, it takes an adaptive backward transition to ask a targeted question and pauses for the human, resuming later from where it stopped. |
| **Why not just trust the student's 4/5 or 5/5 self-rating?** | The core premise of the system is that self-perception frequently disagrees with demonstrated correctness. Students consistently suffer from the Dunning-Kruger effect on foundational concepts. MindMesh checks the answer independently before deciding whether to trust the rating. |
| **Why does the AI verify correct MCQs with an explanation prompt?** | Multiple-choice questions can be guessed correctly with a 25% random probability. When a student chooses the right option, MindMesh prompts for a brief explanation to distinguish genuine conceptual understanding from lucky guesses. |
| **Why doesn't the AI lecture or teach?** | Teaching is explicitly outside scope. If the agent lectures, the student remains passive. By providing a targeted objection and waiting for the student to formulate the fix, the cognitive work stays with the learner. |
| **How does persistence enable the "Second Encounter"?** | When a student revisits a concept days later, MindMesh reads its prior audit history and explicitly reports what changed: *"Last time you rated yourself 4/5 but needed a follow-up. Today: correct on first attempt — confidence raised from 3 to 5."* |
| **How is cost and latency controlled?** | Standard MCQs evaluate deterministically in 0ms without LLM calls. Dynamic question generation uses anti-repetition prompts with caching, and LLM calls are bounded by a hard 4-call limit per session. |

---

## 📜 License
MindMesh is open-source software licensed under the [MIT License](LICENSE).
