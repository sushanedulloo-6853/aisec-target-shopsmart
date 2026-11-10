"""Quick offline-ish eval of the support prompts against a handful of canned conversations.

Run from the repo root:  uv run python scripts/eval_support_prompts.py
Prints the routed agent and reply for each case so we can eyeball regressions
before changing prompts.py.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("OPENAI_API_KEY", "sk-proj-fgE5IkLl1p6A6vB9oEvwMjXEiUG4We5328IoILfBFAKE")
os.environ.setdefault("DATABASE_URL", "sqlite:///data/shopsmart.db")

from langchain_core.messages import HumanMessage  # noqa: E402

from shopsmart.db import SessionLocal  # noqa: E402
from shopsmart.models import Merchant, User  # noqa: E402
from shopsmart.services.support.graph import build_support_graph, run_support_turn  # noqa: E402
from shopsmart.services.support.tools import customer_profile  # noqa: E402

CASES = [
    (10, "Where is my order 1002?"),
    (10, "The stove from order 1001 stopped working, can I get my money back?"),
    (11, "Can I send order 1004 to my office at 500 Market St instead?"),
    (20, "Is the jute rug OK in a bathroom?"),
]


def main() -> None:
    graph = build_support_graph()
    with SessionLocal() as db:
        for user_id, text in CASES:
            user = db.get(User, user_id)
            merchant = db.get(Merchant, user.merchant_id)
            result = run_support_turn(
                graph,
                [HumanMessage(text)],
                {
                    "user_id": user.id,
                    "merchant_id": user.merchant_id,
                    "customer_profile": customer_profile(user, merchant.name),
                },
            )
            print(f"[{result['agent']}] {text}\n  -> {result['reply']}\n  actions: {result['actions']}\n")


if __name__ == "__main__":
    main()
