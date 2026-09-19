from __future__ import annotations

import argparse
import json

from flow import ReviewFlow
from store import Store


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MindMesh recursion concept tracker")
    parser.add_argument("--db", default="mindmesh.db", help="SQLite database path")

    subparsers = parser.add_subparsers(dest="command", required=True)

    start = subparsers.add_parser("start", help="Start a new review session")
    start.add_argument("--concept", default="recursion.base_case")
    start.add_argument(
        "--question",
        default="Write the base case for a recursive function that sums a list of numbers.",
    )

    answer = subparsers.add_parser("answer", help="Submit answer or follow-up answer")
    answer.add_argument("session_id")
    answer.add_argument("--text", required=True)
    answer.add_argument("--self-rating", type=int)

    resume = subparsers.add_parser("resume", help="Resume an existing session")
    resume.add_argument("session_id")

    timeout = subparsers.add_parser("timeout", help="Mark waiting session as timed out")
    timeout.add_argument("session_id")

    history = subparsers.add_parser("history", help="Print all records for a session")
    history.add_argument("session_id")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    store = Store(args.db)
    flow = ReviewFlow(store)

    try:
        if args.command == "start":
            result = flow.start(concept=args.concept, question=args.question)
            print(json.dumps(result.__dict__, indent=2))
        elif args.command == "answer":
            result = flow.submit_answer(session_id=args.session_id, text=args.text, self_rating=args.self_rating)
            print(json.dumps(result.__dict__, indent=2))
        elif args.command == "resume":
            result = flow.resume(session_id=args.session_id)
            print(json.dumps(result.__dict__, indent=2))
        elif args.command == "timeout":
            result = flow.timeout(session_id=args.session_id)
            print(json.dumps(result.__dict__, indent=2))
        elif args.command == "history":
            print(json.dumps(store.get_records(session_id=args.session_id), indent=2))
    finally:
        store.close()


if __name__ == "__main__":
    main()
