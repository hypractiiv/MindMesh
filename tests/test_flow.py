from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from flow import ANSWERING, RECORDED, SKIPPED, WAITING_FOLLOW_UP, ReviewFlow
from store import Store


class ReviewFlowTests(unittest.TestCase):
    def _flow(self, db_path: Path):
        store = Store(db_path)
        return ReviewFlow(store, today=date(2026, 9, 19)), store

    def test_confident_wrong_answer_requires_follow_up(self):
        with tempfile.TemporaryDirectory() as tmp:
            flow, store = self._flow(Path(tmp) / "mindmesh.db")
            started = flow.start(
                concept="recursion.base_case",
                question="Write the base case for a recursive function that sums a list of numbers.",
            )
            self.assertEqual(started.state, ANSWERING)

            first = flow.submit_answer(
                session_id=started.session_id,
                text="The base case is when the list is empty, return 1.",
                self_rating=4,
            )
            self.assertEqual(first.state, WAITING_FOLLOW_UP)

            second = flow.submit_answer(
                session_id=started.session_id,
                text="It needs to be 0, so the base case should return 0.",
                self_rating=None,
            )
            self.assertEqual(second.state, RECORDED)

            record = store.get_latest_record(session_id=started.session_id, kind="record")
            self.assertEqual(record["confidence"], 3)
            self.assertEqual(record["note"], "resolved on follow-up, not first attempt")
            self.assertEqual(record["next_review"], "2026-09-23")
            store.close()

    def test_timeout_writes_skipped_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            flow, store = self._flow(Path(tmp) / "mindmesh.db")
            started = flow.start(
                concept="recursion.base_case",
                question="Write the base case for a recursive function that sums a list of numbers.",
            )
            timed_out = flow.timeout(session_id=started.session_id)
            self.assertEqual(timed_out.state, SKIPPED)

            record = store.get_latest_record(session_id=started.session_id, kind="record")
            self.assertEqual(record["status"], SKIPPED)
            self.assertEqual(record["note"], "not confirmed - asked, no response")
            store.close()

    def test_sessions_resume_after_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "mindmesh.db"
            store = Store(db)
            flow = ReviewFlow(store)
            started = flow.start(
                concept="recursion.base_case",
                question="Write the base case for a recursive function that sums a list of numbers.",
            )
            store.close()

            reopened_store = Store(db)
            reopened_flow = ReviewFlow(reopened_store)
            resumed = reopened_flow.resume(session_id=started.session_id)
            self.assertEqual(resumed.state, ANSWERING)
            reopened_store.close()


if __name__ == "__main__":
    unittest.main()
