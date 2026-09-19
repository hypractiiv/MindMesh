"""
app.py - Streamlit interface for MindMesh with Multi-User Accounts, Dynamic Topic Selection, and Internet Q&A.

Features:
- Student account authentication (Sign-Up / Login / Logout / Guest Mode).
- Student data isolation across learning sessions and review schedules.
- Dynamic topic selection from curated catalog or live web search (Wikipedia / Educational APIs).
- Display of internet source citation and rubric criteria.
- 6-state visual ribbon highlighting the active state.
- Confidence / Correctness mismatch detection with adaptive backward transition.
- Persistent SQLite multi-student event stream and encounter history.
- Spaced repetition decay and debug time-travel fast-forward.
"""

from __future__ import annotations
from typing import Any
import os

from dotenv import load_dotenv
load_dotenv()

import streamlit as st
from datetime import datetime, timezone
import pandas as pd

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
try:
    from store import MindMeshStore, get_database_store
except (ImportError, AttributeError):
    import importlib
    import store
    importlib.reload(store)
    try:
        from store import MindMeshStore, get_database_store
    except (ImportError, AttributeError):
        from store import MindMeshStore
        def get_database_store(db_url: Any = None) -> Any:
            return MindMeshStore()


st.set_page_config(
    page_title="MindMesh | Adaptive Learning-Confidence Tracker",
    page_icon="🧠",
    layout="wide",
)

# Custom styling for states, mismatch alerts, source badges, and profiles
st.markdown("""
<style>
    .state-badge {
        padding: 6px 14px;
        border-radius: 18px;
        font-weight: 600;
        font-size: 0.85rem;
        display: inline-block;
        margin: 2px;
    }
    .state-active {
        background-color: #1a73e8;
        color: white;
        box-shadow: 0 0 10px rgba(26, 115, 232, 0.5);
    }
    .state-inactive {
        background-color: #f1f3f4;
        color: #5f6368;
    }
    .mismatch-box {
        background-color: rgba(249, 171, 0, 0.12);
        border-left: 5px solid #f9ab00;
        padding: 16px;
        border-radius: 6px;
        margin-top: 15px;
        margin-bottom: 15px;
    }
    .mismatch-title {
        color: #e37400;
        font-weight: 700;
        font-size: 1.1rem;
        margin: 0;
    }
    .mismatch-desc {
        margin: 8px 0 0 0;
        font-size: 0.95rem;
    }
    .mismatch-objection {
        font-style: italic;
        margin: 8px 0 0 0;
        font-size: 0.95rem;
        font-weight: 500;
        padding-left: 10px;
        border-left: 2px solid rgba(249, 171, 0, 0.5);
    }
    .source-badge {
        background-color: #e8f0fe;
        color: #1a73e8;
        padding: 4px 10px;
        border-radius: 12px;
        font-size: 0.8rem;
        font-weight: 500;
        display: inline-block;
        margin-bottom: 10px;
    }
    .user-card {
        background-color: #f8f9fa;
        border: 1px solid #dadce0;
        border-radius: 8px;
        padding: 10px 14px;
        margin-bottom: 12px;
    }
</style>
""", unsafe_allow_html=True)


def get_store() -> Any:
    if "store" not in st.session_state:
        st.session_state.store = get_database_store()
    return st.session_state.store


def get_provider() -> InternetQAProvider:
    if "provider" not in st.session_state:
        st.session_state.provider = InternetQAProvider()
    return st.session_state.provider


def get_current_user() -> User:
    if "current_user" not in st.session_state:
        # Default guest profile
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
        st.session_state.current_topic = "recursion_base_case"

    if "flow_session" not in st.session_state or st.session_state.flow_session is None:
        session = FlowSession(store=store, user_id=user.username)
        q = provider.get_question(st.session_state.current_topic)
        step_prompting(session, question=q)
        st.session_state.flow_session = session
    return st.session_state.flow_session


def reset_session(new_topic: str | None = None):
    if new_topic:
        st.session_state.current_topic = new_topic
    st.session_state.flow_session = None
    st.session_state["ans_area"] = ""
    st.session_state["fu_area"] = ""
    st.session_state["rating_slider"] = 4
    if "mcq_radio" in st.session_state:
        del st.session_state["mcq_radio"]
    if "fu_mcq_radio" in st.session_state:
        del st.session_state["fu_mcq_radio"]
    st.rerun()


def apply_preset(answer_text: str, rating_val: int):
    """Directly populates the text area and rating slider widget states and reruns."""
    st.session_state["ans_area"] = answer_text
    st.session_state["rating_slider"] = rating_val
    st.rerun()


def apply_mcq_preset(option_key: str, rating_val: int):
    """Directly selects the MCQ option radio button and rating slider and reruns."""
    st.session_state["mcq_radio"] = option_key
    st.session_state["rating_slider"] = rating_val
    st.rerun()


def apply_fu_preset(fu_answer_text: str):
    """Directly populates the follow-up text area widget state and reruns."""
    st.session_state["fu_area"] = fu_answer_text
    st.rerun()


def apply_fu_mcq_preset(option_key: str):
    """Directly selects the follow-up MCQ option radio button and reruns."""
    st.session_state["fu_mcq_radio"] = option_key
    st.rerun()


store = get_store()
provider = get_provider()
current_user = get_current_user()
flow = get_session()

# Ensure widget keys exist in session state
if "ans_area" not in st.session_state:
    st.session_state["ans_area"] = ""
if "rating_slider" not in st.session_state:
    st.session_state["rating_slider"] = 4
if "fu_area" not in st.session_state:
    st.session_state["fu_area"] = ""

# Sidebar: Accounts, Topic Selection, History
with st.sidebar:
    st.title("🧠 MindMesh Control")
    st.caption("Multi-Student Learning-Confidence Tracker")
    st.divider()

    # --- Student Account Panel ---
    st.subheader("👤 Student Account")

    is_guest = current_user.username == "default_student"

    if not is_guest:
        user_records = store.get_user_records(current_user.username)
        due_count = sum(1 for r in user_records if is_due_for_review(r))

        st.markdown(
            f"""
            <div class='user-card'>
                <strong>{current_user.display_name}</strong> <span style='color: #666;'>@{current_user.username}</span><br>
                <small style='color: #444;'>📚 Reviewed: {len(user_records)} concepts | ⏰ Due: {due_count}</small>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("🚪 Log Out", use_container_width=True):
            st.session_state.current_user = User(
                username="default_student",
                display_name="Guest Student",
                created_at=datetime.now(timezone.utc),
            )
            reset_session()
    else:
        st.caption("Currently studying as **Guest Student**.")
        auth_mode = st.radio("Account Action", ["Log In", "Sign Up"], horizontal=True, label_visibility="collapsed")

        if auth_mode == "Log In":
            with st.form("login_form"):
                u_in = st.text_input("Username", key="login_user")
                p_in = st.text_input("Password", type="password", key="login_pass")
                sub_login = st.form_submit_button("Log In", use_container_width=True)
                if sub_login:
                    auth_u = store.authenticate_user(u_in, p_in)
                    if auth_u:
                        st.session_state.current_user = auth_u
                        st.success(f"Welcome back, {auth_u.display_name}!")
                        reset_session()
                    else:
                        st.error("Invalid username or password.")
        else:
            with st.form("signup_form"):
                new_u = st.text_input("Choose Username (min 3 chars)", key="signup_user")
                new_name = st.text_input("Your Display Name", key="signup_name")
                new_p = st.text_input("Choose Password (min 3 chars)", type="password", key="signup_pass")
                sub_reg = st.form_submit_button("Create Account", use_container_width=True)
                if sub_reg:
                    created_u = store.create_user(new_u, new_name, new_p)
                    if created_u:
                        st.session_state.current_user = created_u
                        st.success(f"Account created! Welcome, {created_u.display_name}!")
                        reset_session()
                    else:
                        st.error("Username already taken or invalid details.")

    st.divider()

    # --- Topic Selection ---
    st.subheader("🌐 Topic Selection")
    curated_topics_list = provider.list_curated_topics()
    curated_options = {item["concept_id"]: item["topic_name"] for item in curated_topics_list}

    selected_topic_key = st.selectbox(
        "Choose a Curated Topic:",
        options=list(curated_options.keys()),
        format_func=lambda k: curated_options[k],
        index=list(curated_options.keys()).index(st.session_state.get("current_topic", "recursion_base_case"))
        if st.session_state.get("current_topic", "recursion_base_case") in curated_options
        else 0,
    )

    if st.button("Load Curated Topic", use_container_width=True):
        reset_session(new_topic=selected_topic_key)

    st.write("— OR —")
    custom_topic = st.text_input("Search & Generate Any Topic:", placeholder="e.g. Trie, Red-Black Tree, Docker, Raft")
    if st.button("✨ Generate with Gemini AI", use_container_width=True):
        if custom_topic.strip():
            with st.spinner("Generating authentic CS quiz question via Gemini AI..."):
                reset_session(new_topic=custom_topic.strip())

    st.divider()
    st.subheader("Session Actions")
    col_s1, col_s2 = st.columns(2)
    with col_s1:
        if st.button("🔄 New Session", use_container_width=True):
            reset_session()
    with col_s2:
        if st.button("🗑️ Reset DB", use_container_width=True):
            if hasattr(store, "db_path") and store.db_path.exists():
                try:
                    store.db_path.unlink()
                except Exception:
                    pass
            st.session_state.store = get_database_store()
            reset_session()

    st.divider()
    st.subheader("⏱️ Debug Time-Travel")
    current_cid = flow.question.concept_id if flow.question else "recursion_base_case"
    if st.button(f"⏩ Fast-Forward (+72h)", use_container_width=True):
        latest_rec = store.get_latest_concept_record(current_cid, user_id=flow.user_id)
        if latest_rec:
            ff = fast_forward_record(latest_rec, hours=72.0)
            store.save_concept_record(ff)
            st.success(f"Fast-forwarded '{current_cid}' for {flow.user_id} by 72 hours!")
            reset_session()
        else:
            st.warning(f"No records found for '{current_cid}' to fast forward.")

    st.divider()
    st.subheader("📊 Student Encounter History")
    filter_my_records = st.checkbox("Only show my records", value=True)
    filter_user = flow.user_id if filter_my_records else None

    records = store.get_concept_records(current_cid, user_id=filter_user) if current_cid else []

    if records:
        rec_data = [
            {
                "Student": r.user_id,
                "Topic": r.concept_id[:18],
                "Outcome": r.outcome.value,
                "Conf": f"{r.confidence}/5",
                "Due": r.next_review_at.strftime("%b %d, %H:%M"),
            }
            for r in records
        ]
        st.dataframe(pd.DataFrame(rec_data), use_container_width=True, hide_index=True)
    else:
        st.caption("No encounters recorded yet for this student.")

    st.divider()
    engine_badge = "🐘 PostgreSQL" if store.engine_name == "PostgreSQL" else "🪶 SQLite"
    st.caption(f"**Database Engine:** {engine_badge}")


# Main Interface Header
st.title("MindMesh: Persistent Learning-Confidence Tracker")
st.markdown(
    f"Active Student: **{current_user.display_name}** (`@{current_user.username}`) &nbsp;|&nbsp; "
    "**Core Agentic Loop:** Evaluates answers against internet rubrics, detects confidence/correctness disagreement, "
    "executes an adaptive backward transition to ask a targeted follow-up, and schedules reviews via spaced repetition."
)

# 6-State Visual Ribbon
states = [
    State.PROMPTING,
    State.ANSWERING,
    State.CHECKING,
    State.WAITING_FOR_FOLLOWUP,
    State.RECORDED,
    State.SKIPPED,
]

cols = st.columns(len(states))
for col, s in zip(cols, states):
    is_active = flow.state == s
    badge_class = "state-active" if is_active else "state-inactive"
    icon = "▶ " if is_active else ""
    col.markdown(
        f"<div class='state-badge {badge_class}' style='text-align: center; width: 100%;'>{icon}{s.value}</div>",
        unsafe_allow_html=True,
    )

st.write("")

# Context Card / Prior Encounter Notice (Isolated per student)
current_cid = flow.question.concept_id if flow.question else "concept"
prior_records = store.get_concept_records(current_cid, user_id=flow.user_id)
if prior_records and not flow.is_terminated and flow.attempt_count == 0:
    latest = prior_records[-1]
    is_due = is_due_for_review(latest)
    status_str = "⚠️ DUE FOR REVIEW" if is_due else "Upcoming"
    st.info(
        f"📅 **Encounter #{len(prior_records) + 1} for {current_user.display_name} on `{current_cid}`** — "
        f"Previous outcome: `{latest.outcome.value}` with confidence **{latest.confidence}/5** "
        f"on {latest.created_at.strftime('%Y-%m-%d')}. ({status_str})"
    )

# Active Question Card
with st.container(border=True):
    topic_display = flow.question.topic_name or flow.question.concept_id
    st.subheader(f"Topic: {topic_display}")

    if flow.question.quiz_source:
        st.markdown(
            f"<div class='source-badge'>📚 <strong>Quiz Reference:</strong> {flow.question.quiz_source} &nbsp;|&nbsp; "
            f"<a href='{flow.question.source_url}' target='_blank'>Original Source ↗</a></div>",
            unsafe_allow_html=True,
        )
    elif flow.question.source_url:
        st.markdown(
            f"<div class='source-badge'>🌐 <strong>Internet Source:</strong> <a href='{flow.question.source_url}' target='_blank'>{flow.question.source_url}</a></div>",
            unsafe_allow_html=True,
        )

    st.markdown(f"**Question:**\n{flow.question.prompt_text}")

    if flow.question.code_context:
        st.code(flow.question.code_context, language="python")

    if flow.question.rubric_criteria:
        with st.expander("📋 Evaluation Rubric Criteria (fetched from web)"):
            for crit in flow.question.rubric_criteria:
                st.markdown(f"- {crit}")

# State 1: ANSWERING
if flow.state == State.ANSWERING:
    st.markdown("### Step 1: Select the Correct Option (MCQ)")

    has_options = bool(flow.question and flow.question.options)

    # Topic-specific demo quick-fill presets
    col_b1, col_b2, col_b3 = st.columns(3)
    if has_options:
        correct_opt = flow.question.correct_option or "B"
        wrong_opts = [k for k in flow.question.options.keys() if k != correct_opt]
        wrong_opt = wrong_opts[0] if wrong_opts else "A"
        with col_b1:
            if st.button(f"Preset: Distractor Option {wrong_opt} (Wrong)", use_container_width=True):
                apply_mcq_preset(wrong_opt, 4)
        with col_b2:
            if st.button(f"Preset: Correct Option {correct_opt} (Right)", use_container_width=True):
                apply_mcq_preset(correct_opt, 5)
        with col_b3:
            if st.button("Preset: Guess (Conf 1/5)", use_container_width=True):
                apply_mcq_preset(correct_opt, 1)

    if has_options:
        opt_keys = list(flow.question.options.keys())
        default_index = opt_keys.index(st.session_state["mcq_radio"]) if st.session_state.get("mcq_radio") in opt_keys else 0
        selected_opt = st.radio(
            "Select your answer from the options below:",
            options=opt_keys,
            format_func=lambda k: f"**Option {k}:** {flow.question.options[k]}",
            index=default_index,
            key="mcq_radio",
        )
        answer_submission = selected_opt
    else:
        ans_text = st.text_area(
            "Your technical answer / implementation:",
            placeholder="Type your answer here...",
            key="ans_area",
        )
        answer_submission = ans_text

    rating = st.slider(
        "How confident are you that your answer is correct?",
        min_value=1,
        max_value=5,
        key="rating_slider",
        help="1 = Complete guess, 5 = Absolutely certain",
    )

    col_sub, col_skip = st.columns([4, 1])
    with col_sub:
        if st.button("Submit MCQ Answer for Evaluation", type="primary", use_container_width=True):
            if not answer_submission or not str(answer_submission).strip():
                st.error("Please select an option before submitting.")
            else:
                step_answering(flow, str(answer_submission).strip(), self_rating=rating)
                step_checking(flow)
                st.rerun()

    with col_skip:
        if st.button("Skip / Timeout", use_container_width=True):
            step_skip(flow, reason="User skipped")
            st.rerun()

# State 2: WAITING_FOR_FOLLOWUP (Explanation Check or Mismatch Loop)
elif flow.state == State.WAITING_FOR_FOLLOWUP:
    latest_answer = flow.answers[-1]
    latest_verdict = flow.verdicts[-1]
    is_explanation_phase = len(flow.verdicts) >= 1 and flow.verdicts[0].passed

    if is_explanation_phase:
        # Prompt user for explanation if answer was right in the first try
        st.markdown(
            f"""
            <div style='background-color: rgba(52, 168, 83, 0.12); border-left: 5px solid #34a853; padding: 16px; border-radius: 6px; margin-top: 15px; margin-bottom: 15px;'>
                <div style='color: #188038; font-weight: 700; font-size: 1.15rem; margin: 0;'>
                    🎉 Option {latest_answer.student_answer} is Correct! Now Explain Why
                </div>
                <div style='margin-top: 8px; font-size: 0.95rem; color: #202124;'>
                    Multiple-choice questions can sometimes be guessed correctly by chance.
                    To verify genuine conceptual understanding and cement your mastery:
                    <strong>Explain why Option {latest_answer.student_answer} is correct and why the alternatives fail.</strong>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        with st.container(border=True):
            st.subheader("💡 Conceptual Explanation Prompt")
            fu_prompt = (
                flow.question.follow_up_prompt
                if (flow.question and flow.question.follow_up_prompt)
                else f"Explain the core technical principles that make Option {latest_answer.student_answer} correct."
            )
            st.info(f"**Verification Question:** {fu_prompt}")

            col_fu_preset = st.columns(2)
            with col_fu_preset[0]:
                if flow.question.explanation and st.button("Preset: Verified Technical Explanation", use_container_width=True):
                    apply_fu_preset(flow.question.explanation)
            with col_fu_preset[1]:
                if st.button("Preset: Lucky Guess ('I just guessed randomly')", use_container_width=True):
                    apply_fu_preset("I just guessed Option " + str(latest_answer.student_answer) + " randomly, not sure why.")

            fu_text = st.text_area(
                "Your Technical Explanation (proves understanding beyond guessing):",
                placeholder="Explain why this option is correct, edge cases handled, and underlying computer science principles...",
                key="fu_area",
            )

            col_fu_sub, col_fu_skip = st.columns([4, 1])
            with col_fu_sub:
                if st.button("Submit Explanation for Verification", type="primary", use_container_width=True):
                    if not fu_text.strip():
                        st.error("Please provide an explanation to verify your answer.")
                    else:
                        step_followup(flow, fu_text.strip())
                        step_checking(flow)
                        st.rerun()
            with col_fu_skip:
                if st.button("Skip Question", use_container_width=True):
                    step_skip(flow, reason="Skipped during explanation")
                    st.rerun()

    else:
        # Standard Mismatch Objection Loop (Wrong answer + confident)
        st.markdown(
            f"""
            <div class='mismatch-box'>
                <div class='mismatch-title'>⚠️ Confidence / Correctness Mismatch Detected</div>
                <div class='mismatch-desc'>
                    You rated your confidence <strong>{latest_answer.self_rating}/5</strong>, but the evaluator identified an issue with your choice:
                </div>
                <div class='mismatch-objection'>
                    "{latest_verdict.objection}"
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        with st.container(border=True):
            st.subheader("🎯 Agent Targeted Follow-up: Select Corrected Option")
            if flow.question and flow.question.follow_up_prompt:
                st.info(f"**Guidance:** {flow.question.follow_up_prompt}")

            if flow.question and flow.question.options:
                opt_keys = list(flow.question.options.keys())
                correct_opt = flow.question.correct_option or "B"

                col_fu_preset = st.columns(2)
                with col_fu_preset[0]:
                    if st.button(f"Preset: Correct Option {correct_opt}", use_container_width=True):
                        apply_fu_mcq_preset(correct_opt)

                default_idx = (
                    opt_keys.index(st.session_state["fu_mcq_radio"])
                    if st.session_state.get("fu_mcq_radio") in opt_keys
                    else 0
                )
                fu_selected_opt = st.radio(
                    "Choose your corrected option (no written explanation needed):",
                    options=opt_keys,
                    format_func=lambda k: f"**Option {k}:** {flow.question.options[k]}",
                    index=default_idx,
                    key="fu_mcq_radio",
                )

                col_fu_sub, col_fu_skip = st.columns([4, 1])
                with col_fu_sub:
                    if st.button("Submit Corrected Option", type="primary", use_container_width=True):
                        step_followup(flow, fu_selected_opt)
                        step_checking(flow)
                        st.rerun()

                with col_fu_skip:
                    if st.button("Skip Question", use_container_width=True):
                        step_skip(flow, reason="Skipped during follow-up")
                        st.rerun()
            else:
                col_fu_preset = st.columns(2)
                if flow.question and flow.question.concept_id == "recursion_base_case":
                    with col_fu_preset[0]:
                        if st.button("Preset: Corrected Follow-up (return 0)", use_container_width=True):
                            apply_fu_preset("if not numbers: return 0 (empty list returns additive identity 0)")
                elif flow.question and flow.question.concept_id == "binary_search_bounds":
                    with col_fu_preset[0]:
                        if st.button("Preset: Corrected Follow-up (low <= high)", use_container_width=True):
                            apply_fu_preset("while low <= high: mid = low + (high - low) // 2")

                fu_text = st.text_area(
                    "Your corrected answer / clarification:",
                    placeholder="Type your corrected answer or choice...",
                    key="fu_area",
                )

                col_fu_sub, col_fu_skip = st.columns([4, 1])
                with col_fu_sub:
                    if st.button("Submit Follow-up", type="primary", use_container_width=True):
                        if not fu_text.strip():
                            st.error("Please enter a corrected answer.")
                        else:
                            step_followup(flow, fu_text.strip())
                            step_checking(flow)
                            st.rerun()

                with col_fu_skip:
                    if st.button("Skip Question", use_container_width=True):
                        step_skip(flow, reason="Skipped during follow-up")
                        st.rerun()

# State 3: RECORDED (Resolved)
elif flow.state == State.RECORDED:
    latest_rec = store.get_latest_concept_record(current_cid, user_id=flow.user_id)
    is_success = latest_rec and latest_rec.outcome in (Outcome.FIRST_TRY_CORRECT, Outcome.RESOLVED_ON_FOLLOW_UP)

    if is_success:
        if latest_rec and latest_rec.outcome == Outcome.FIRST_TRY_CORRECT:
            st.balloons()
        st.success(f"### 🎉 Review Complete: {latest_rec.outcome.value.replace('_', ' ').title()}")
    else:
        st.warning("### Review Recorded: Unresolved")

    if latest_rec:
        col_r1, col_r2, col_r3 = st.columns(3)
        col_r1.metric("Final Confidence", f"{latest_rec.confidence} / 5")
        col_r2.metric("Attempts Taken", latest_rec.attempts_count)
        col_r3.metric("Next Review Due", latest_rec.next_review_at.strftime("%Y-%m-%d %H:%M"))

    st.write(f"**Student:** `{flow.user_id}` | **Session:** `{flow.session_id}` | **Concept:** `{current_cid}`")

    if st.button("Start Next Review Cycle", type="primary"):
        reset_session()

# State 4: SKIPPED
elif flow.state == State.SKIPPED:
    st.error("### ⏸️ Session Skipped / Timed Out")
    st.caption("Decay interval has been accelerated. Review will be resurfaced soon.")
    if st.button("Restart Session"):
        reset_session()

# Persistent Event Stream Table
st.divider()
st.subheader(f"📜 Persistent {store.engine_name} Event Stream for Student: {flow.user_id}")
events = store.get_session_events(flow.session_id)
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
