# MindMesh 8-Beat Judge Demo Script

This script corresponds directly to the official 8-beat sequence in Section 10 of the *MindMesh 5-Person Build & Preparation Plan*.

---

### Demo Objective
Prove in under 3 minutes that MindMesh is an **agentic system**:
1. It persists state.
2. It detects disagreement between confidence and correctness.
3. It changes course via an adaptive backward transition (`Checking` $\to$ `Waiting for follow-up`).
4. It keeps the human responsible for the answer.
5. It remembers what happened in a second encounter.

---

### The 8 Beats

| Beat | What Judges See | Script / Talking Points | Code Verification |
| :--- | :--- | :--- | :--- |
| **Beat 1** | Old autograder-passing recursion code snippet. | *"Yesterday, our student passed a standard unit test for summing a list recursively. But did they really understand the base case, or was it luck?"* | Initial prompt loaded with `QUESTION` context |
| **Beat 2** | Student submits wrong base case (`return 1`) and rates confidence `4/5`. | *"The student writes `if len(numbers) == 0: return 1` and marks their confidence as 4 out of 5. They think they are right, but they made a common flaw: returning the multiplicative identity for an addition problem."* | `step_answering` records `Answer(rating=4)` |
| **Beat 3** | Evaluator flags the answer as incorrect. | *"The evaluator checks the answer independently. It notes that returning 1 causes an off-by-one error on every list sum. A naive system would just fail them or trust their confidence. MindMesh notices the mismatch."* | `Verdict(passed=False, is_mismatch=True)` |
| **Beat 4** | System asks one targeted follow-up. | *"Here is the agentic loop: instead of terminating at 'Failed', the state machine takes a backward transition to `Waiting for follow-up`. The agent asks: 'Why would returning 1 cause sum_list([5]) to equal 6?' and pauses."* | Transition to `State.WAITING_FOR_FOLLOWUP` |
| **Beat 5** | Student answers correctly. | *"The student reflects on the question and submits the correction: `if not numbers: return 0`. The student remains responsible for producing the correct code."* | `step_followup` records Attempt 2; `Verdict(passed=True)` |
| **Beat 6** | Record shows confidence 3 and 'resolved on follow-up'. | *"The system transitions to `Recorded`. In SQLite, it stores confidence 3 and outcome 'resolved on follow-up', scheduling the next review in 2 days."* | SQLite stores `ConceptRecord` |
| **Beat 7** | Fast-forward the clock with debug mode. | *"Now we use our debug time-travel button to advance the clock 72 hours. The concept is now due for review again."* | `decay.fast_forward_record(hours=72)` |
| **Beat 8** | Reopen the concept; show improved first-try outcome. | *"When the student opens the concept for encounter #2, the system remembers their past encounter. This time, the student answers correctly on the first attempt with 5/5 confidence. The system rewards them with a 7-day review interval. Persistence matters."* | Encounter 2 query loaded from SQLite, record updated to `first_try_correct` |

---

### How to Run the Demo

#### Option A: Automated CLI Demo
Run the script directly from the terminal:
```powershell
python cli.py --demo
```

#### Option B: Interactive Web Demo (Streamlit)
Run the Streamlit application:
```powershell
streamlit run app.py
```
1. Click **Demo: Wrong Base Case (Beat 2)** and click **Submit Answer**.
2. Observe the **Confidence/Correctness Mismatch** alert and targeted question.
3. Click **Demo: Corrected Follow-up (Beat 5)** and click **Submit Follow-up**.
4. Observe the **Recorded** outcome and the updated SQLite audit stream.
5. Click **Fast-Forward (+72h)** in the sidebar.
6. Click **Demo: Correct Base Case (Beat 8)** and submit to complete Encounter #2.
