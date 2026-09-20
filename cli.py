"""
cli.py - Command-Line Interface and 8-Beat Judge Demo Runner for MindMesh.

Usage:
  python cli.py --demo                      # Run automated 8-beat judge demo
  python cli.py --interactive               # Run interactive review (prompts for user)
  python cli.py --user alice --topic binary # Run review for user alice on binary search
  python cli.py --history                   # Display persistent SQLite concept records
  python cli.py --fast-forward 72           # Fast-forward review clock by hours
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from decay import fast_forward_record, is_due_for_review
from fetcher import CURATED_TOPICS, InternetQAProvider
from flow import FlowSession
from models import Outcome, State
from steps import (
    step_answering,
    step_checking,
    step_followup,
    step_prompting,
)
from store import MindMeshStore


def print_banner(title: str) -> None:
    border = "=" * 70
    print(f"\n{border}\n  {title}\n{border}")


def print_beat(beat_num: int, title: str, purpose: str) -> None:
    print(f"\n>>> [BEAT {beat_num}] {title}")
    print(f"    Purpose: {purpose}")
    print("-" * 70)


def run_judge_demo(delay: float = 0.8) -> None:
    """Executes the exact eight-beat demo sequence specified in Section 10 of the plan."""
    db_path = Path("mindmesh_demo.db")
    if db_path.exists():
        try:
            db_path.unlink()
        except Exception:
            pass

    store = MindMeshStore(db_path=db_path)
    demo_user = "demo_student"

    print_banner("MINDMESH: 8-BEAT JUDGE DEMO FLOW")
    print("Agentic Learning-Confidence Tracker (Concept: Recursion Base Case)")
    time.sleep(delay)

    # BEAT 1
    print_beat(1, "Old autograder-passing submission", "Establish the problem.")
    print("Historical Context: Student passed an autograder yesterday with code:")
    print("  def sum_list(numbers):")
    print("      if len(numbers) == 0: return 0")
    print("      return numbers[0] + sum_list(numbers[1:])")
    print("Question: Does the student actually understand the base case, or did they guess?")
    time.sleep(delay)

    # BEAT 2
    session_enc1 = "demo-session-enc-1"
    session1 = FlowSession(session_id=session_enc1, store=store, user_id=demo_user)
    step_prompting(session1, topic="recursion_base_case")

    print_beat(2, "Student gives wrong base case and self-rates 4/5", "Create the confidence/correctness mismatch.")
    print(f"Current State: [{session1.state.value}]")
    print(f"Question: {session1.question.prompt_text}")
    print("\nStudent Submission:")
    wrong_answer = "if len(numbers) == 0: return 1"
    self_rating = 4
    print(f"  Student:     {session1.user_id}")
    print(f"  Answer:      \"{wrong_answer}\"")
    print(f"  Self-Rating: {self_rating}/5 (Highly Confident)")
    step_answering(session1, wrong_answer, self_rating=self_rating)
    print(f"State transition -> [{session1.state.value}]")
    time.sleep(delay)

    # BEAT 3
    print_beat(3, "Evaluator flags answer as incorrect", "Show independent checking.")
    print("System evaluates submission against domain rubric...")
    verdict1 = step_checking(session1)
    print(f"  Passed:      {verdict1.passed}")
    print(f"  Mismatch:    {verdict1.is_mismatch} (Student rated 4/5 but answer failed!)")
    print(f"  Objection:   \"{verdict1.objection}\"")
    time.sleep(delay)

    # BEAT 4
    print_beat(4, "System asks one targeted follow-up", "Show adaptive backward transition.")
    print(f"State transition: Checking -> [{session1.state.value}]")
    print(f"Targeted Prompt: \"{session1.question.follow_up_prompt}\"")
    print("System pauses and waits for the human to answer...")
    time.sleep(delay)

    # BEAT 5
    print_beat(5, "Student answers correctly", "Human remains responsible for the answer.")
    corrected_answer = "if not numbers: return 0"
    print(f"Student Follow-up Submission: \"{corrected_answer}\"")
    step_followup(session1, corrected_answer)
    print(f"State transition -> [{session1.state.value}]")
    verdict2 = step_checking(session1)
    print(f"Evaluator Verdict: Passed={verdict2.passed}")
    time.sleep(delay)

    # BEAT 6
    print_beat(6, "Record shows confidence 3 and 'resolved on follow-up'", "Show persistent state.")
    print(f"State transition -> [{session1.state.value}]")
    rec1 = store.get_latest_concept_record("recursion_base_case", user_id=demo_user)
    print("Persisted ConceptRecord in SQLite:")
    print(f"  Student ID:     {rec1.user_id}")
    print(f"  Session ID:     {rec1.session_id}")
    print(f"  Outcome:        {rec1.outcome.value}")
    print(f"  Confidence:     {rec1.confidence} / 5")
    print(f"  Attempts Count: {rec1.attempts_count}")
    print(f"  Next Review At: {rec1.next_review_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    time.sleep(delay)

    # BEAT 7
    print_beat(7, "Fast-forward the clock with debug mode", "Show next-review scheduling.")
    print("Simulating elapsed time: fast-forwarding 72 hours...")
    ff_rec = fast_forward_record(rec1, hours=72.0)
    store.save_concept_record(ff_rec)
    due = is_due_for_review(ff_rec)
    print(f"  Concept is now due for review: {due}")
    time.sleep(delay)

    # BEAT 8
    print_beat(8, "Reopen the concept; show improved first-try outcome", "Prove persistence matters.")
    session_enc2 = "demo-session-enc-2"
    session2 = FlowSession(session_id=session_enc2, store=store, user_id=demo_user)
    step_prompting(session2, topic="recursion_base_case")

    events = store.get_session_events(session_enc2)
    prior_info = events[0].payload.get("prior_history")
    print(f"System context loaded for {demo_user} from prior encounter:")
    print(f"  Previous encounters: {prior_info['previous_encounters']}")
    print(f"  Last outcome:        {prior_info['last_outcome']}")
    print(f"  Last confidence:     {prior_info['last_confidence']}")

    print("\nStudent second encounter response:")
    mastery_opt = "B"
    mastery_rating = 5
    print(f"  Option Selected: Option {mastery_opt} (if not numbers: return 0)")
    print(f"  Self-Rating:     {mastery_rating}/5 (Highest Confidence)")
    step_answering(session2, mastery_opt, self_rating=mastery_rating)
    v_opt = step_checking(session2)
    print(f"State transition -> [{session2.state.value}] (MCQ explanation requested)")

    # Follow-up conceptual explanation to verify understanding
    mastery_explanation = "An empty list has length 0, so the recursive sum must return 0 as the additive identity."
    print(f"Student Explanation: \"{mastery_explanation}\"")
    step_followup(session2, mastery_explanation)
    v_exp = step_checking(session2)
    print(f"Evaluator Verdict: Passed={v_exp.passed} -> [{session2.state.value}]")

    rec2 = store.get_latest_concept_record("recursion_base_case", user_id=demo_user)
    print("\nUpdated Persistence in SQLite:")
    print(f"  Student:        {rec2.user_id}")
    print(f"  Outcome:        {rec2.outcome.value}")
    print(f"  Confidence:     {rec2.confidence} / 5")
    print(f"  Next Review At: {rec2.next_review_at.strftime('%Y-%m-%d %H:%M:%S UTC')} (+7 days interval)")

    print_banner("DEMO COMPLETED SUCCESSFULLY")


def run_interactive(topic: str | None = None, user_id: str | None = None) -> None:
    """Runs an interactive session with user accounts and topic selection."""
    provider = InternetQAProvider()
    store = MindMeshStore()

    if not user_id:
        print_banner("STUDENT LOGIN")
        user_id = input("Enter student username (e.g. alice, bob, or press Enter for 'default_student'): ").strip()
        if not user_id:
            user_id = "default_student"

    # Ensure profile exists
    if not store.get_user(user_id):
        store.create_user(user_id, user_id.capitalize(), "pass123")

    if not topic:
        print_banner("SELECT AUTHENTIC CS QUIZ TOPIC")
        provider = InternetQAProvider()
        curated_list = provider.list_curated_topics()
        choice_map = {}
        for idx, item in enumerate(curated_list, 1):
            print(f"{idx}. {item['topic_name']} [{item.get('quiz_source', 'Quiz')}]")
            choice_map[str(idx)] = item["concept_id"]

        custom_idx = len(curated_list) + 1
        print(f"{custom_idx}. Search Web for Any Other Topic")

        choice = input(f"\nEnter choice (1-{custom_idx}, default 1): ").strip()
        if choice == str(custom_idx):
            topic = input("Enter any CS topic to search the web for: ").strip()
        else:
            topic = choice_map.get(choice, "recursion_base_case")

    session = FlowSession(store=store, user_id=user_id)
    print(f"\nFetching question for '{topic}' from internet/knowledge base...")
    step_prompting(session, topic=topic)

    q = session.question
    print_banner(f"STUDENT: {user_id} | TOPIC: {q.topic_name or q.concept_id}")
    if q.quiz_source:
        print(f"Quiz Reference: {q.quiz_source}")
    if q.source_url:
        print(f"Source URL: {q.source_url}\n")

    # Check prior history for this student
    records = store.get_concept_records(q.concept_id, user_id=user_id)
    if records:
        print(f"Welcome back, {user_id}! You have {len(records)} previous review(s) for this concept.")
        print(f"Last outcome: {records[-1].outcome.value} (Confidence: {records[-1].confidence}/5)")
    else:
        print(f"Welcome, {user_id}! This is your first encounter for this concept.")

    print(f"\nQuestion:\n{q.prompt_text}")
    if q.code_context:
        print(f"\nCode Context:\n{q.code_context}")

    ans_text = input("\nYour answer: ").strip()
    while not ans_text:
        ans_text = input("Please provide an answer: ").strip()

    rating_input = input("How confident are you? (1=Not confident, 5=Extremely confident): ").strip()
    try:
        rating = int(rating_input)
        rating = max(1, min(5, rating))
    except ValueError:
        rating = 3

    step_answering(session, ans_text, rating)
    print("\nEvaluating your answer against rubric...")
    verdict = step_checking(session)

    if session.state == State.WAITING_FOR_FOLLOWUP:
        print(f"\n⚠️ Mismatch detected! (Your self-rating: {rating}/5, Evaluator flagged an issue).")
        print(f"Evaluator Objection: {verdict.objection}")
        print(f"\nTargeted Follow-up Question:\n{q.follow_up_prompt}")

        fu_text = input("\nYour corrected answer: ").strip()
        step_followup(session, fu_text)
        print("\nRe-evaluating...")
        verdict2 = step_checking(session)

        if verdict2.passed:
            print("\nGreat job! Your corrected answer resolved the issue.")
        else:
            print(f"\nFollow-up answer was still not complete: {verdict2.objection}")

    rec = store.get_latest_concept_record(q.concept_id, user_id=user_id)
    print_banner("SESSION COMPLETED")
    print(f"Student:         {user_id}")
    print(f"Final State:     {session.state.value}")
    print(f"Outcome:         {rec.outcome.value}")
    print(f"Confidence:      {rec.confidence}/5")
    print(f"Next Review Due: {rec.next_review_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")


def display_history(user_id: str | None = None) -> None:
    store = MindMeshStore()
    with store._get_connection() as conn:
        cursor = conn.cursor()
        if user_id:
            cursor.execute("SELECT * FROM concept_records WHERE user_id = ? ORDER BY created_at ASC", (user_id,))
        else:
            cursor.execute("SELECT * FROM concept_records ORDER BY created_at ASC")
        records = cursor.fetchall()

    title = f"MINDMESH PERSISTENT HISTORY ({f'STUDENT: {user_id}' if user_id else 'ALL STUDENTS'})"
    print_banner(title)
    if not records:
        print("No concept records found.")
        return

    print(f"{'#':<4} {'Student':<16} {'Concept':<25} {'Outcome':<22} {'Conf':<6} {'Next Review':<18}")
    print("-" * 95)
    for i, r in enumerate(records, start=1):
        uid = r["user_id"] if "user_id" in r.keys() else "default"
        print(
            f"{i:<4} {uid[:14]:<16} {r['concept_id'][:23]:<25} {r['outcome']:<22} {r['confidence']:<6} {r['next_review_at'][:16]:<18}"
        )


def main():
    parser = argparse.ArgumentParser(description="MindMesh Learning-Confidence Tracker CLI")
    parser.add_argument("--demo", action="store_true", help="Run the automated 8-beat judge demo")
    parser.add_argument("--interactive", action="store_true", help="Run an interactive session")
    parser.add_argument("--user", type=str, help="Student username")
    parser.add_argument("--topic", type=str, help="Specify topic name or internet query")
    parser.add_argument("--history", action="store_true", help="View concept history from SQLite")
    parser.add_argument("--fast-forward", type=float, metavar="HOURS", help="Fast-forward the latest review clock by hours")

    args = parser.parse_args()

    if args.demo:
        run_judge_demo()
    elif args.interactive or args.topic or args.user:
        run_interactive(topic=args.topic, user_id=args.user)
    elif args.history:
        display_history(user_id=args.user)
    elif args.fast_forward is not None:
        store = MindMeshStore()
        rec = store.get_latest_concept_record("recursion_base_case")
        if not rec:
            print("No records found to fast forward.")
            return
        ff_rec = fast_forward_record(rec, hours=args.fast_forward)
        store.save_concept_record(ff_rec)
        print(f"Fast-forwarded latest record by {args.fast_forward} hours.")
        print(f"Due for review now: {is_due_for_review(ff_rec)}")
    else:
        run_judge_demo()


if __name__ == "__main__":
    main()
