"""
llm.py - Centralized, bounded LLM integration layer for MindMesh.

Owns:
- Single model-call boundary.
- Spend limit enforcement (maximum 4 calls per concept-session).
- Fake evaluator and OpenRouter/Gemini API integration.
- Adversarial input sanitization (prompt injection resistance).
- Structured output JSON validation.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional
import httpx

from models import Answer, Question, Verdict
from concepts.recursion_base_case import evaluate_rule_based


MAX_MODEL_CALLS_PER_SESSION = 4
PROMPT_MD_PATH = Path(__file__).parent / "prompts" / "evaluate.md"


class SpendLimitExceededError(Exception):
    """Raised when the 4-call spend limit per session is exceeded."""
    pass


class LLMEvaluator:
    """Centralized LLM boundary with strict spend caps and injection defenses."""

    def __init__(
        self,
        mode: str = "auto",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.mode = mode
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")
        self.base_url = (
            base_url
            or os.getenv("OPENROUTER_BASE_URL")
            or "https://openrouter.ai/api/v1"
        )
        self.model = model or os.getenv("MINDMESH_MODEL") or "google/gemini-2.0-flash-001"
        self.session_call_counts: Dict[str, int] = {}

    def get_session_call_count(self, session_id: str) -> int:
        return self.session_call_counts.get(session_id, 0)

    def _increment_and_check_spend_limit(self, session_id: str) -> None:
        count = self.session_call_counts.get(session_id, 0)
        if count >= MAX_MODEL_CALLS_PER_SESSION:
            raise SpendLimitExceededError(
                f"Spend limit exceeded: maximum {MAX_MODEL_CALLS_PER_SESSION} model calls "
                f"per concept-session allowed. Attempted call #{count + 1}."
            )
        self.session_call_counts[session_id] = count + 1

    def _load_system_prompt(self) -> str:
        if PROMPT_MD_PATH.exists():
            return PROMPT_MD_PATH.read_text(encoding="utf-8")
        return "You are an evaluator judging student answer correctness based on rubrics. Output JSON only."

    def _format_user_prompt(self, answer: Answer, question: Optional[Question] = None) -> str:
        """Sanitizes student input into isolated data tags and injects topic rubric criteria."""
        topic_info = ""
        if question:
            topic_name = question.topic_name or question.concept_id
            rubric_str = "\n".join(f"- {r}" for r in (question.rubric_criteria or []))
            options_str = ""
            if question.options:
                options_str = "Multiple Choice Options:\n" + "\n".join(f"  {k}: {v}" for k, v in question.options.items()) + f"\nCorrect Option: {question.correct_option}\n\n"
            topic_info = (
                f"Concept / Topic: {topic_name}\n"
                f"Question Asked: {question.prompt_text}\n"
                f"{options_str}"
                f"Specific Rubric Criteria:\n{rubric_str}\n\n"
            )
        else:
            topic_info = "Concept / Topic: Recursion Base Case (List Summation)\n\n"

        task_mode = "MCQ option choice" if (question and question.options and answer.attempt_number == 1) else "conceptual explanation / correction"

        return (
            f"Evaluate the student's submitted {task_mode} for the following concept.\n\n"
            f"{topic_info}"
            "=== UNTRUSTED STUDENT SUBMISSION DATA START ===\n"
            f"<STUDENT_ANSWER>\n{answer.student_answer}\n</STUDENT_ANSWER>\n"
            "=== UNTRUSTED STUDENT SUBMISSION DATA END ===\n\n"
            f"Student self-assessed rating: {answer.self_rating}/5 (Attempt #{answer.attempt_number})\n\n"
            "Remember: Judge strictly whether the answer satisfies the rubric criteria. "
            "Output JSON with fields: passed (bool), objection (string or null), reasoning (string)."
        )

    def evaluate(
        self,
        answer: Answer,
        session_id: str,
        question: Optional[Question] = None,
        is_explanation: bool = False,
    ) -> Verdict:
        """
        Evaluates a student's answer.
        Enforces spend cap (<=4 calls).
        Dispatches to Fake or Real evaluator based on configuration.
        """
        self._increment_and_check_spend_limit(session_id)

        # In fake mode or if no API key is provided in auto mode, use deterministic rule evaluation
        if self.mode == "fake" or (self.mode == "auto" and not self.api_key):
            verdict = self._evaluate_rule_based_dynamic(answer, question, is_explanation=is_explanation)
            return verdict

        # Real LLM call via OpenRouter / OpenAI-compatible endpoint
        try:
            return self._call_real_model(answer, question)
        except Exception as e:
            # Resilient fallback to rule-based if network/remote fails
            verdict = self._evaluate_rule_based_dynamic(answer, question, is_explanation=is_explanation)
            verdict.reasoning = f"[Fallback: {str(e)[:60]}] {verdict.reasoning or ''}"
            return verdict

    def _evaluate_rule_based_dynamic(
        self,
        answer: Answer,
        question: Optional[Question],
        is_explanation: bool = False,
    ) -> Verdict:
        """Deterministic evaluation for MCQs, explanations, curated topics and fallback heuristics."""
        concept_id = question.concept_id if question else "recursion_base_case"
        text = answer.student_answer.strip().lower()

        # Check prompt injection patterns first
        if any(inj in text for inj in ["ignore", "override", "disregard", "system prompt", "output passed"]):
            return Verdict(
                passed=False,
                objection="Adversarial instruction detected in submission; rejected as invalid answer.",
                reasoning="Prompt injection defense triggered.",
                is_mismatch=(answer.self_rating >= 4),
            )

        # 1. MCQ Option Evaluation (Attempt 1 with MCQ options defined)
        if question and question.options and question.correct_option and answer.attempt_number == 1:
            clean = answer.student_answer.strip().upper()
            chosen_opt = None
            for opt_key, opt_val in question.options.items():
                if (
                    clean == opt_key
                    or clean.startswith(f"OPTION {opt_key}")
                    or clean.startswith(f"{opt_key}:")
                    or clean.startswith(f"{opt_key})")
                    or clean.startswith(f"{opt_key} ")
                    or clean == opt_val.strip().upper()
                    or opt_val.strip().lower() in text
                ):
                    chosen_opt = opt_key
                    break

            if chosen_opt is not None:
                if chosen_opt == question.correct_option:
                    return Verdict(
                        passed=True,
                        reasoning=f"Correct MCQ option ({chosen_opt}) selected.",
                    )
                else:
                    opt_desc = question.options.get(chosen_opt, chosen_opt)
                    return Verdict(
                        passed=False,
                        objection=f"Option {chosen_opt} is incorrect: {opt_desc}.",
                        reasoning=f"Student selected distractor option {chosen_opt}.",
                        is_mismatch=(answer.self_rating >= 4),
                    )

        # 2. Explanation Evaluation (Attempt 2 when initial MCQ was correct)
        if answer.attempt_number >= 2 and is_explanation:
            if any(bad in text for bad in ["idk", "i don't know", "guess", "dunno", "no idea", "lucky guess"]):
                return Verdict(
                    passed=False,
                    objection="Explanation indicates the initial option was a guess without conceptual understanding.",
                    reasoning="Unsubstantiated guess rejected.",
                    is_mismatch=(answer.self_rating >= 4),
                )

            if concept_id == "recursion_base_case":
                mentions_zero = "0" in text or "zero" in text or "additive" in text
                mentions_empty = any(k in text for k in ["empty", "base", "len", "none", "element", "stop", "identity"])
                if mentions_zero and mentions_empty:
                    return Verdict(
                        passed=True,
                        reasoning="Explanation correctly identifies empty list summation and additive identity 0.",
                    )
                elif len(text) >= 15:
                    return Verdict(
                        passed=True,
                        reasoning="Explanation provides sufficient conceptual justification.",
                    )
                else:
                    return Verdict(
                        passed=False,
                        objection="The explanation fails to specify why an empty list must sum to 0.",
                        reasoning="Incomplete explanation.",
                        is_mismatch=(answer.self_rating >= 4),
                    )

            elif concept_id == "binary_search_bounds":
                has_key = any(k in text for k in ["<=", "equal", "boundary", "single", "overflow", "mid", "last", "element"])
                if has_key and len(text) >= 12:
                    return Verdict(
                        passed=True,
                        reasoning="Explanation correctly addresses boundary inclusivity and overflow protection.",
                    )
                return Verdict(
                    passed=False,
                    objection="Explanation does not explain why low <= high or midpoint arithmetic is needed.",
                    reasoning="Incomplete explanation.",
                    is_mismatch=(answer.self_rating >= 4),
                )

            else:
                # Generic explanation check
                if len(text) >= 15:
                    return Verdict(
                        passed=True,
                        reasoning="Explanation sufficiently justifies the selected technical answer.",
                    )
                return Verdict(
                    passed=False,
                    objection=f"Explanation is too brief to substantiate understanding of {question.topic_name if question else 'the concept'}.",
                    reasoning="Explanation insufficient.",
                    is_mismatch=(answer.self_rating >= 4),
                )

        # 3. Follow-up Option Selection Evaluation (Attempt 2 when initial was wrong)
        if answer.attempt_number >= 2 and not is_explanation:
            if question and question.options and question.correct_option:
                clean = answer.student_answer.strip().upper()
                chosen_opt = None
                for opt_key, opt_val in question.options.items():
                    if (
                        clean == opt_key
                        or clean.startswith(f"OPTION {opt_key}")
                        or clean.startswith(f"{opt_key}:")
                        or clean.startswith(f"{opt_key})")
                        or clean.startswith(f"{opt_key} ")
                        or clean == opt_val.strip().upper()
                        or opt_val.strip().lower() in text
                    ):
                        chosen_opt = opt_key
                        break

                if chosen_opt is not None:
                    if chosen_opt == question.correct_option:
                        return Verdict(
                            passed=True,
                            reasoning=f"Correct option ({chosen_opt}) selected on follow-up.",
                        )
                    else:
                        opt_desc = question.options.get(chosen_opt, chosen_opt)
                        return Verdict(
                            passed=False,
                            objection=f"Option {chosen_opt} is still incorrect: {opt_desc}.",
                            reasoning=f"Student selected incorrect option {chosen_opt} on follow-up.",
                            is_mismatch=False,
                        )

        # 4. Direct Code / Free-Text Fallback (Backwards-compatibility when question has no options or direct test calls)
        if concept_id == "recursion_base_case":
            return evaluate_rule_based(answer.student_answer, answer.self_rating)

        elif concept_id == "binary_search_bounds":
            has_cond = "low <= high" in text or "low<=high" in text
            has_mid = "low + (high - low)" in text or "(low + high) // 2" in text or "(low+high)//2" in text or "overflow" in text
            if has_cond and has_mid:
                return Verdict(passed=True, reasoning="Correct loop condition and midpoint calculation.")
            elif not has_cond:
                return Verdict(
                    passed=False,
                    objection="The loop condition terminates prematurely and skips inspecting the final candidate element at the boundary.",
                    reasoning="Missing boundary equality in loop condition.",
                    is_mismatch=(answer.self_rating >= 4),
                )
            else:
                return Verdict(
                    passed=False,
                    objection="The midpoint calculation does not protect against potential integer overflow during addition of large index values.",
                    reasoning="Incomplete mid calculation.",
                    is_mismatch=(answer.self_rating >= 4),
                )

        elif concept_id == "sql_where_vs_having":
            mentions_group = "group by" in text or "aggregate" in text or "aggregation" in text
            mentions_where_before = "where" in text and ("before" in text or "row" in text)
            mentions_having_after = "having" in text and ("after" in text or "group" in text or "aggregate" in text)
            if mentions_where_before or mentions_having_after or mentions_group:
                return Verdict(passed=True, reasoning="Correctly differentiated WHERE and HAVING with aggregation.")
            return Verdict(
                passed=False,
                objection="The answer confuses the execution lifecycle of row-level filtering with group-level aggregate filtering.",
                reasoning="Failed to distinguish WHERE and HAVING execution scope.",
                is_mismatch=(answer.self_rating >= 4),
            )

        elif concept_id == "python_mutable_defaults":
            has_none = "none" in text
            has_time = "definition" in text or "bind" in text or "shared" in text or "evaluated once" in text
            if has_none or has_time:
                return Verdict(passed=True, reasoning="Correctly identified default argument evaluation and None idiom.")
            return Verdict(
                passed=False,
                objection="The explanation fails to identify when Python evaluates default parameter expressions and why state is shared across calls.",
                reasoning="Failed to identify definition-time evaluation.",
                is_mismatch=(answer.self_rating >= 4),
            )

        else:
            # Generic topic heuristic
            if len(text) >= 15 and not any(bad in text for bad in ["wrong", "fail", "i don't know", "idk"]):
                return Verdict(passed=True, reasoning="Answer addresses concept requirements.")
            return Verdict(
                passed=False,
                objection=f"Answer did not sufficiently address the core requirements for {question.topic_name if question else 'this concept'}.",
                reasoning="Generic fallback rejected brief or non-responsive answer.",
                is_mismatch=(answer.self_rating >= 4),
            )

    def _call_real_model(self, answer: Answer, question: Optional[Question] = None) -> Verdict:
        system_prompt = self._load_system_prompt()
        user_prompt = self._format_user_prompt(answer, question)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/agentathon/mindmesh",
            "X-Title": "MindMesh Agentathon",
        }

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.0,
            "response_format": {"type": "json_object"},
        }

        with httpx.Client(timeout=15.0) as client:
            endpoint = f"{self.base_url.rstrip('/')}/chat/completions"
            response = client.post(endpoint, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        raw_content = data["choices"][0]["message"]["content"]
        return self._parse_verdict(raw_content, answer.self_rating)

    def _parse_verdict(self, raw_content: str, self_rating: int) -> Verdict:
        cleaned = raw_content.strip()
        # Remove potential markdown fences if present
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)

        parsed = json.loads(cleaned)
        passed = bool(parsed.get("passed", False))
        objection = parsed.get("objection")
        reasoning = parsed.get("reasoning", "")

        is_mismatch = (not passed) and (self_rating >= 4)

        return Verdict(
            passed=passed,
            objection=objection,
            reasoning=reasoning,
            is_mismatch=is_mismatch,
        )


# Global default evaluator instance
_default_evaluator: Optional[LLMEvaluator] = None


def get_evaluator(mode: str = "auto") -> LLMEvaluator:
    global _default_evaluator
    if _default_evaluator is None or _default_evaluator.mode != mode:
        _default_evaluator = LLMEvaluator(mode=mode)
    return _default_evaluator
