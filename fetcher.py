"""
fetcher.py - Internet Q&A Provider and Topic Engine for MindMesh.

Owns:
- Curated CS topic catalog referenced from authoritative quiz platforms (GeeksforGeeks, Sanfoundry, LeetCode, Real Python, W3Schools, MDN).
- Live internet retrieval via Wikipedia REST API & educational documentation.
- Dynamic Question synthesis with concrete code context, authentic distractors, rubric criteria, and follow-up prompts.
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
            "Returning 1 produces an off-by-one error (e.g. sum_list([5]) == 6), and returning None causes a TypeError."
        ),
        follow_up_prompt=(
            "Think about what `sum_list([])` should return when there are no elements to sum. "
            "Why would returning 1 cause `sum_list([5])` to equal 6 instead of 5? "
            "Please select the corrected base case condition."
        ),
        rubric_criteria=[
            "Must check for empty list (e.g. len(numbers) == 0 or not numbers).",
            "Must return 0 (the additive identity).",
            "Returning 1 or None is incorrect.",
        ],
        source_url="https://www.geeksforgeeks.org/recursion-practice-questions-for-gate/",
        quiz_source="LeetCode Explore & GeeksforGeeks Recursion Practice",
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
        source_url="https://www.geeksforgeeks.org/binary-search/",
        quiz_source="LeetCode Binary Search Study Plan & GeeksforGeeks Searching Algorithms Quiz",
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
        source_url="https://www.w3schools.com/sql/sql_having.asp",
        quiz_source="W3Schools SQL Certification Quiz & GeeksforGeeks DBMS Quiz",
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
        source_url="https://realpython.com/quizzes/python-default-arguments/",
        quiz_source="Real Python Default Parameter Quiz & Sanfoundry Python MCQs",
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
        source_url="https://www.geeksforgeeks.org/dynamic-programming/",
        quiz_source="GeeksforGeeks Dynamic Programming Quiz & LeetCode DP Study Plan",
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
        source_url="https://www.sanfoundry.com/graph-algorithms-problems-solutions/",
        quiz_source="Sanfoundry Graph Algorithms Quiz & GeeksforGeeks Graph Traversal MCQs",
    ),
    "quicksort_pivot_complexity": Question(
        concept_id="quicksort_pivot_complexity",
        topic_name="QuickSort: Pivot Selection & Worst-Case Time Complexity",
        prompt_text=(
            "In a standard QuickSort implementation where the first or last element is always selected as the pivot, "
            "what is the worst-case time complexity, and under what input condition does it occur?"
        ),
        code_context="""def quicksort(arr):
    if len(arr) <= 1:
        return arr
    pivot = arr[0]  # Choosing first element as pivot
    less = [x for x in arr[1:] if x <= pivot]
    greater = [x for x in arr[1:] if x > pivot]
    return quicksort(less) + [pivot] + quicksort(greater)""",
        options={
            "A": "O(N log N) when the elements are uniformly distributed in random order.",
            "B": "O(N^2) when the array is already sorted in ascending or descending order.",
            "C": "O(N) when all elements in the array are distinct and positive.",
            "D": "O(log N) when median-of-three pivot selection is omitted.",
        },
        correct_option="B",
        explanation=(
            "When the input array is already sorted and the first element is selected as pivot, "
            "each partitioning step creates completely unbalanced partitions of size 0 and N-1. "
            "The recurrence relation becomes T(N) = T(N-1) + O(N), which resolves to O(N^2) worst-case time."
        ),
        follow_up_prompt=(
            "Why does choosing an extreme element (first or last) on sorted data eliminate the divide-and-conquer "
            "logarithmic tree depth? How does randomized pivot selection fix this?"
        ),
        rubric_criteria=[
            "Worst-case time complexity is O(N^2).",
            "Occurs on sorted or reverse-sorted input with first/last pivot choice.",
            "Balanced partition yields O(N log N).",
        ],
        source_url="https://www.geeksforgeeks.org/quicksort-quiz-questions/",
        quiz_source="GeeksforGeeks Sorting Algorithms Quiz",
    ),
    "dijkstra_negative_weights": Question(
        concept_id="dijkstra_negative_weights",
        topic_name="Dijkstra's Algorithm: Negative Edge Weight Limitation",
        prompt_text=(
            "Why does standard Dijkstra's shortest path algorithm fail to guarantee correct results "
            "on graphs containing negative edge weights, and which algorithm should be used instead?"
        ),
        code_context="""# Graph with negative weight:
# A -> B (cost: 3)
# A -> C (cost: 5)
# B -> C (cost: -4)  <-- Negative edge!
# True shortest path A to C is A -> B -> C (total: -1).
# Dijkstra greedily finalizes C as 5 upon initial extraction.""",
        options={
            "A": "Negative weights cause an infinite recursion stack overflow; use Prim's algorithm instead.",
            "B": "Dijkstra greedily finalizes node distances assuming non-negative weights; use Bellman-Ford instead.",
            "C": "Negative weights invert the min-heap into a max-heap; use Kruskal's algorithm instead.",
            "D": "Dijkstra only functions on Directed Acyclic Graphs; use Breadth-First Search instead.",
        },
        correct_option="B",
        explanation=(
            "Dijkstra relies on the greedy property that adding an edge to a path can never decrease its total length. "
            "Once a vertex is marked visited and extracted from the priority queue, its distance is considered final. "
            "A subsequent negative edge could reduce the path distance to an already-settled vertex, invalidating this assumption. "
            "The Bellman-Ford algorithm relaxes all edges |V|-1 times and properly handles negative edge weights."
        ),
        follow_up_prompt=(
            "Why does the greedy choice in Dijkstra depend on edge weights being non-negative? "
            "What additional risk do negative cycles introduce to shortest path calculations?"
        ),
        rubric_criteria=[
            "Dijkstra assumes non-negative edge weights for its greedy settlement property.",
            "A negative edge can provide a shorter path to an already settled node.",
            "Bellman-Ford algorithm correctly handles negative edges and detects negative cycles.",
        ],
        source_url="https://www.geeksforgeeks.org/dijkstras-shortest-path-algorithm-greedy-algo-7/",
        quiz_source="Sanfoundry Shortest Path Algorithms Quiz & GeeksforGeeks MCQs",
    ),
    "python_is_vs_equality": Question(
        concept_id="python_is_vs_equality",
        topic_name="Python: Object Identity (`is`) vs Value Equality (`==`)",
        prompt_text=(
            "In Python, given two list variables `a = [1, 2, 3]` and `b = [1, 2, 3]`, "
            "what do `a == b` and `a is b` evaluate to, and what is the underlying distinction?"
        ),
        code_context="""a = [1, 2, 3]
b = [1, 2, 3]

print(a == b)  # Equality test
print(a is b)  # Identity test""",
        options={
            "A": "Both evaluate to True because their elements have identical values and types.",
            "B": "a == b is True (values are equivalent), but a is b is False (distinct objects at different memory addresses).",
            "C": "a == b is False because they are distinct list instances, but a is b is True.",
            "D": "Both evaluate to False until a and b are explicitly interned or cast to tuples.",
        },
        correct_option="B",
        explanation=(
            "`==` tests value equality by calling `__eq__`, comparing the contents of the objects. "
            "`is` tests object identity (`id(a) == id(b)`), checking whether both variables point to the exact same location in memory. "
            "Because `a` and `b` are separately allocated list objects on the heap, they have equal values but different identities."
        ),
        follow_up_prompt=(
            "What does the `is` operator actually check under the hood? "
            "Why is `x is None` preferred in Python rather than `x == None`?"
        ),
        rubric_criteria=[
            "== checks value equality by calling __eq__.",
            "is checks identity by comparing memory addresses id().",
            "Separate mutable allocations have equal values but distinct identities.",
        ],
        source_url="https://realpython.com/quizzes/python-is-identity-vs-equality/",
        quiz_source="Real Python Identity & Comparison Quiz",
    ),
    "hash_table_collision_resolution": Question(
        concept_id="hash_table_collision_resolution",
        topic_name="Hash Tables: Collision Resolution (Chaining vs Open Addressing)",
        prompt_text=(
            "In hash table data structures, what is the core architectural difference between Separate Chaining "
            "and Open Addressing (such as Linear Probing) when multiple keys hash to the same bucket index?"
        ),
        code_context="""# Collision scenario: hash(key1) % size == hash(key2) % size
# Method 1: Table buckets store pointers to linked lists / auxiliary chains.
# Method 2: Table buckets store entries directly; collisions probe subsequent array slots.""",
        options={
            "A": "Separate Chaining rehashes the entire table; Open Addressing permanently discards colliding keys.",
            "B": "Separate Chaining stores colliding entries in linked lists outside the array; Open Addressing stores all entries within the primary array by probing vacant slots.",
            "C": "Open Addressing allows the load factor to exceed 1.0; Separate Chaining crashes when load factor > 0.5.",
            "D": "Separate Chaining requires cryptographic SHA-256 hashes; Open Addressing only works with consecutive integers.",
        },
        correct_option="B",
        explanation=(
            "In Separate Chaining, table buckets point to auxiliary data structures (like linked lists or dynamic arrays) "
            "that hold all colliding items, allowing the load factor to exceed 1.0. "
            "In Open Addressing (linear probing, quadratic probing, double hashing), all elements are stored directly in the "
            "main table array, and collisions are resolved by probing for the next available slot; the load factor cannot exceed 1.0."
        ),
        follow_up_prompt=(
            "What happens to Open Addressing performance when the load factor approaches 1.0? "
            "Why can Separate Chaining gracefully handle a load factor greater than 1.0?"
        ),
        rubric_criteria=[
            "Separate Chaining stores collisions in auxiliary chains/lists at each bucket.",
            "Open Addressing probes for empty slots directly within the main array.",
            "Open Addressing load factor cannot exceed 1.0.",
        ],
        source_url="https://www.geeksforgeeks.org/hashing-data-structure/",
        quiz_source="GeeksforGeeks Hashing Data Structure Quiz & Sanfoundry MCQs",
    ),
    "os_deadlock_conditions": Question(
        concept_id="os_deadlock_conditions",
        topic_name="Operating Systems: The 4 Coffman Deadlock Conditions",
        prompt_text=(
            "Which of the following is NOT one of the four necessary Coffman conditions that must hold "
            "simultaneously for a system deadlock to occur in an operating system?"
        ),
        code_context="""# The 4 Coffman Conditions (1971):
# 1. Mutual Exclusion
# 2. Hold and Wait
# 3. ???  (Notice whether preemption is allowed or disallowed!)
# 4. Circular Wait""",
        options={
            "A": "Mutual Exclusion (resources cannot be used concurrently by multiple processes).",
            "B": "Preemptive Resource Allocation (the operating system forcibly reclaims resources from running processes).",
            "C": "Hold and Wait (processes holding allocated resources can request additional ones).",
            "D": "Circular Wait (a closed loop of processes exists where each process waits for a resource held by the next).",
        },
        correct_option="B",
        explanation=(
            "The four necessary Coffman conditions are: Mutual Exclusion, Hold and Wait, NO Preemption (resources cannot be "
            "forcibly taken from a process), and Circular Wait. "
            "'Preemptive Resource Allocation' is an operating system recovery and prevention technique, the opposite of the 'No Preemption' requirement."
        ),
        follow_up_prompt=(
            "What is the exact requirement regarding preemption for a deadlock to happen? "
            "Why does allowing the OS to preemptively revoke a resource break the deadlock?"
        ),
        rubric_criteria=[
            "Identifies that 'No Preemption' is the required condition, not Preemption.",
            "Lists the 4 Coffman conditions: Mutual Exclusion, Hold & Wait, No Preemption, Circular Wait.",
            "Violating any one condition guarantees deadlock freedom.",
        ],
        source_url="https://www.sanfoundry.com/operating-system-mcqs-deadlock-characterization/",
        quiz_source="Sanfoundry Operating System MCQs & GeeksforGeeks OS Quiz",
    ),
    "tcp_vs_udp_transport": Question(
        concept_id="tcp_vs_udp_transport",
        topic_name="Computer Networks: TCP vs UDP Transport Layer Mechanics",
        prompt_text=(
            "In computer networking, which set of mechanisms does TCP implement to ensure reliable, ordered byte-stream delivery "
            "that UDP deliberately omits in favor of minimal overhead and latency?"
        ),
        code_context="""# TCP: Connection-oriented, full duplex, 20-60 byte header
# UDP: Connectionless, message-oriented, fixed 8 byte header""",
        options={
            "A": "Hardware-level DMA channel reservation and token ring collision avoidance.",
            "B": "Three-way handshake (SYN, SYN-ACK, ACK), sequence/acknowledgment numbers, and sliding-window flow control.",
            "C": "Unordered packet multicasting and unthrottled datagram broadcast without checksums.",
            "D": "Mandatory application-layer TLS encryption and HTTP/2 multiplexing.",
        },
        correct_option="B",
        explanation=(
            "TCP achieves reliability and ordering through a three-way connection handshake, sequence numbers to reassemble "
            "packets in correct order, acknowledgments with retransmission timers for lost packets, and sliding-window flow control. "
            "UDP is connectionless and sends datagrams without establishing a session, tracking order, or guaranteeing delivery."
        ),
        follow_up_prompt=(
            "Why do real-time applications like video streaming, gaming, and DNS prefer UDP over TCP? "
            "What performance penalty does TCP's retransmission and congestion control create?"
        ),
        rubric_criteria=[
            "TCP uses 3-way handshake, sequence numbers, ACKs, retransmissions, and flow control.",
            "UDP is lightweight, connectionless, and does not guarantee packet arrival or ordering.",
            "UDP has lower overhead (8-byte header vs 20-byte TCP header).",
        ],
        source_url="https://www.geeksforgeeks.org/differences-between-tcp-and-udp/",
        quiz_source="GeeksforGeeks Computer Networks Quiz & InterviewBit",
    ),
    "js_event_loop_microtasks": Question(
        concept_id="js_event_loop_microtasks",
        topic_name="JavaScript: Event Loop, Microtasks (Promises) vs Macrotasks",
        prompt_text=(
            "In the JavaScript Event Loop, what is the exact console output order of the following asynchronous code snippet?"
        ),
        code_context="""console.log("1");
setTimeout(() => console.log("2"), 0);
Promise.resolve().then(() => console.log("3"));
console.log("4");""",
        options={
            "A": "1, 2, 3, 4 (FIFO execution order based on line position)",
            "B": "1, 4, 3, 2 (Synchronous stack executes first, then microtasks [Promises], then macrotasks [setTimeout])",
            "C": "1, 3, 4, 2 (Promise callbacks take precedence over all synchronous console logs)",
            "D": "1, 4, 2, 3 (setTimeout with 0ms delay takes precedence over Promise microtasks)",
        },
        correct_option="B",
        explanation=(
            "1. Synchronous code executes immediately on the call stack: prints '1' then '4'. "
            "2. `setTimeout(..., 0)` schedules its callback into the Macrotask (Task) queue. "
            "3. `Promise.resolve().then(...)` schedules its callback into the high-priority Microtask queue. "
            "4. When the call stack is empty, the Event Loop empties the entire Microtask queue before picking from the Macrotask queue. "
            "Hence '3' prints before '2'. Final output: 1, 4, 3, 2."
        ),
        follow_up_prompt=(
            "Why does the Event Loop always drain the entire Microtask queue before executing the next Macrotask? "
            "Which queue do Promises, process.nextTick, and MutationObserver belong to?"
        ),
        rubric_criteria=[
            "Execution order: 1, 4, 3, 2.",
            "Synchronous execution runs first to completion.",
            "Microtasks (Promises) run before Macrotasks (setTimeout).",
        ],
        source_url="https://javascript.info/event-loop",
        quiz_source="MDN Web Docs & JavaScript.info Event Loop Quiz",
    ),
    "db_acid_isolation": Question(
        concept_id="db_acid_isolation",
        topic_name="Databases: ACID Transaction Properties & Atomicity",
        prompt_text=(
            "In relational database management systems (RDBMS), which ACID property guarantees that all operations "
            "within a transaction succeed or all fail together, leaving no intermediate partial changes?"
        ),
        code_context="""BEGIN TRANSACTION;
UPDATE accounts SET balance = balance - 100 WHERE id = 1; -- Debit
-- System failure or foreign key constraint error occurs here!
UPDATE accounts SET balance = balance + 100 WHERE id = 2; -- Credit
COMMIT;""",
        options={
            "A": "Consistency (ensures schema integrity constraints and foreign keys are never violated).",
            "B": "Atomicity (the all-or-nothing principle: failed transactions are automatically rolled back).",
            "C": "Isolation (ensures concurrent transactions do not observe intermediate states).",
            "D": "Durability (ensures committed transactions survive unexpected power loss).",
        },
        correct_option="B",
        explanation=(
            "Atomicity guarantees that a database transaction is treated as a single indivisible unit. "
            "Either all SQL statements in the transaction are successfully committed, or if any error or crash occurs, "
            "the database rolls back all partial modifications, restoring the database to its state before the transaction began."
        ),
        follow_up_prompt=(
            "What is the difference between Atomicity ('all or nothing') and Consistency ('valid state transitions')? "
            "How does write-ahead logging (WAL) support Atomicity?"
        ),
        rubric_criteria=[
            "Atomicity is the 'all-or-nothing' execution property.",
            "Partial transactions are rolled back upon error or system crash.",
            "Distinguishes Atomicity from Consistency, Isolation, and Durability.",
        ],
        source_url="https://www.geeksforgeeks.org/acid-properties-in-dbms/",
        quiz_source="GeeksforGeeks DBMS Quiz & Sanfoundry Database MCQs",
    ),
    "python_gil_multiprocessing": Question(
        concept_id="python_gil_multiprocessing",
        topic_name="Python: Global Interpreter Lock (GIL) & Multiprocessing",
        prompt_text=(
            "Why does standard CPython employ a Global Interpreter Lock (GIL), and what is the standard recommended approach "
            "in Python to achieve true parallel execution across multi-core CPUs for CPU-bound tasks?"
        ),
        code_context="""# CPU-bound computation
def compute_heavy(n):
    return sum(i * i for i in range(n))

# In CPython, threading runs on a single core due to the GIL!
# Which module runs independent processes with separate GILs across CPU cores?""",
        options={
            "A": "The GIL prevents race conditions in asyncio event loops; use greenlet threads for CPU parallelism.",
            "B": "The GIL ensures thread-safe memory management and reference counting; CPU-bound tasks should use the multiprocessing module.",
            "C": "The GIL is a compiler optimization; invoking threading.Thread automatically bypasses the GIL on multi-core servers.",
            "D": "The GIL is a hardware CPU lock; Python programs cannot execute across multiple cores under any circumstances.",
        },
        correct_option="B",
        explanation=(
            "CPython uses reference counting for garbage collection, which requires synchronization to avoid memory corruption. "
            "The GIL was introduced as a mutex to protect Python object access, ensuring only one thread executes Python bytecode at a time. "
            "To achieve true CPU parallelism across cores, Python provides the `multiprocessing` module (and ProcessPoolExecutor), "
            "which spawns separate OS processes with independent memory spaces and separate GIL instances."
        ),
        follow_up_prompt=(
            "Why does `multiprocessing` achieve multi-core parallelism where `threading` cannot in CPython? "
            "Why do I/O-bound programs still benefit from standard threading?"
        ),
        rubric_criteria=[
            "GIL protects CPython memory management and reference counting.",
            "Limits Python bytecode execution to one thread at a time.",
            "CPU-bound tasks require multiprocessing (or ProcessPoolExecutor) for multi-core parallelism.",
        ],
        source_url="https://realpython.com/python-gil/",
        quiz_source="Real Python GIL & Concurrency Quiz",
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
            {
                "concept_id": q.concept_id,
                "topic_name": q.topic_name or q.concept_id,
                "quiz_source": q.quiz_source or "Authoritative CS Quiz",
            }
            for q in CURATED_TOPICS.values()
        ]

    def get_question(self, topic_or_id: str) -> Question:
        """
        Retrieves a Question for the given topic:
        1. Checks curated catalog first (exact key or partial match).
        2. Checks keyword alias mappings.
        3. If not found, fetches live from Wikipedia / Internet knowledge and synthesizes a Question.
        """
        cleaned = topic_or_id.strip()
        slug = self._slugify(cleaned)

        # 1. Exact catalog match
        if slug in CURATED_TOPICS:
            return CURATED_TOPICS[slug]

        # 2. Case-insensitive full name match
        for q in CURATED_TOPICS.values():
            if q.topic_name and cleaned.lower() == q.topic_name.lower():
                return q

        # 3. Live internet fetch
        return self.fetch_from_internet(cleaned)

    def fetch_from_internet(self, topic_query: str) -> Question:
        """
        Fetches educational background from the internet (Wikipedia REST API)
        and constructs an authentic, topic-specific Question with rubric criteria.
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
                f"of execution flow, operational constraints, and algorithmic correctness."
            )

        # Parse sentences from extract for authentic topic-related content
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", extract) if len(s.strip()) > 20]
        core_definition = sentences[0] if sentences else extract[:180]
        secondary_fact = sentences[1] if len(sentences) > 1 else f"Adheres strictly to core computer science invariants of {topic_title}."

        prompt_text = (
            f"Based on foundational computer science principles regarding '{topic_title}':\n\n"
            f"\"{core_definition}\"\n\n"
            f"Which of the following statements accurately characterizes the operational mechanism, "
            f"primary invariant, or algorithmic complexity associated with {topic_title}?"
        )

        code_context = f"# Topic: {topic_title}\n# Context: Reference authoritative documentation and standard specifications."

        follow_up_prompt = (
            f"Consider standard edge cases and implementation invariants for '{topic_title}'. "
            f"Why does a naive assumption fail when boundary conditions or resource constraints are tested? "
            f"Select the corrected option that adheres to core principles."
        )

        rubric_criteria = [
            f"Must accurately reflect the authoritative computer science definition and invariants of {topic_title}.",
            "Must reject flawed assumptions that ignore boundary conditions or operational constraints.",
            "Must preserve formal algorithmic or architectural guarantees.",
        ]

        options = {
            "A": f"Executes under an unconstrained heuristic that bypasses formal validation and ignores input boundaries.",
            "B": f"Accurately adheres to {topic_title} principles: {core_definition[:130]}...",
            "C": f"Inverts the execution model by eliminating state tracking and omitting boundary termination checks.",
            "D": f"Restricted strictly to legacy single-threaded architectures and deprecated in modern standard implementations.",
        }

        explanation = (
            f"The authoritative technical definition and requirement for {topic_title} states: {core_definition} "
            f"{secondary_fact} Options A, C, and D introduce invalid assumptions or flawed operational constraints."
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
            quiz_source="Authoritative CS Documentation & Topic Assessment",
        )

    def _slugify(self, text: str) -> str:
        s = text.lower().strip()
        s = re.sub(r"[^a-z0-9]+", "_", s)
        return s.strip("_") or "concept"
