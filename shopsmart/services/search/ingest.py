"""(Re)build the knowledge base from the database.

    python -m shopsmart.services.search.ingest
"""

from __future__ import annotations

import logging

from shopsmart.db import SessionLocal
from shopsmart.seed import load_policy_docs
from shopsmart.services.search.vectorstore import get_vectorstore, index_all


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    store = get_vectorstore()
    store.reset_collection()
    with SessionLocal() as db:
        added = load_policy_docs(db)
        db.commit()
        n = index_all(db, store)
    if added:
        print(f"loaded {added} new policy documents")
    print(f"indexed {n} chunks")


if __name__ == "__main__":
    main()
