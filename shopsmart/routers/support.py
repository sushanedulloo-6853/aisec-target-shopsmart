from __future__ import annotations

import uuid
from functools import lru_cache
from typing import Literal

from fastapi import APIRouter, Depends
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from shopsmart.auth import Principal, require_role
from shopsmart.db import get_db
from shopsmart.models import Merchant, User
from shopsmart.services.support.graph import build_support_graph, run_support_turn
from shopsmart.services.support.tools import customer_profile

router = APIRouter(prefix="/support", tags=["support"])

# (user_id, session_id) -> conversation
_sessions: dict[tuple[int, str], list[BaseMessage]] = {}

_ROLE_TO_MESSAGE = {"user": HumanMessage, "assistant": AIMessage, "system": SystemMessage}


@lru_cache
def get_support_graph():
    return build_support_graph()


class ChatTurn(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    session_id: str | None = None
    # Mobile clients keep the transcript locally and send it with every turn.
    history: list[ChatTurn] | None = None


class ChatResponse(BaseModel):
    reply: str
    session_id: str
    agent: str | None
    actions: list[dict]


@router.post("/chat", response_model=ChatResponse)
def chat(
    req: ChatRequest,
    principal: Principal = Depends(require_role("customer")),
    db: Session = Depends(get_db),
) -> ChatResponse:
    user = db.get(User, principal.user_id)
    merchant = db.get(Merchant, user.merchant_id)
    session_id = req.session_id or uuid.uuid4().hex
    key = (principal.user_id, session_id)

    if req.history is not None:
        history = [_ROLE_TO_MESSAGE[t.role](content=t.content) for t in req.history]
    else:
        history = list(_sessions.get(key, []))
    history.append(HumanMessage(content=req.message))

    result = run_support_turn(
        get_support_graph(),
        history,
        configurable={
            "user_id": principal.user_id,
            "merchant_id": principal.merchant_id,
            "customer_profile": customer_profile(user, merchant.name),
            "thread_id": session_id,
        },
    )
    _sessions[key] = result["messages"]
    return ChatResponse(reply=result["reply"], session_id=session_id, agent=result["agent"], actions=result["actions"])


@router.delete("/chat/{session_id}", status_code=204)
def end_chat(session_id: str, principal: Principal = Depends(require_role("customer"))) -> None:
    _sessions.pop((principal.user_id, session_id), None)
