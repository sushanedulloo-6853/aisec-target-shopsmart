"""Chroma-backed knowledge base: product catalog + merchant policy documents."""

from __future__ import annotations

import logging
import threading

import chromadb
from chromadb.config import Settings as ChromaSettings
from langchain_chroma import Chroma
from langchain_core.documents import Document
from sqlalchemy import select
from sqlalchemy.orm import Session

from shopsmart.config import get_settings
from shopsmart.llm import get_embeddings
from shopsmart.models import PolicyDoc, Product

log = logging.getLogger(__name__)

_store: Chroma | None = None
_lock = threading.Lock()


def get_vectorstore() -> Chroma:
    global _store
    with _lock:
        if _store is None:
            settings = get_settings()
            client = chromadb.PersistentClient(
                path=settings.chroma_dir, settings=ChromaSettings(anonymized_telemetry=False)
            )
            _store = Chroma(
                client=client,
                collection_name=settings.chroma_collection,
                embedding_function=get_embeddings(),
            )
        return _store


def set_vectorstore(store: Chroma | None) -> None:
    global _store
    _store = store


def _chunks(text: str, size: int = 800) -> list[str]:
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    out, buf = [], ""
    for para in paragraphs:
        if buf and len(buf) + len(para) > size:
            out.append(buf)
            buf = ""
        buf = f"{buf}\n\n{para}".strip()
    if buf:
        out.append(buf)
    return out or [text]


def product_document(product: Product) -> Document:
    text = (
        f"{product.name} ({product.category}) - ${product.price_cents / 100:.2f}. "
        f"{product.description} In stock: {product.stock}."
    )
    return Document(
        page_content=text,
        metadata={
            "kind": "product",
            "merchant_id": product.merchant_id,
            "product_id": product.id,
            "title": product.name,
        },
    )


def add_policy_doc(store: Chroma, doc: PolicyDoc) -> list[str]:
    docs = [
        Document(
            page_content=chunk,
            metadata={
                "kind": "policy",
                "merchant_id": doc.merchant_id,
                "doc_id": doc.id,
                "title": doc.title,
                "visibility": doc.visibility,
            },
        )
        for chunk in _chunks(doc.content)
    ]
    ids = [f"policy-{doc.id}-{i}" for i in range(len(docs))]
    store.add_documents(docs, ids=ids)
    return ids


def index_all(db: Session, store: Chroma | None = None) -> int:
    store = store or get_vectorstore()
    products = db.scalars(select(Product)).all()
    if products:
        store.add_documents([product_document(p) for p in products], ids=[f"product-{p.id}" for p in products])
    count = len(products)
    for doc in db.scalars(select(PolicyDoc)).all():
        count += len(add_policy_doc(store, doc))
    log.info("indexed %d chunks into %s", count, get_settings().chroma_collection)
    return count


def ensure_indexed(db: Session) -> Chroma:
    store = get_vectorstore()
    if store._collection.count() == 0:
        index_all(db, store)
    return store


def search_products(db: Session, query: str, merchant_id: int, k: int = 5) -> list[Document]:
    store = ensure_indexed(db)
    return store.similarity_search(
        query,
        k=k,
        filter={"$and": [{"kind": {"$eq": "product"}}, {"merchant_id": {"$eq": merchant_id}}]},
    )
