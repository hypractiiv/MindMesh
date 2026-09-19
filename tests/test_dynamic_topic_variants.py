"""Unit tests verifying dynamic topic generation, anti-repetition constraints,
and variation progression across repeated topic practice.
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
from fetcher import CURATED_TOPICS, InternetQAProvider
from steps import step_prompting
from flow import FlowSession
from store import MindMeshStore


def test_gemini_anti_repetition_prompt_injection():
    """Verify that prior questions and encounter index are injected into the Gemini prompt payload."""
    provider = InternetQAProvider(api_key="mock_test_key", timeout=5.0)

    prior_pqs = [
        "What is the base case in a recursive factorial calculation?",
        "How does tail call optimization prevent recursion stack overflow?",
    ]

    mock_gemini_response = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": (
                                '{"concept_id": "recursion", '
                                '"topic_name": "Recursion: Tree Depth & Call Stack Frame Limits", '
                                '"prompt_text": "In a non-tail recursive tree traversal, what determines the maximum call stack depth?", '
                                '"code_context": null, '
                                '"options": {"A": "Maximum tree depth O(D)", "B": "Total node count O(N)", "C": "O(1)", "D": "Heap capacity"}, '
                                '"correct_option": "A", '
                                '"explanation": "Call stack frames persist until the bottom of the deepest recursive path is reached.", '
                                '"follow_up_prompt": "What happens if recursion exceeds sys.getrecursionlimit()?", '
                                '"rubric_criteria": ["Identifies maximum call stack depth equals maximum path depth."], '
                                '"quiz_source": "GeeksforGeeks Recursion Quiz", '
                                '"source_url": "https://en.wikipedia.org/wiki/Recursion_(computer_science)"}'
                            )
                        }
                    ]
                }
            }
        ]
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_gemini_response

    with patch("httpx.Client.post", return_value=mock_resp) as mock_post:
        q = provider.fetch_with_gemini(
            "Recursion",
            encounter_index=2,
            prior_questions=prior_pqs,
            shuffle=False,
        )

        assert q is not None
        assert q.concept_id == "recursion"
        assert q.correct_option == "A"

        # Verify the payload sent to Gemini contained the anti-repetition constraint
        sent_payload = mock_post.call_args[1]["json"]
        prompt_text = sent_payload["contents"][0]["parts"][0]["text"]

        assert "ANTI-REPETITION CONSTRAINT" in prompt_text
        assert "Question #3 on this topic" in prompt_text
        assert "What is the base case in a recursive factorial calculation?" in prompt_text
        assert "How does tail call optimization prevent recursion stack overflow?" in prompt_text
        assert "Do NOT repeat, rephrase, or ask about the same scenario/function" in prompt_text


def test_get_question_force_dynamic_bypasses_curated_catalog():
    """Verify that force_dynamic=True does not return the static curated question directly."""
    provider = InternetQAProvider(api_key=None)  # Offline fallback mode

    # Default without force_dynamic gets curated question
    curated_q = provider.get_question("recursion_base_case", force_dynamic=False)
    assert curated_q.concept_id == "recursion_base_case"
    assert curated_q == CURATED_TOPICS["recursion_base_case"]

    # With force_dynamic=True, it dynamically synthesizes from knowledge
    dyn_q0 = provider.get_question("recursion_base_case", encounter_index=0, force_dynamic=True)
    dyn_q1 = provider.get_question("recursion_base_case", encounter_index=1, force_dynamic=True)

    # force_dynamic question is distinct from the static curated question
    assert dyn_q0.prompt_text != curated_q.prompt_text
    assert dyn_q0 is not None
    assert dyn_q1 is not None


def test_step_prompting_passes_prior_questions_from_store():
    """Verify that step_prompting gathers prior question prompts from the student session events."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_var.db"
        store = MindMeshStore(db_path=db_path)
        student_id = "test_student_var"

        # Create session 1 on dynamic topic 'Graph Traversal'
        s1 = FlowSession(store=store, user_id=student_id)
        step_prompting(s1, topic="Graph Traversal")

        # The first question was loaded and recorded as an event
        events = store.get_all_session_events(user_id=student_id)
        question_events = [ev for ev in events if ev.event_type == "QUESTION_LOADED"]
        assert len(question_events) == 1
        q1_prompt = question_events[0].payload["question"]["prompt_text"]

        # Now simulate a second session for the same student on the same topic
        s2 = FlowSession(store=store, user_id=student_id)

        # Mock provider to inspect parameters passed to get_question
        with patch.object(InternetQAProvider, "get_question", wraps=InternetQAProvider().get_question) as spy_get_q:
            step_prompting(s2, topic="Graph Traversal")

            # Verify get_question was called with encounter_index and prior_questions containing q1_prompt
            spy_get_q.assert_called_once()
            call_kwargs = spy_get_q.call_args[1]
            assert "Graph Traversal" in spy_get_q.call_args[0]
            assert call_kwargs.get("prior_questions") == [q1_prompt]
