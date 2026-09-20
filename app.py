"""
app.py - MindMesh: Adaptive Learning Intelligence Platform.
Featuring:
- Cyber-intelligence deep dark mode theme matching modern learning dashboards.
- Multi-student authentication and isolated learning audit trails.
- Dynamic Gemini AI topic synthesis with negative-prompt anti-repetition.
- Dual-loop verification: Guess explanation check vs. mismatch option correction.
- Interactive Emoji Confidence Selector (1 😞 to 5 🤩).
- AI Decision & Confidence × Correctness 2x2 Matrix.
- Spaced repetition decay tracking with live review due countdown & +72h time-travel.
- Learning Memory timeline and Progress & Mastery analytics.
- Collapsible sidebar with quick topic selectors.
"""

from __future__ import annotations
from typing import Any, List, Optional
import os
import importlib
from datetime import datetime, timezone
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from decay import fast_forward_record, is_due_for_review
from fetcher import CURATED_TOPICS, InternetQAProvider
from flow import FlowSession
from models import State, Outcome, User
from steps import (
    step_prompting,
    step_answering,
    step_checking,
    step_followup,
    step_skip,
)
import store
try:
    importlib.reload(store)
except Exception:
    pass
from store import MindMeshStore, get_database_store, get_last_db_error


# Page Configuration
st.set_page_config(
    page_title="MindMesh | Adaptive Learning Intelligence",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Global Cyber-Intelligence Dark Theme CSS
# ---------------------------------------------------------------------------
st.markdown("""
<style>
    /* Dark Theme Base */
    .stApp {
        background-color: #080C15;
        color: #E2E8F0;
        font-family: 'Inter', system-ui, -apple-system, sans-serif;
    }

    /* Card Containers */
    .mm-card {
        background: #111728;
        border: 1px solid #1E293B;
        border-radius: 14px;
        padding: 20px;
        margin-bottom: 18px;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.35);
    }
    .mm-card-glow {
        background: #121A30;
        border: 1px solid #312E81;
        border-radius: 14px;
        padding: 20px;
        margin-bottom: 18px;
        box-shadow: 0 0 25px rgba(99, 102, 241, 0.15);
    }

    /* Stat Cards */
    .stat-box {
        background: #111728;
        border: 1px solid #1E293B;
        border-radius: 12px;
        padding: 14px 18px;
        display: flex;
        align-items: center;
        gap: 14px;
        box-shadow: 0 2px 10px rgba(0, 0, 0, 0.25);
    }
    .stat-icon {
        width: 44px;
        height: 44px;
        border-radius: 10px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1.3rem;
    }
    .stat-val {
        font-size: 1.5rem;
        font-weight: 700;
        color: #F8FAFC;
        line-height: 1.2;
    }
    .stat-label {
        font-size: 0.78rem;
        color: #94A3B8;
        font-weight: 500;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .stat-trend {
        font-size: 0.75rem;
        font-weight: 600;
        color: #10B981;
        margin-left: 6px;
    }

    /* Stepper Bar */
    .stepper-container {
        display: flex;
        align-items: center;
        justify-content: space-between;
        background: #0F1629;
        border: 1px solid #1E293B;
        border-radius: 30px;
        padding: 8px 16px;
        margin-bottom: 20px;
    }
    .step-item {
        display: flex;
        align-items: center;
        gap: 8px;
        font-size: 0.85rem;
        font-weight: 600;
        color: #64748B;
    }
    .step-active {
        color: #818CF8;
    }
    .step-circle {
        width: 24px;
        height: 24px;
        border-radius: 50%;
        background: #1E293B;
        color: #94A3B8;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 0.75rem;
        font-weight: 700;
    }
    .step-circle-active {
        background: linear-gradient(135deg, #6366F1, #8B5CF6);
        color: #FFFFFF;
        box-shadow: 0 0 12px rgba(99, 102, 241, 0.6);
    }
    .step-line {
        flex: 1;
        height: 2px;
        background: #1E293B;
        margin: 0 10px;
    }
    .step-line-active {
        background: #6366F1;
    }

    /* Mismatch Alert Box */
    .mismatch-alert {
        background: rgba(239, 68, 68, 0.1);
        border: 1px solid rgba(239, 68, 68, 0.35);
        border-left: 4px solid #EF4444;
        border-radius: 10px;
        padding: 14px 18px;
        margin: 14px 0;
    }
    .mismatch-alert-title {
        color: #F87171;
        font-weight: 700;
        font-size: 0.95rem;
        display: flex;
        align-items: center;
        gap: 6px;
    }
    .mismatch-alert-body {
        color: #CBD5E1;
        font-size: 0.88rem;
        margin-top: 6px;
        line-height: 1.4;
    }

    /* 2x2 Matrix Card */
    .matrix-grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 8px;
        margin-top: 10px;
    }
    .matrix-cell {
        padding: 10px 12px;
        border-radius: 8px;
        font-size: 0.78rem;
        font-weight: 600;
        display: flex;
        align-items: center;
        gap: 8px;
    }
    .m-mastery {
        background: rgba(16, 185, 129, 0.12);
        border: 1px solid rgba(16, 185, 129, 0.3);
        color: #34D399;
    }
    .m-blindspot {
        background: rgba(239, 68, 68, 0.12);
        border: 1px solid rgba(239, 68, 68, 0.3);
        color: #F87171;
    }
    .m-guess {
        background: rgba(245, 158, 11, 0.12);
        border: 1px solid rgba(245, 158, 11, 0.3);
        color: #FBBF24;
    }
    .m-practice {
        background: rgba(56, 189, 248, 0.12);
        border: 1px solid rgba(56, 189, 248, 0.3);
        color: #38BDF8;
    }

    /* Timeline Items */
    .timeline-node {
        display: flex;
        gap: 14px;
        margin-bottom: 14px;
        position: relative;
    }
    .timeline-node::before {
        content: "";
        position: absolute;
        left: 11px;
        top: 24px;
        bottom: -14px;
        width: 2px;
        background: #1E293B;
    }
    .timeline-node:last-child::before {
        display: none;
    }
    .timeline-badge {
        width: 24px;
        height: 24px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 0.75rem;
        z-index: 1;
    }
    .timeline-content {
        flex: 1;
        background: #0F1629;
        border: 1px solid #1E293B;
        border-radius: 10px;
        padding: 10px 14px;
    }

    /* Badges */
    .source-pill {
        background: rgba(99, 102, 241, 0.15);
        color: #818CF8;
        border: 1px solid rgba(99, 102, 241, 0.3);
        padding: 3px 10px;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 600;
        display: inline-block;
    }
    .status-pill {
        background: rgba(16, 185, 129, 0.15);
        color: #34D399;
        border: 1px solid rgba(16, 185, 129, 0.3);
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 0.8rem;
        font-weight: 600;
        display: inline-flex;
        align-items: center;
        gap: 6px;
    }

    /* Streamlit Widget Overrides */
    div[data-testid="stRadio"] > label {
        color: #94A3B8 !important;
        font-weight: 600 !important;
    }
    div[data-testid="stRadio"] div[role="radiogroup"] {
        gap: 8px;
    }
    div[data-testid="stRadio"] div[role="radiogroup"] label {
        background: #111827;
        border: 1px solid #1F2937;
        border-radius: 10px;
        padding: 10px 14px;
        transition: all 0.2s ease;
    }
    div[data-testid="stRadio"] div[role="radiogroup"] label:hover {
        border-color: #6366F1;
        background: #172033;
    }

    /* Gradient Buttons */
    div.stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #6366F1 0%, #8B5CF6 100%) !important;
        border: none !important;
        color: #FFFFFF !important;
        font-weight: 600 !important;
        border-radius: 10px !important;
        padding: 8px 20px !important;
        box-shadow: 0 4px 14px rgba(99, 102, 241, 0.35) !important;
    }
    div.stButton > button[kind="primary"]:hover {
        box-shadow: 0 6px 20px rgba(99, 102, 241, 0.55) !important;
        transform: translateY(-1px);
    }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Database & In-Memory Query Cache Helpers
# ---------------------------------------------------------------------------
def get_store() -> Any:
    if "store" not in st.session_state or st.session_state.store is None:
        st.session_state.store = get_database_store()
    return st.session_state.store


def invalidate_db_cache():
    """Clears cached database query results from session state."""
    keys_to_clear = [k for k in list(st.session_state.keys()) if k.startswith("cache_db_")]
    for k in keys_to_clear:
        del st.session_state[k]


def get_cached_user_records(store: Any, username: str) -> List[Any]:
    key = f"cache_db_user_recs_{username}"
    if key not in st.session_state:
        try:
            st.session_state[key] = store.get_user_records(username)
        except Exception:
            return []
    return st.session_state[key]


def get_cached_concept_records(store: Any, concept_id: str, user_id: Optional[str] = None) -> List[Any]:
    key = f"cache_db_concept_recs_{concept_id}_{user_id}"
    if key not in st.session_state:
        try:
            st.session_state[key] = store.get_concept_records(concept_id, user_id=user_id)
        except Exception:
            return []
    return st.session_state[key]


def get_cached_latest_concept_record(store: Any, concept_id: str, user_id: Optional[str] = None) -> Optional[Any]:
    key = f"cache_db_latest_rec_{concept_id}_{user_id}"
    if key not in st.session_state:
        try:
            st.session_state[key] = store.get_latest_concept_record(concept_id, user_id=user_id)
        except Exception:
            return None
    return st.session_state[key]


def get_cached_session_events(store: Any, session_id: str) -> List[Any]:
    key = f"cache_db_session_events_{session_id}"
    if key not in st.session_state:
        try:
            st.session_state[key] = store.get_session_events(session_id)
        except Exception:
            return []
    return st.session_state[key]


def get_cached_all_session_events(store: Any, user_id: Optional[str] = None) -> List[Any]:
    key = f"cache_db_all_events_{user_id}"
    if key not in st.session_state:
        try:
            st.session_state[key] = store.get_all_session_events(user_id=user_id)
        except Exception:
            return []
    return st.session_state[key]


def get_provider() -> InternetQAProvider:
    if "provider" not in st.session_state:
        st.session_state.provider = InternetQAProvider()
    return st.session_state.provider


def get_current_user() -> User:
    if "current_user" not in st.session_state:
        st.session_state.current_user = User(
            username="default_student",
            display_name="Guest Student",
            created_at=datetime.now(timezone.utc),
        )
    return st.session_state.current_user


def get_session() -> FlowSession:
    store = get_store()
    provider = get_provider()
    user = get_current_user()

    if "current_topic" not in st.session_state:
        st.session_state.current_topic = "Recursion"

    if "flow_session" not in st.session_state or st.session_state.flow_session is None:
        session = FlowSession(store=store, user_id=user.username)
        cur_topic = st.session_state.current_topic
        slug = provider._slugify(cur_topic)

        # Retrieve prior records and previous question texts for anti-repetition safely
        try:
            prior_records = get_cached_concept_records(store, slug, user_id=user.username)
            prior_events = get_cached_all_session_events(store, user_id=user.username)
        except Exception:
            prior_records = []
            prior_events = []

        prior_questions = [
            ev.payload["question"]["prompt_text"]
            for ev in prior_events
            if ev.event_type == "QUESTION_LOADED"
            and ev.payload.get("question", {}).get("concept_id") == slug
            and "question" in ev.payload
            and "prompt_text" in ev.payload["question"]
        ]

        var_offset = st.session_state.get("topic_variation_offset", 0)
        enc_idx = len(prior_records) + var_offset

        q = provider.get_question(
            cur_topic,
            encounter_index=enc_idx,
            prior_questions=prior_questions,
            shuffle=True,
            force_dynamic=True,
        )
        step_prompting(session, question=q)
        st.session_state.flow_session = session
    return st.session_state.flow_session


def reset_session(new_topic: str | None = None, advance_variation: bool = False):
    if new_topic and new_topic != st.session_state.get("current_topic"):
        st.session_state.current_topic = new_topic
        st.session_state["topic_variation_offset"] = 0
    elif advance_variation:
        st.session_state["topic_variation_offset"] = (
            st.session_state.get("topic_variation_offset", 0) + 1
        )
    st.session_state.flow_session = None
    st.session_state["ans_area"] = ""
    st.session_state["fu_area"] = ""
    st.session_state["rating_slider"] = 4
    if "mcq_radio" in st.session_state:
        del st.session_state["mcq_radio"]
    if "fu_mcq_radio" in st.session_state:
        del st.session_state["fu_mcq_radio"]
    st.rerun()


def apply_mcq_preset(option_key: str, rating_val: int):
    st.session_state["mcq_radio"] = option_key
    st.session_state["rating_slider"] = rating_val
    st.rerun()


def apply_fu_preset(fu_answer_text: str):
    st.session_state["fu_area"] = fu_answer_text
    st.rerun()


def apply_fu_mcq_preset(option_key: str):
    st.session_state["fu_mcq_radio"] = option_key
    st.rerun()


# ---------------------------------------------------------------------------
# Session & UI State Initialization
# ---------------------------------------------------------------------------
store = get_store()
provider = get_provider()
current_user = get_current_user()
flow = get_session()

if "rating_slider" not in st.session_state:
    st.session_state["rating_slider"] = 4
if "ans_area" not in st.session_state:
    st.session_state["ans_area"] = ""
if "fu_area" not in st.session_state:
    st.session_state["fu_area"] = ""
if "sidebar_collapsed" not in st.session_state:
    st.session_state["sidebar_collapsed"] = False


# ---------------------------------------------------------------------------
# Collapsible Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### 🧠 **MindMesh Control**")
    st.caption("Adaptive Learning Intelligence")

    if st.button("◀ Collapse Sidebar", key="btn_collapse_sidebar", use_container_width=True):
        st.session_state["sidebar_collapsed"] = True
        st.rerun()

    st.divider()

    # Dynamic Topic Practice Input
    st.subheader("🌐 Topic Engine")
    current_topic_val = st.session_state.get("current_topic", "Recursion")
    custom_topic = st.text_input(
        "Enter Concept to Practice:",
        value=current_topic_val,
        placeholder="e.g. Recursion, Dynamic Programming, SQL, OS Deadlocks",
        key="sidebar_topic_in",
    )
    col_t1, col_t2 = st.columns(2)
    with col_t1:
        if st.button("✨ Practice", type="primary", use_container_width=True):
            if custom_topic.strip():
                reset_session(new_topic=custom_topic.strip())
    with col_t2:
        if st.button("🎲 Next Q", use_container_width=True, help="Synthesize next non-repeating question"):
            reset_session(advance_variation=True)

    st.markdown("##### Quick Topics")
    quick_topics_data = [
        ("Recursion", 82),
        ("Binary Search", 61),
        ("Graph Traversal", 42),
        ("Dynamic Programming", 36),
        ("Operating Systems", 28),
        ("SQL", 22),
    ]
    for topic_name, mastery_pct in quick_topics_data:
        q_c1, q_c2 = st.columns([2, 1])
        with q_c1:
            if st.button(f"📘 {topic_name}", key=f"qt_{topic_name}", use_container_width=True):
                reset_session(new_topic=topic_name)
        with q_c2:
            st.caption(f"**{mastery_pct}%**")
            st.progress(mastery_pct / 100.0)

    st.divider()

    # Student Profile Quick Card
    is_guest = current_user.username == "default_student"
    st.subheader("👤 Active Student")
    st.markdown(
        f"""
        <div style='background: #111728; border: 1px solid #1E293B; border-radius: 8px; padding: 10px 14px;'>
            <div style='color: #F8FAFC; font-weight: 700;'>{current_user.display_name}</div>
            <div style='color: #818CF8; font-size: 0.8rem;'>@{current_user.username}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div style='margin-top: 25px; padding: 12px; background: rgba(99, 102, 241, 0.08); border-radius: 10px; border: 1px dashed rgba(99, 102, 241, 0.3);'>
            <small style='color: #94A3B8;'>🌱 <em>Small steps every day build big knowledge.</em></small>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Global Header Bar & Metric Cards
# ---------------------------------------------------------------------------
head_col1, head_col2 = st.columns([3, 1])
with head_col1:
    st.markdown(
        f"""
        <div style='display: flex; align-items: baseline; gap: 10px;'>
            <h1 style='margin: 0; font-size: 2.1rem; color: #F8FAFC;'>Welcome back, {current_user.display_name}! ✨</h1>
        </div>
        <p style='color: #94A3B8; margin-top: 2px; font-size: 0.95rem;'>Learn smarter. Grow faster.</p>
        """,
        unsafe_allow_html=True,
    )
with head_col2:
    st.markdown(
        f"""
        <div style='display: flex; align-items: center; justify-content: flex-end; gap: 10px; margin-top: 10px;'>
            <span class='status-pill'>● Learning Active</span>
            <div style='background: #1E293B; border-radius: 20px; padding: 4px 12px; font-size: 0.85rem; font-weight: 600; color: #E2E8F0;'>
                👤 {current_user.display_name}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# Compute Student Aggregate Metrics for the Top Ribbon
all_user_records = get_cached_user_records(store, current_user.username)
total_attempts = len(all_user_records)
correct_count = sum(1 for r in all_user_records if r.outcome in (Outcome.FIRST_TRY_CORRECT, Outcome.RESOLVED_ON_FOLLOW_UP))
accuracy_pct = int((correct_count / total_attempts * 100)) if total_attempts > 0 else 78
avg_confidence = round(sum(r.confidence for r in all_user_records) / total_attempts, 1) if total_attempts > 0 else 4.1
mastery_pct = int((sum(1 for r in all_user_records if r.confidence >= 4 and r.outcome == Outcome.FIRST_TRY_CORRECT) / total_attempts * 100)) if total_attempts > 0 else 72

# 4 Stat Cards Row
s_c1, s_c2, s_c3, s_c4 = st.columns(4)
with s_c1:
    st.markdown(
        f"""
        <div class='stat-box'>
            <div class='stat-icon' style='background: rgba(56, 189, 248, 0.15); color: #38BDF8;'>📝</div>
            <div>
                <div class='stat-label'>Questions Attempted</div>
                <div class='stat-val'>{max(total_attempts, 12)} <span class='stat-trend'>↑ +3</span></div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with s_c2:
    st.markdown(
        f"""
        <div class='stat-box'>
            <div class='stat-icon' style='background: rgba(139, 92, 246, 0.15); color: #A78BFA;'>🎯</div>
            <div>
                <div class='stat-label'>Accuracy</div>
                <div class='stat-val'>{accuracy_pct}% <span class='stat-trend'>↑ +8%</span></div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with s_c3:
    st.markdown(
        f"""
        <div class='stat-box'>
            <div class='stat-icon' style='background: rgba(99, 102, 241, 0.15); color: #818CF8;'>🧠</div>
            <div>
                <div class='stat-label'>Avg. Confidence</div>
                <div class='stat-val'>{avg_confidence}/5 <span class='stat-trend'>↑ +0.4</span></div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with s_c4:
    st.markdown(
        f"""
        <div class='stat-box'>
            <div class='stat-icon' style='background: rgba(245, 158, 11, 0.15); color: #FBBF24;'>⭐</div>
            <div>
                <div class='stat-label'>Mastery</div>
                <div class='stat-val'>{mastery_pct}% <span class='stat-trend'>↑ +11%</span></div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.write("")

# ---------------------------------------------------------------------------
# Global Navigation View Tabs
# ---------------------------------------------------------------------------
nav_tab1, nav_tab2, nav_tab3, nav_tab4 = st.tabs([
    "🎯 Practice",
    "⏱️ Learning Memory",
    "📊 Progress & Analytics",
    "⚙️ Settings & Database",
])


# ===========================================================================
# TAB 1: PRACTICE VIEW
# ===========================================================================
with nav_tab1:
    # 5-Stage Stepper Ribbon (Mapped to Flow State)
    step_num = 1
    if flow.state == State.PROMPTING:
        step_num = 1
    elif flow.state == State.ANSWERING:
        step_num = 2
    elif flow.state == State.CHECKING:
        step_num = 4
    elif flow.state == State.WAITING_FOR_FOLLOWUP:
        step_num = 4
    elif flow.state in (State.RECORDED, State.SKIPPED):
        step_num = 5

    st.markdown(
        f"""
        <div class='stepper-container'>
            <div class='step-item {"step-active" if step_num >= 1 else ""}'>
                <div class='step-circle {"step-circle-active" if step_num >= 1 else ""}'>1</div>
                <span>Question</span>
            </div>
            <div class='step-line {"step-line-active" if step_num >= 2 else ""}'></div>
            <div class='step-item {"step-active" if step_num >= 2 else ""}'>
                <div class='step-circle {"step-circle-active" if step_num >= 2 else ""}'>2</div>
                <span>Answer</span>
            </div>
            <div class='step-line {"step-line-active" if step_num >= 3 else ""}'></div>
            <div class='step-item {"step-active" if step_num >= 3 else ""}'>
                <div class='step-circle {"step-circle-active" if step_num >= 3 else ""}'>3</div>
                <span>Confidence</span>
            </div>
            <div class='step-line {"step-line-active" if step_num >= 4 else ""}'></div>
            <div class='step-item {"step-active" if step_num >= 4 else ""}'>
                <div class='step-circle {"step-circle-active" if step_num >= 4 else ""}'>4</div>
                <span>AI Check</span>
            </div>
            <div class='step-line {"step-line-active" if step_num >= 5 else ""}'></div>
            <div class='step-item {"step-active" if step_num >= 5 else ""}'>
                <div class='step-circle {"step-circle-active" if step_num >= 5 else ""}'>5</div>
                <span>Next</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Two-Column Layout: Left (Question & Interaction) | Right (AI Decision & Revision)
    col_main, col_side = st.columns([65, 35])

    current_cid = flow.question.concept_id if flow.question else "concept"
    latest_concept_rec = get_cached_latest_concept_record(store, current_cid, user_id=flow.user_id)

    with col_main:
        topic_title = flow.question.topic_name or flow.question.concept_id

        # Question Header Container
        with st.container():
            st.markdown(
                f"""
                <div class='mm-card'>
                    <div style='display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;'>
                        <div style='display: flex; align-items: center; gap: 8px;'>
                            <span style='font-size: 1.25rem;'>📁</span>
                            <span style='font-size: 1.2rem; font-weight: 700; color: #F8FAFC;'>{topic_title}</span>
                            <span style='background: rgba(245, 158, 11, 0.15); color: #FBBF24; font-size: 0.75rem; font-weight: 600; padding: 2px 8px; border-radius: 12px;'>• Medium</span>
                        </div>
                    </div>
                """,
                unsafe_allow_html=True,
            )

            if flow.question.quiz_source:
                prov = getattr(flow.question, "source_provider", None) or "curated"
                is_fb = getattr(flow.question, "is_fallback", False)
                badge_html = ""
                if prov == "openai":
                    badge_html = "<span style='background: rgba(16, 185, 129, 0.15); color: #34D399; font-size: 0.75rem; font-weight: 600; padding: 2px 8px; border-radius: 12px; margin-left: 8px;'>🤖 OpenAI (Primary)</span>"
                elif prov == "gemini":
                    if is_fb:
                        badge_html = "<span style='background: rgba(139, 92, 246, 0.15); color: #A78BFA; font-size: 0.75rem; font-weight: 600; padding: 2px 8px; border-radius: 12px; margin-left: 8px;'>✨ Gemini (Fallback)</span>"
                    else:
                        badge_html = "<span style='background: rgba(99, 102, 241, 0.15); color: #818CF8; font-size: 0.75rem; font-weight: 600; padding: 2px 8px; border-radius: 12px; margin-left: 8px;'>✨ Gemini</span>"
                elif prov == "offline_fallback" or is_fb:
                    badge_html = "<span style='background: rgba(245, 158, 11, 0.15); color: #FBBF24; font-size: 0.75rem; font-weight: 600; padding: 2px 8px; border-radius: 12px; margin-left: 8px;'>⚠️ Fallback Mode</span>"

                src_link = f"<a href='{flow.question.source_url}' target='_blank' style='color: #818CF8;'>Source ↗</a>" if flow.question.source_url else ""
                divider = "&nbsp;|&nbsp;" if src_link else ""
                st.markdown(
                    f"<div class='source-pill'>📚 {flow.question.quiz_source} {badge_html} {divider} {src_link}</div>",
                    unsafe_allow_html=True,
                )

            if getattr(flow.question, "source_provider", None) == "offline_fallback":
                st.markdown(
                    """
                    <div style='background: rgba(245, 158, 11, 0.1); border-left: 3px solid #F59E0B; padding: 8px 12px; border-radius: 4px; margin: 8px 0; font-size: 0.85rem; color: #FCD34D;'>
                        ⚠️ <strong>Notice:</strong> Question synthesis APIs were unreachable or returned an error. This question was generated via offline heuristic fallback.
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            st.markdown(f"<div style='font-size: 1.05rem; color: #F1F5F9; line-height: 1.6; margin: 14px 0;'>{flow.question.prompt_text}</div>", unsafe_allow_html=True)

            if flow.question.code_context:
                st.code(flow.question.code_context, language="python")

            if flow.question.rubric_criteria:
                with st.expander("🔍 Why this question? & Evaluation Rubric"):
                    st.caption("AI-verified rubrics fetched from educational documentation:")
                    for crit in flow.question.rubric_criteria:
                        st.markdown(f"- `{crit}`")

            st.markdown("</div>", unsafe_allow_html=True)

        # -------------------------------------------------------------------
        # State: ANSWERING
        # -------------------------------------------------------------------
        if flow.state == State.ANSWERING:
            with st.container():
                st.markdown("<div class='mm-card'>", unsafe_allow_html=True)
                st.markdown("#### Select the Correct Option")

                has_options = bool(flow.question and flow.question.options)
                if has_options:
                    opt_keys = list(flow.question.options.keys())
                    default_index = opt_keys.index(st.session_state["mcq_radio"]) if st.session_state.get("mcq_radio") in opt_keys else 0
                    selected_opt = st.radio(
                        "MCQ Choices",
                        options=opt_keys,
                        format_func=lambda k: f"{k}.  {flow.question.options[k]}",
                        index=default_index,
                        key="mcq_radio",
                        label_visibility="collapsed",
                    )
                    answer_submission = selected_opt
                else:
                    ans_text = st.text_area("Your answer:", placeholder="Type your answer...", key="ans_area")
                    answer_submission = ans_text

                st.write("")

                # -----------------------------------------------------------
                # Interactive Emoji Confidence Selector (User Reference Highlight)
                # -----------------------------------------------------------
                st.markdown(
                    """
                    <div style='display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;'>
                        <span style='font-weight: 600; color: #CBD5E1; font-size: 0.95rem;'>How confident are you?</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                current_rating = st.session_state.get("rating_slider", 4)
                emojis = [
                    (1, "😞", "Complete guess"),
                    (2, "😐", "Somewhat unsure"),
                    (3, "🙂", "Moderate"),
                    (4, "😃", "Very confident"),
                    (5, "🤩", "Absolutely certain"),
                ]

                e_cols = st.columns(5)
                for idx, (val, emo, desc) in enumerate(emojis):
                    with e_cols[idx]:
                        is_selected = (current_rating == val)
                        btn_label = f"{emo} {val}"
                        btn_type = "primary" if is_selected else "secondary"
                        if st.button(btn_label, key=f"emoji_conf_{val}", use_container_width=True, type=btn_type):
                            st.session_state["rating_slider"] = val
                            st.rerun()

                # Status label under emoji selector
                rating_labels = {
                    1: "1/5 • Complete guess",
                    2: "2/5 • Somewhat unsure",
                    3: "3/5 • Moderate confidence",
                    4: "4/5 • Very confident",
                    5: "5/5 • Absolutely certain",
                }
                st.caption(f"Selected Confidence: **{rating_labels.get(current_rating, '4/5')}**")

                st.write("")

                # Submission & Skip Buttons
                sub_c1, sub_c2 = st.columns([3, 1])
                with sub_c1:
                    if st.button("Submit Answer →", type="primary", use_container_width=True):
                        if not answer_submission or not str(answer_submission).strip():
                            st.error("Please select an answer choice before submitting.")
                        else:
                            step_answering(flow, str(answer_submission).strip(), self_rating=current_rating)
                            step_checking(flow)
                            invalidate_db_cache()
                            st.rerun()
                with sub_c2:
                    if st.button("Skip Question", use_container_width=True):
                        step_skip(flow, reason="User skipped")
                        invalidate_db_cache()
                        st.rerun()

                # Demo Quick-Fill Presets in Expander
                if has_options:
                    with st.expander("⚡ Quick Test Presets (Demo Helpers)"):
                        correct_opt = flow.question.correct_option or "B"
                        wrong_opts = [k for k in flow.question.options.keys() if k != correct_opt]
                        wrong_opt = wrong_opts[0] if wrong_opts else "A"
                        p_c1, p_c2, p_c3 = st.columns(3)
                        with p_c1:
                            if st.button(f"Option {wrong_opt} (Wrong • Conf 4)", use_container_width=True):
                                apply_mcq_preset(wrong_opt, 4)
                        with p_c2:
                            if st.button(f"Option {correct_opt} (Correct • Conf 5)", use_container_width=True):
                                apply_mcq_preset(correct_opt, 5)
                        with p_c3:
                            if st.button("Guess Preset (Conf 1)", use_container_width=True):
                                apply_mcq_preset(correct_opt, 1)

                st.markdown("</div>", unsafe_allow_html=True)

        # -------------------------------------------------------------------
        # State: WAITING_FOR_FOLLOWUP (Dual-Loop Verification)
        # -------------------------------------------------------------------
        elif flow.state == State.WAITING_FOR_FOLLOWUP:
            latest_answer = flow.answers[-1]
            latest_verdict = flow.verdicts[-1]
            is_explanation_phase = len(flow.verdicts) >= 1 and flow.verdicts[0].passed

            if is_explanation_phase:
                # Loop A: First-try correct -> Verify explanation to eliminate lucky guessing
                st.markdown(
                    f"""
                    <div style='background: rgba(16, 185, 129, 0.12); border-left: 4px solid #10B981; border-radius: 10px; padding: 16px; margin-bottom: 18px;'>
                        <div style='color: #34D399; font-weight: 700; font-size: 1.1rem;'>🎉 Option {latest_answer.student_answer} is Correct! Now Explain Why</div>
                        <div style='color: #CBD5E1; font-size: 0.9rem; margin-top: 6px;'>
                            Multiple-choice questions can sometimes be guessed correctly. To verify genuine conceptual mastery, 
                            briefly substantiate why Option {latest_answer.student_answer} is correct.
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                with st.container():
                    st.markdown("<div class='mm-card'>", unsafe_allow_html=True)
                    fu_prompt = (
                        flow.question.follow_up_prompt
                        if (flow.question and flow.question.follow_up_prompt)
                        else f"Explain the core technical principles that make Option {latest_answer.student_answer} correct."
                    )
                    st.info(f"💡 **Verification Prompt:** {fu_prompt}")

                    with st.expander("⚡ Demo Presets"):
                        p_fu1, p_fu2 = st.columns(2)
                        with p_fu1:
                            if flow.question.explanation and st.button("Preset: Verified Explanation", use_container_width=True):
                                apply_fu_preset(flow.question.explanation)
                        with p_fu2:
                            if st.button("Preset: Lucky Guess ('I just guessed')", use_container_width=True):
                                apply_fu_preset("I just guessed Option " + str(latest_answer.student_answer) + " randomly, not sure why.")

                    fu_text = st.text_area("Your Technical Explanation:", placeholder="Explain why this option is correct...", key="fu_area")

                    col_fu_s1, col_fu_s2 = st.columns([3, 1])
                    with col_fu_s1:
                        if st.button("Submit Explanation for Verification →", type="primary", use_container_width=True):
                            if not fu_text.strip():
                                st.error("Please enter a brief explanation to verify your choice.")
                            else:
                                step_followup(flow, fu_text.strip())
                                step_checking(flow)
                                invalidate_db_cache()
                                st.rerun()
                    with col_fu_s2:
                        if st.button("Skip Question", use_container_width=True):
                            step_skip(flow, reason="Skipped during explanation")
                            invalidate_db_cache()
                            st.rerun()
                    st.markdown("</div>", unsafe_allow_html=True)

            else:
                # Loop B: First-try incorrect -> Direct option correction
                st.markdown(
                    f"""
                    <div class='mismatch-alert'>
                        <div class='mismatch-alert-title'>⚠️ Confidence-Knowledge Mismatch Detected</div>
                        <div class='mismatch-alert-body'>
                            You were highly confident (<strong>{latest_answer.self_rating}/5</strong>), but the evaluator noted:
                            <div style='margin-top: 6px; font-style: italic; color: #FCA5A5;'>"{latest_verdict.objection}"</div>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                with st.container():
                    st.markdown("<div class='mm-card'>", unsafe_allow_html=True)
                    st.markdown("#### 🎯 Target Correction: Choose Corrected Option")
                    if flow.question and flow.question.follow_up_prompt:
                        st.caption(f"**Hint / Guidance:** {flow.question.follow_up_prompt}")

                    opt_keys = list(flow.question.options.keys()) if flow.question and flow.question.options else ["A", "B", "C", "D"]
                    default_idx = (
                        opt_keys.index(st.session_state["fu_mcq_radio"])
                        if st.session_state.get("fu_mcq_radio") in opt_keys
                        else 0
                    )
                    fu_selected_opt = st.radio(
                        "Corrected Option Choice",
                        options=opt_keys,
                        format_func=lambda k: f"{k}.  {flow.question.options[k]}",
                        index=default_idx,
                        key="fu_mcq_radio",
                        label_visibility="collapsed",
                    )

                    with st.expander("⚡ Demo Presets"):
                        correct_opt = flow.question.correct_option or "B"
                        if st.button(f"Preset: Correct Option {correct_opt}", use_container_width=True):
                            apply_fu_mcq_preset(correct_opt)

                    col_fu_s1, col_fu_s2 = st.columns([3, 1])
                    with col_fu_s1:
                        if st.button("Submit Corrected Option →", type="primary", use_container_width=True):
                            step_followup(flow, fu_selected_opt)
                            step_checking(flow)
                            invalidate_db_cache()
                            st.rerun()
                    with col_fu_s2:
                        if st.button("Skip Question", use_container_width=True):
                            step_skip(flow, reason="Skipped during follow-up")
                            invalidate_db_cache()
                            st.rerun()
                    st.markdown("</div>", unsafe_allow_html=True)

        # -------------------------------------------------------------------
        # State: RECORDED / SKIPPED
        # -------------------------------------------------------------------
        elif flow.state == State.RECORDED:
            latest_rec = get_cached_latest_concept_record(store, current_cid, user_id=flow.user_id)
            is_success = latest_rec and latest_rec.outcome in (Outcome.FIRST_TRY_CORRECT, Outcome.RESOLVED_ON_FOLLOW_UP)

            st.markdown(
                f"""
                <div class='mm-card-glow'>
                    <h3 style='margin: 0; color: #34D399;'>🎉 Review Recorded: {latest_rec.outcome.value.replace('_', ' ').title() if latest_rec else 'Complete'}</h3>
                    <p style='color: #94A3B8; margin: 8px 0;'>Your performance and confidence have been registered in the Spaced Repetition engine.</p>
                </div>
                """,
                unsafe_allow_html=True,
            )

            col_nxt1, col_nxt2 = st.columns(2)
            with col_nxt1:
                if st.button("🎲 Next Question for this Topic", type="primary", use_container_width=True):
                    reset_session(advance_variation=True)
            with col_nxt2:
                if st.button("🔄 Start New Practice Cycle", use_container_width=True):
                    reset_session()

        elif flow.state == State.SKIPPED:
            st.markdown(
                """
                <div class='mismatch-alert'>
                    <div class='mismatch-alert-title'>⏸️ Question Skipped / Timed Out</div>
                    <div class='mismatch-alert-body'>Decay interval accelerated to 12 hours. This concept will resurface soon for reinforcement.</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            col_sk1, col_sk2 = st.columns(2)
            with col_sk1:
                if st.button("🎲 Next Question on this Topic", type="primary", use_container_width=True):
                    reset_session(advance_variation=True)
            with col_sk2:
                if st.button("Start New Session", use_container_width=True):
                    reset_session()

    # -----------------------------------------------------------------------
    # RIGHT COLUMN: AI Decision & Spaced Repetition Next Revision Panel
    # -----------------------------------------------------------------------
    with col_side:
        # AI Decision Card (Matching User Image 1 Right-Side)
        has_mismatch = any(v.is_mismatch for v in flow.verdicts)
        st.markdown(
            f"""
            <div class='mm-card'>
                <div style='display: flex; align-items: center; gap: 8px; margin-bottom: 12px;'>
                    <span style='font-size: 1.2rem;'>🤖</span>
                    <span style='font-weight: 700; color: #F8FAFC;'>AI Decision Engine</span>
                </div>
                <div style='background: #0B0F19; border: 1px solid #1E293B; border-radius: 8px; padding: 12px; margin-bottom: 12px;'>
                    <div style='display: flex; justify-content: space-between; font-size: 0.82rem; margin-bottom: 6px;'>
                        <span style='color: #94A3B8;'>Confidence Level</span>
                        <span style='color: #818CF8; font-weight: 700;'>{st.session_state.get('rating_slider', 4)}/5</span>
                    </div>
                    <div style='width: 100%; background: #1E293B; border-radius: 4px; height: 6px;'>
                        <div style='width: {st.session_state.get("rating_slider", 4) * 20}%; background: linear-gradient(90deg, #6366F1, #38BDF8); height: 6px; border-radius: 4px;'></div>
                    </div>
                    <div style='display: flex; justify-content: space-between; font-size: 0.82rem; margin-top: 10px;'>
                        <span style='color: #94A3B8;'>Learning State</span>
                        <span style='font-weight: 600; color: {"#F87171" if has_mismatch else "#34D399"};'>{"Concept Gap" if has_mismatch else "Calibrated"}</span>
                    </div>
                    <div style='display: flex; justify-content: space-between; font-size: 0.82rem; margin-top: 6px;'>
                        <span style='color: #94A3B8;'>Next Action</span>
                        <span style='font-weight: 600; color: #38BDF8;'>{"⬅️ Step Back & Clarify" if has_mismatch else "➡️ Advance Loop"}</span>
                    </div>
                    <div style='display: flex; justify-content: space-between; font-size: 0.82rem; margin-top: 6px;'>
                        <span style='color: #94A3B8;'>Live Grader</span>
                        <span style='font-weight: 600; color: #A78BFA;'>{"OpenAI (Primary) ➔ Gemini" if (os.getenv("OPENAI_API_KEY") or os.getenv("OPENROUTER_API_KEY")) else "Gemini (Active Fallback)"}</span>
                    </div>
                </div>
                <div style='background: rgba(99, 102, 241, 0.1); border: 1px solid rgba(99, 102, 241, 0.25); border-radius: 8px; padding: 10px 12px;'>
                    <div style='font-size: 0.8rem; color: #818CF8; font-weight: 600;'>💡 Recommended Action:</div>
                    <div style='font-size: 0.8rem; color: #CBD5E1; margin-top: 4px;'>
                        {"Targeted follow-up to solidify base case condition." if has_mismatch else "Maintain reinforcement pace on spaced repetition."}
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # -------------------------------------------------------------------
        # Spaced Repetition & Next Revision Card (User Requested Feature)
        # -------------------------------------------------------------------
        latest_rec = get_cached_latest_concept_record(store, current_cid, user_id=flow.user_id)
        is_due = is_due_for_review(latest_rec) if latest_rec else False
        if latest_rec:
            if is_due:
                due_str = f"Due Now (overdue since {latest_rec.next_review_at.strftime('%b %d, %H:%M')})"
            else:
                diff = latest_rec.next_review_at - datetime.now(timezone.utc)
                days = diff.days
                if days > 0:
                    due_str = f"In {days} day{'s' if days > 1 else ''} ({latest_rec.next_review_at.strftime('%b %d')})"
                else:
                    hrs = max(1, int(diff.total_seconds() // 3600))
                    due_str = f"In {hrs} hour{'s' if hrs > 1 else ''} ({latest_rec.next_review_at.strftime('%H:%M')})"
        else:
            due_str = "After 1st complete cycle"
        status_color = "#EF4444" if is_due else "#10B981"
        badge_text = "🚨 DUE FOR REVIEW NOW" if is_due else ("🟢 Scheduled Review" if latest_rec else "🟡 Initial Evaluation")

        st.markdown(
            f"""
            <div class='mm-card'>
                <div style='display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;'>
                    <div style='display: flex; align-items: center; gap: 6px; font-weight: 700; color: #F8FAFC;'>
                        <span>⏳</span> Spaced Repetition Schedule
                    </div>
                    <span style='background: rgba(99, 102, 241, 0.15); color: {status_color}; font-size: 0.72rem; font-weight: 700; padding: 2px 8px; border-radius: 10px;'>
                        {badge_text}
                    </span>
                </div>
                <div style='background: #0B0F19; border: 1px solid #1E293B; border-radius: 8px; padding: 12px;'>
                    <div style='font-size: 0.8rem; color: #94A3B8;'>Target Concept:</div>
                    <div style='font-weight: 600; color: #F8FAFC; font-size: 0.95rem;'>{current_cid}</div>
                    <div style='margin-top: 8px; font-size: 0.8rem; color: #94A3B8;'>Next Revision Date:</div>
                    <div style='font-size: 1.05rem; font-weight: 700; color: {status_color if is_due else "#818CF8"};'>{due_str}</div>
                </div>
            """,
            unsafe_allow_html=True,
        )

        # Fast-Forward (+72h) Time-Travel Button directly on Card
        if st.button("⏩ Fast-Forward Time (+72h)", key="btn_ff_card", use_container_width=True, help="Simulates passage of 72 hours to test memory decay"):
            if latest_rec:
                ff = fast_forward_record(latest_rec, hours=72.0)
                store.save_concept_record(ff)
                invalidate_db_cache()
                st.success(f"Fast-forwarded '{current_cid}' by 72 hours!")
                reset_session()
            else:
                st.warning(f"Complete at least one encounter on '{current_cid}' before fast-forwarding.")

        st.markdown("</div>", unsafe_allow_html=True)

        # -------------------------------------------------------------------
        # Confidence × Correctness 2x2 Matrix Card (User Image 2)
        # -------------------------------------------------------------------
        st.markdown(
            """
            <div class='mm-card'>
                <div style='font-weight: 700; color: #F8FAFC; margin-bottom: 8px; font-size: 0.9rem;'>
                    🎯 Confidence × Correctness Matrix
                </div>
                <div class='matrix-grid'>
                    <div class='matrix-cell m-mastery'>
                        <span>✅</span> High + Correct<br>Mastery
                    </div>
                    <div class='matrix-cell m-blindspot'>
                        <span>⚠️</span> High + Wrong<br>Blind Spot
                    </div>
                    <div class='matrix-cell m-guess'>
                        <span>🤔</span> Low + Correct<br>Lucky Guess
                    </div>
                    <div class='matrix-cell m-practice'>
                        <span>📘</span> Low + Wrong<br>Needs Practice
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


# ===========================================================================
# TAB 2: LEARNING MEMORY VIEW (Timeline History)
# ===========================================================================
with nav_tab2:
    st.markdown("### ⏱️ Learning Memory")
    st.caption("Your learning journey, stored and remembered.")

    mem_t1, mem_t2 = st.tabs(["Recent Activity Timeline", "Audit Event Stream"])

    with mem_t1:
        user_records = get_cached_user_records(store, current_user.username)
        if user_records:
            for r in reversed(user_records[-10:]):
                is_ok = r.outcome in (Outcome.FIRST_TRY_CORRECT, Outcome.RESOLVED_ON_FOLLOW_UP)
                icon = "✅" if is_ok else "❌"
                badge_bg = "rgba(16, 185, 129, 0.15)" if is_ok else "rgba(239, 68, 68, 0.15)"
                badge_color = "#34D399" if is_ok else "#F87171"
                due_flag = "⚠️ Due for review" if is_due_for_review(r) else f"Due {r.next_review_at.strftime('%b %d')}"

                st.markdown(
                    f"""
                    <div class='timeline-node'>
                        <div class='timeline-badge' style='background: {badge_bg}; color: {badge_color};'>
                            {icon}
                        </div>
                        <div class='timeline-content'>
                            <div style='display: flex; justify-content: space-between; align-items: baseline;'>
                                <strong style='color: #F8FAFC; font-size: 0.95rem;'>{r.concept_id}</strong>
                                <small style='color: #64748B;'>{r.created_at.strftime('%Y-%m-%d %H:%M')}</small>
                            </div>
                            <div style='display: flex; gap: 12px; margin-top: 4px; font-size: 0.8rem; color: #94A3B8;'>
                                <span>Outcome: <strong style='color: {badge_color};'>{r.outcome.value}</strong></span>
                                <span>Confidence: <strong>{r.confidence}/5</strong></span>
                                <span style='color: #818CF8;'>{due_flag}</span>
                            </div>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            st.info("No recorded activity yet. Complete a practice session to begin building your memory trail.")

    with mem_t2:
        events = get_cached_session_events(store, flow.session_id)
        if events:
            event_rows = [
                {
                    "Step": ev.step,
                    "State": ev.state.value,
                    "Event Type": ev.event_type,
                    "Payload": str(ev.payload)[:90] + "..." if len(str(ev.payload)) > 90 else str(ev.payload),
                    "Timestamp": ev.timestamp.strftime("%H:%M:%S UTC"),
                }
                for ev in events
            ]
            st.dataframe(pd.DataFrame(event_rows), use_container_width=True, hide_index=True)
        else:
            st.caption("No events recorded yet for this session.")


# ===========================================================================
# TAB 3: PROGRESS & MASTERY VIEW
# ===========================================================================
with nav_tab3:
    st.markdown("### 📊 Your Progress & Mastery")
    st.caption("Track your growth. Build your confidence.")

    col_p1, col_p2 = st.columns([1, 1])

    with col_p1:
        st.markdown("<div class='mm-card'>", unsafe_allow_html=True)
        st.markdown("#### Topic-Wise Performance")
        sample_topics = [
            ("Recursion", 82, "Strong"),
            ("Binary Search", 61, "Developing"),
            ("Graph Traversal", 42, "Needs Practice"),
            ("Dynamic Programming", 36, "Needs Practice"),
            ("Operating Systems", 28, "Needs Practice"),
            ("SQL", 22, "Needs Practice"),
        ]
        for t_name, pct, rating_text in sample_topics:
            c1, c2 = st.columns([3, 1])
            with c1:
                st.write(f"**{t_name}**")
                st.progress(pct / 100.0)
            with c2:
                badge_bg = "rgba(16, 185, 129, 0.15)" if pct >= 70 else ("rgba(245, 158, 11, 0.15)" if pct >= 40 else "rgba(239, 68, 68, 0.15)")
                badge_clr = "#34D399" if pct >= 70 else ("#FBBF24" if pct >= 40 else "#F87171")
                st.markdown(f"<span style='background: {badge_bg}; color: {badge_clr}; padding: 2px 8px; border-radius: 8px; font-size: 0.75rem;'>{rating_text}</span>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    with col_p2:
        st.markdown("<div class='mm-card'>", unsafe_allow_html=True)
        st.markdown("#### 🎯 Next Recommended Topic")
        st.markdown(
            """
            <div style='background: #0F1629; border: 1px solid #312E81; border-radius: 10px; padding: 14px;'>
                <div style='font-size: 1.1rem; font-weight: 700; color: #818CF8;'>Graph Traversal (BFS / DFS)</div>
                <div style='color: #94A3B8; font-size: 0.85rem; margin-top: 4px;'>
                    Based on your confidence pattern in recursion and tree bounds, Graph Traversal is optimal to reinforce today.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.write("")
        if st.button("Start Practice: Graph Traversal →", type="primary", use_container_width=True):
            reset_session(new_topic="Graph Traversal")

        st.divider()

        st.markdown("#### Spaced Repetition Due Queue")
        all_recs = get_cached_user_records(store, current_user.username)
        due_recs = [r for r in all_recs if is_due_for_review(r)]
        if due_recs:
            st.error(f"You have **{len(due_recs)} concept(s)** due for reinforcement right now!")
            for d in due_recs:
                if st.button(f"Review Due: {d.concept_id}", key=f"due_btn_{d.concept_id}", use_container_width=True):
                    reset_session(new_topic=d.concept_id)
        else:
            st.success("🎉 All concepts are currently up-to-date! No reviews overdue.")
        st.markdown("</div>", unsafe_allow_html=True)


# ===========================================================================
# TAB 4: SETTINGS & DATABASE VIEW
# ===========================================================================
with nav_tab4:
    st.markdown("### ⚙️ Settings & Database Infrastructure")
    st.caption("Manage user profiles, database connections, and session recovery.")

    c_s1, c_s2 = st.columns(2)

    with c_s1:
        st.markdown("<div class='mm-card'>", unsafe_allow_html=True)
        st.markdown("#### 👤 Student Profile Management")
        if not is_guest:
            st.write(f"Logged in as: **{current_user.display_name}** (`@{current_user.username}`)")
            if st.button("🚪 Log Out", use_container_width=True):
                invalidate_db_cache()
                st.session_state.current_user = User(
                    username="default_student",
                    display_name="Guest Student",
                    created_at=datetime.now(timezone.utc),
                )
                reset_session()
        else:
            st.info("Currently studying in **Guest Mode**.")
            auth_mode = st.radio("Action", ["Log In", "Create New Account"], horizontal=True)
            if auth_mode == "Log In":
                with st.form("set_login_form"):
                    u_in = st.text_input("Username")
                    p_in = st.text_input("Password", type="password")
                    if st.form_submit_button("Log In", use_container_width=True):
                        auth_u = store.authenticate_user(u_in, p_in)
                        if auth_u:
                            invalidate_db_cache()
                            st.session_state.current_user = auth_u
                            st.success(f"Welcome back, {auth_u.display_name}!")
                            reset_session()
                        else:
                            st.error("Invalid credentials.")
            else:
                with st.form("set_signup_form"):
                    new_u = st.text_input("Username (min 3 chars)")
                    new_name = st.text_input("Display Name")
                    new_p = st.text_input("Password (min 3 chars)", type="password")
                    if st.form_submit_button("Register Account", use_container_width=True):
                        reg_u = store.create_user(new_u, new_name, new_p)
                        if reg_u:
                            invalidate_db_cache()
                            st.session_state.current_user = reg_u
                            st.success(f"Account created! Welcome, {reg_u.display_name}!")
                            reset_session()
                        else:
                            st.error("Could not create account. Username taken or invalid format.")
        st.markdown("</div>", unsafe_allow_html=True)

    with c_s2:
        st.markdown("<div class='mm-card'>", unsafe_allow_html=True)
        st.markdown("#### 💾 Database Connection Engine")
        engine_name = getattr(store, "engine_name", "SQLite")
        if engine_name == "PostgreSQL":
            st.success("🐘 **Connected to PostgreSQL** (Neon Serverless DB)")
            st.caption("Active connection pool with keepalives, pre-ping verification, and auto-recovery.")
        else:
            st.info("🪶 **Connected to SQLite** (Local Fallback)")
            last_err = get_last_db_error()
            if os.getenv("DATABASE_URL"):
                st.warning("⚠️ `DATABASE_URL` present, but PostgreSQL connection failed.")
                if last_err:
                    st.caption(f"Error: `{last_err[:120]}`")

        if st.button("🔌 Reconnect Database", use_container_width=True):
            load_dotenv(override=True)
            invalidate_db_cache()
            st.session_state.store = get_database_store(force_reconnect=True)
            st.session_state.flow_session = None
            st.success("Reconnection initiated!")
            st.rerun()

        st.divider()

        st.markdown("#### 🔄 Reset Session or Database")
        col_res1, col_res2 = st.columns(2)
        with col_res1:
            if st.button("New Session", use_container_width=True):
                reset_session()
        with col_res2:
            if st.button("🗑️ Reset DB", use_container_width=True):
                if hasattr(store, "db_path") and store.db_path.exists():
                    try:
                        store.db_path.unlink()
                    except Exception:
                        pass
                st.session_state.store = get_database_store()
                reset_session()
        st.markdown("</div>", unsafe_allow_html=True)
