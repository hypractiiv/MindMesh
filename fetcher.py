"""
fetcher.py - Internet Q&A Provider and Topic Engine for MindMesh.

Owns:
- Curated CS topic catalog.
- Live internet retrieval via Wikipedia REST API & educational documentation.
- Dynamic Question synthesis with code context, rubric criteria, and follow-up prompts.
"""

from __future__ import annotations

import re
import urllib.parse
from typing import Dict, List, Optional
import httpx

from models import Question


CURATED_TOPICS: Dict[str, Question] = {
    "recursion_base_case": Question(
        concept_id="recursion_base_case",
        topic_name="Recursion: Base Case in List Summation",
        prompt_text=(
            "For a recursive function that sums a list of integers `def sum_list(numbers):`, "
            "what is the base case condition and what value should it return?"
        ),
        code_context="""def sum_list(numbers):
    # Base case goes here
    ...
    return numbers[0] + sum_list(numbers[1:])""",
        options={
            "A": "if len(numbers) == 0: return 1  (Multiplicative identity)",
            "B": "if not numbers: return 0  (Additive identity for empty list)",
            "C": "if not numbers: return None  (Terminates recursion with null)",
            "D": "if len(numbers) == 1: return numbers[0]  (Fails on empty list input)",
        },
        correct_option="B",
        explanation=(
            "An empty list has no elements, so its sum must be 0 (the additive identity). "
            "Returning 1 produces an off-by-one error, and returning None causes a TypeError."
        ),
        follow_up_prompt=(
            "Think about what `sum_list([])` should return when there are no elements to sum. "
            "Why would returning 1 cause `sum_list([5])` to equal 6 instead of 5? "
            "Please provide the corrected base case condition and return value."
        ),
        rubric_criteria=[
            "Must check for empty list (e.g. len(numbers) == 0 or not numbers).",
            "Must return 0 (the additive identity).",
            "Returning 1 or None is incorrect.",
        ],
        source_url="https://en.wikipedia.org/wiki/Recursion_(computer_science)#Base_case",
    ),
    "binary_search_bounds": Question(
        concept_id="binary_search_bounds",
        topic_name="Binary Search: Midpoint & Boundary Conditions",
        prompt_text=(
            "In a standard binary search implementation `def binary_search(arr, target):` on a sorted array, "
            "what is the standard loop continuation condition, and how should `mid` be calculated to avoid integer overflow?"
        ),
        code_context="""def binary_search(arr, target):
    low, high = 0, len(arr) - 1
    while [LOOP_CONDITION]:
        mid = [MID_CALCULATION]
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            low = mid + 1
        else:
            high = mid - 1
    return -1""",
        options={
            "A": "while low < high: and mid = (low + high) // 2",
            "B": "while low <= high: and mid = low + (high - low) // 2",
            "C": "while low <= high: and mid = (high - low) // 2",
            "D": "while low != high: and mid = high // 2",
        },
        correct_option="B",
        explanation=(
            "The loop condition `low <= high` ensures single-element subarrays are inspected. "
            "Calculating `mid = low + (high - low) // 2` prevents integer overflow in bounded-width integer types."
        ),
        follow_up_prompt=(
            "Consider what happens when the target is at the very last element `arr[len(arr) - 1]`. "
            "Why will a loop condition of `while low < high` fail to check the last remaining element?"
        ),
        rubric_criteria=[
            "Loop condition must be `low <= high` (not `low < high`).",
            "Midpoint calculation should be `low + (high - low) // 2` or `(low + high) // 2` in Python.",
            "Must update low = mid + 1 and high = mid - 1.",
        ],
        source_url="https://en.wikipedia.org/wiki/Binary_search_algorithm#Implementation_issues",
    ),
    "sql_where_vs_having": Question(
        concept_id="sql_where_vs_having",
        topic_name="SQL: WHERE vs HAVING Clause Filtering",
        prompt_text=(
            "In SQL, what is the fundamental architectural difference between the `WHERE` clause "
            "and the `HAVING` clause when filtering aggregated query results?"
        ),
        code_context="""SELECT department_id, COUNT(*) AS employee_count
FROM employees
-- Which clause filters individual rows before grouping?
-- Which clause filters grouped results after aggregation?
GROUP BY department_id;""",
        options={
            "A": "WHERE filters aggregated groups; HAVING filters raw table rows before grouping.",
            "B": "WHERE filters individual rows before grouping; HAVING filters aggregated groups after GROUP BY.",
            "C": "WHERE and HAVING are completely interchangeable in SQL standards.",
            "D": "WHERE permits aggregate functions like COUNT(*); HAVING only filters scalar columns.",
        },
        correct_option="B",
        explanation=(
            "WHERE executes first to filter base table rows prior to grouping. "
            "GROUP BY aggregates the remaining rows, and HAVING evaluates conditions on the aggregated groups."
        ),
        follow_up_prompt=(
            "Can aggregate functions like `COUNT(*)` or `SUM(salary)` be placed inside a `WHERE` clause? "
            "Why does the SQL query execution engine require `HAVING` for aggregated conditions?"
        ),
        rubric_criteria=[
            "WHERE filters rows BEFORE grouping and aggregation occurs.",
            "HAVING filters groups/records AFTER aggregation (GROUP BY).",
            "Aggregate functions (COUNT, SUM, AVG) cannot be evaluated in WHERE.",
        ],
        source_url="https://en.wikipedia.org/wiki/Having_(SQL)",
    ),
    "python_mutable_defaults": Question(
        concept_id="python_mutable_defaults",
        topic_name="Python: Mutable Default Arguments Bug",
        prompt_text=(
            "In Python, why is defining a function with a mutable default argument like `def add_item(item, items=[]):` "
            "considered an antipattern, and what is the idiomatic Pythonic fix?"
        ),
        code_context="""def append_to(element, target=[]):
    target.append(element)
    return target

# append_to(1) -> [1]
# append_to(2) -> [1, 2]  <-- Unexpected persistence!""",
        options={
            "A": "Python creates a new list instance on every call, wasting heap memory; fix by using a tuple.",
            "B": "Default arguments are evaluated once at definition time, sharing the list across calls; fix with target=None.",
            "C": "Python raises a compile-time SyntaxError when a mutable literal is used as a default parameter.",
            "D": "Mutable defaults cause variables to leak into global module scope; fix with global target.",
        },
        correct_option="B",
        explanation=(
            "Default parameter expressions are evaluated once when the function definition is executed. "
            "The same list is reused across calls. The fix is `target=None` with `if target is None: target = []`."
        ),
        follow_up_prompt=(
            "Default parameter values are evaluated once when the function is defined, not each time it is called. "
            "How does using `target=None` inside the signature resolve this shared-reference issue?"
        ),
        rubric_criteria=[
            "Default argument is evaluated once at function definition time, sharing the same list across invocations.",
            "Fix: use `target=None` as default, then inside function check `if target is None: target = []`.",
        ],
        source_url="https://docs.python.org/3/tutorial/controlflow.html#default-argument-values",
    ),
    "dp_memoization_base": Question(
        concept_id="dp_memoization_base",
        topic_name="Dynamic Programming: Overlapping Subproblems & Memoization",
        prompt_text=(
            "What are the two core properties a computational problem must possess to be solvable "
            "using Dynamic Programming, and how does memoization prevent exponential time complexity?"
        ),
        code_context="""# Naive Fibonacci: O(2^n)
def fib(n):
    if n <= 1: return n
    return fib(n-1) + fib(n-2)

# Memoized Fibonacci: O(n)
memo = {}
...""",
        options={
            "A": "Greedy choice property and Divide-and-conquer; memoization sorts the problem space.",
            "B": "Optimal substructure and Overlapping subproblems; memoization caches intermediate results.",
            "C": "Disjoint subproblems and Heuristic pruning; memoization replaces recursion with threads.",
            "D": "Linear time bounds and Polynomial storage; memoization compresses DAG nodes.",
        },
        correct_option="B",
        explanation=(
            "Dynamic Programming requires optimal substructure and overlapping subproblems. "
            "Memoization caches subproblem outputs so each unique subproblem is computed only once."
        ),
        follow_up_prompt=(
            "If a problem only has optimal substructure but NO overlapping subproblems (e.g. Merge Sort), "
            "does dynamic programming provide any performance benefit over standard divide-and-conquer?"
        ),
        rubric_criteria=[
            "Two properties: Optimal Substructure and Overlapping Subproblems.",
            "Memoization caches intermediate subproblem results to avoid redundant recursive recomputation.",
            "Reduces time complexity from exponential to polynomial/linear.",
        ],
        source_url="https://en.wikipedia.org/wiki/Dynamic_programming#Overview",
    ),
    "graph_cycle_detection": Question(
        concept_id="graph_cycle_detection",
        topic_name="Graph Algorithms: Directed Graph Cycle Detection",
        prompt_text=(
            "When using Depth-First Search (DFS) to detect a cycle in a DIRECTED graph, "
            "why is a simple binary `visited` boolean set insufficient, and what 3-color state model is required?"
        ),
        code_context="""# Graph node states:
# 0: Unvisited (White)
# 1: Currently in recursion stack / Active path (Gray)
# 2: Fully explored (Black)""",
        options={
            "A": "A 2-color visited set is sufficient; any visited node indicates a cycle.",
            "B": "A 3-color model (White/Gray/Black) is required; a cycle is confirmed only by a Back Edge to a Gray node.",
            "C": "Directed graph cycle detection requires Dijkstra's algorithm; DFS cannot detect cycles.",
            "D": "A 4-color model is mandatory to account for undirected bridge edges.",
        },
        correct_option="B",
        explanation=(
            "In directed graphs, an already visited node may be reached via a cross edge without creating a cycle. "
            "A 3-color model detects cycles by identifying Back Edges to nodes currently in the recursion stack (Gray)."
        ),
        follow_up_prompt=(
            "What kind of graph edge indicates a cycle: a Tree edge, a Cross edge, or a Back edge to an ancestor "
            "currently in the active call stack?"
        ),
        rubric_criteria=[
            "A cycle in a directed graph is detected only when encountering a Back Edge (node in current recursion stack).",
            "A simple visited set cannot distinguish between a cross edge to an already completed subtree versus a true back-cycle.",
            "3 states: Unvisited (White), In-Progress / In-Stack (Gray), Completely Finished (Black).",
        ],
        source_url="https://en.wikipedia.org/wiki/Cycle_(graph_theory)#Cycle_detection",
    ),
}


class InternetQAProvider:
    """Fetches concept questions, code context, and rubrics from internet sources and curated catalogs."""

    def __init__(self, timeout: float = 6.0):
        self.timeout = timeout
        self.headers = {
            "User-Agent": "MindMesh-Agentathon/1.0 (educational CS study tool; contact@mindmesh.local)"
        }

    def list_curated_topics(self) -> List[Dict[str, str]]:
        """Returns a list of curated topics available immediately."""
        return [
            {"concept_id": q.concept_id, "topic_name": q.topic_name or q.concept_id}
            for q in CURATED_TOPICS.values()
        ]

    def get_question(self, topic_or_id: str) -> Question:
        """
        Retrieves a Question for the given topic:
        1. Checks curated catalog first (exact key or partial match).
        2. If not found, fetches live from Wikipedia / Internet knowledge and synthesizes a Question.
        """
        cleaned = topic_or_id.strip()
        slug = self._slugify(cleaned)

        # 1. Exact catalog match
        if slug in CURATED_TOPICS:
            return CURATED_TOPICS[slug]

        # 2. Case-insensitive name match
        for q in CURATED_TOPICS.values():
            if q.topic_name and cleaned.lower() in q.topic_name.lower():
                return q

        # 3. Live internet fetch
        return self.fetch_from_internet(cleaned)

    def fetch_from_internet(self, topic_query: str) -> Question:
        """
        Fetches educational background from the internet (Wikipedia REST API)
        and constructs a structured Question with rubric criteria.
        """
        slug = self._slugify(topic_query)
        clean_title = topic_query.strip().replace(" ", "_")
        api_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(clean_title)}"

        extract = None
        source_url = f"https://en.wikipedia.org/wiki/{clean_title}"
        topic_title = topic_query.title()

        try:
            with httpx.Client(timeout=self.timeout, headers=self.headers) as client:
                resp = client.get(api_url)
                if resp.status_code == 200:
                    data = resp.json()
                    extract = data.get("extract")
                    topic_title = data.get("title", topic_query.title())
                    if "content_urls" in data and "desktop" in data["content_urls"]:
                        source_url = data["content_urls"]["desktop"].get("page", source_url)
                else:
                    # Try search endpoint if exact title didn't match
                    search_url = f"https://en.wikipedia.org/w/api.php?action=opensearch&search={urllib.parse.quote(topic_query)}&limit=1&namespace=0&format=json"
                    search_resp = client.get(search_url)
                    if search_resp.status_code == 200:
                        s_data = search_resp.json()
                        if len(s_data) > 1 and len(s_data[1]) > 0:
                            found_title = s_data[1][0]
                            sub_api = f"https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(found_title.replace(' ', '_'))}"
                            sub_resp = client.get(sub_api)
                            if sub_resp.status_code == 200:
                                sub_data = sub_resp.json()
                                extract = sub_data.get("extract")
                                topic_title = sub_data.get("title", found_title)
                                if "content_urls" in sub_data and "desktop" in sub_data["content_urls"]:
                                    source_url = sub_data["content_urls"]["desktop"].get("page", source_url)
        except Exception:
            # Resilient offline/network fallback
            pass

        # Synthesize question based on fetched or fallback knowledge
        if not extract:
            extract = (
                f"In computer science, {topic_title} is a core foundational concept requiring precise understanding "
                f"of execution flow, constraints, and algorithmic correctness."
            )

        prompt_text = (
            f"Based on fundamental computer science principles regarding '{topic_title}':\n"
            f"{extract[:240]}...\n\n"
            f"What is the key technical requirement, invariant, or common pitfall associated with this concept, "
            f"and how should it be correctly handled in code or architecture?"
        )

        code_context = f"# Concept: {topic_title}\n# Provide the correct implementation or explanation answering the question."

        follow_up_prompt = (
            f"Consider edge cases or common misconceptions for '{topic_title}'. "
            f"Why does a naive approach or incorrect assumption fail under strict testing? "
            f"Please clarify your answer with the precise technical condition."
        )

        rubric_criteria = [
            f"Answer must accurately describe the core technical invariant of {topic_title}.",
            "Must avoid common logical flaws or syntax mistakes.",
            "Must clearly specify how edge cases are safely handled.",
        ]

        options = {
            "A": f"The concept relies on an unconstrained heuristic that ignores boundary conditions.",
            "B": f"Correctly adheres to {topic_title} principles: preserves core invariants and safely handles edge cases.",
            "C": f"Applies an inverted assumption where base checks or termination rules are bypassed.",
            "D": f"Applies only to deprecated legacy systems and cannot be utilized in modern implementations.",
        }

        explanation = (
            f"Adheres to core technical principles of {topic_title} as established in authoritative literature: "
            f"{extract[:200]}..."
        )

        return Question(
            concept_id=slug,
            topic_name=topic_title,
            prompt_text=prompt_text,
            code_context=code_context,
            options=options,
            correct_option="B",
            explanation=explanation,
            follow_up_prompt=follow_up_prompt,
            rubric_criteria=rubric_criteria,
            source_url=source_url,
        )

    def _slugify(self, text: str) -> str:
        s = text.lower().strip()
        s = re.sub(r"[^a-z0-9]+", "_", s)
        return s.strip("_") or "concept"
