"""Store policy & product Q&A over the knowledge base."""

from __future__ import annotations

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from sqlalchemy.orm import Session

from shopsmart.llm import get_chat_model
from shopsmart.models import Merchant
from shopsmart.services.search.vectorstore import ensure_indexed

QA_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are the shopping assistant for {store_name}. Answer the customer's question using the "
            "store information below. Quote exact numbers (prices, days, fees) when they appear. If the "
            "answer isn't in the information, say you don't know.\n\nStore information:\n{context}",
        ),
        ("human", "{question}"),
    ]
)


def retrieve_context(db: Session, question: str, k: int = 6):
    store = ensure_indexed(db)
    return store.similarity_search(question, k=k, filter={"kind": "policy"})


def answer_question(db: Session, question: str, merchant: Merchant, model=None) -> dict:
    docs = retrieve_context(db, question)
    context = "\n\n".join(f"[{d.metadata.get('title')}]\n{d.page_content}" for d in docs)
    chain = QA_PROMPT | (model or get_chat_model(max_tokens=600)) | StrOutputParser()
    answer = chain.invoke({"store_name": merchant.name, "context": context, "question": question})
    return {
        "answer": answer,
        "sources": [{"title": d.metadata.get("title"), "doc_id": d.metadata.get("doc_id")} for d in docs],
    }
