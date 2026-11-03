"""Model clients. Everything is created lazily so the API boots without credentials."""

from __future__ import annotations

from typing import Any

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from openai import OpenAI

from shopsmart.config import get_settings


def get_chat_model(**overrides: Any) -> ChatOpenAI:
    settings = get_settings()
    params: dict[str, Any] = {
        "model": settings.openai_model,
        "api_key": settings.openai_api_key,
        "base_url": settings.openai_base_url,
        "max_retries": 2,
    }
    params.update(overrides)
    return ChatOpenAI(**params)


def get_agent_model(**overrides: Any) -> ChatOpenAI:
    # Luna does function calling through the Responses API.
    return get_chat_model(use_responses_api=True, **overrides)


def get_embeddings() -> OpenAIEmbeddings:
    settings = get_settings()
    return OpenAIEmbeddings(
        model=settings.openai_embedding_model,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
    )


def get_openai_client() -> OpenAI:
    settings = get_settings()
    return OpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)
