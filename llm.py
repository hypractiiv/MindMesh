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
            topic_info = (
                f"Concept / Topic: {topic_name}\n"
                f"Question Asked: {question.prompt_text}\n"
                f"Specific Rubric Criteria:\n{rubric_str}\n\n"
            )
        else:
            topic_info = "Concept / Topic: Recursion Base Case (List Summation)\n\n"

        return (
            f"Evaluate the student's submitted answer for the following concept.\n\n"
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
    ) -> Verdict:
        """
        Evaluates a student's answer.
        Enforces spend cap (<=4 calls).
        Dispatches to Fake or Real evaluator based on configuration.
        """
        self._increment_and_check_spend_limit(session_id)

        # In fake mode or if no API key is provided in auto mode, use deterministic rule evaluation
        if self.mode == "fake" or (self.mode == "auto" and not self.api_key):
            verdict = self._evaluate_rule_based_dynamic(answer, question)
            return verdict

        # Real LLM call via OpenRouter / OpenAI-compatible endpoint
        try:
            return self._call_real_model(answer, question)
        except Exception as e:
            # Resilient fallback to rule-based if network/remote fails
            verdict = self._evaluate_rule_based_dynamic(answer, question)
            verdict.reasoning = f"[Fallback: {str(e)[:60]}] {verdict.reasoning or ''}"
            return verdict

    def _evaluate_rule_based_dynamic(self, answer: Answer, question: Optional[Question]) -> Verdict:
        """Deterministic evaluation for curated topics and fallback heuristics for custom topics."""
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
