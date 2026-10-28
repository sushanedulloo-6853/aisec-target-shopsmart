import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="shopsmart-tests-")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["LOG_DIR"] = f"{_tmp}/logs"
os.environ["CHROMA_DIR"] = f"{_tmp}/chroma"
os.environ["JWT_SECRET"] = "test-secret-0123456789abcdef0123456789"
os.environ.pop("OPENAI_API_KEY", None)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from langchain_core.language_models.chat_models import BaseChatModel  # noqa: E402
from langchain_core.messages import AIMessage  # noqa: E402
from langchain_core.outputs import ChatGeneration, ChatResult  # noqa: E402
from pydantic import Field  # noqa: E402

from shopsmart.auth import create_access_token, login_limiter  # noqa: E402
from shopsmart.db import Base, SessionLocal, get_engine  # noqa: E402
from shopsmart.models import User  # noqa: E402
from shopsmart.seed import seed  # noqa: E402


class ScriptedChatModel(BaseChatModel):
    """Returns queued AIMessages in order; records every prompt it receives."""

    responses: list = Field(default_factory=list)
    calls: list = Field(default_factory=list)
    call_kwargs: list = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.calls.append(messages)
        msg = self.responses.pop(0) if self.responses else AIMessage(content="ok")
        if isinstance(msg, str):
            msg = AIMessage(content=msg)
        return ChatResult(generations=[ChatGeneration(message=msg)])

    def bind_tools(self, tools, **kwargs):
        return self


@pytest.fixture(autouse=True)
def fresh_db():
    engine = get_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed(db)
    login_limiter.reset()
    yield


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


@pytest.fixture
def client():
    from shopsmart.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def token():
    def make(user_id: int) -> str:
        with SessionLocal() as s:
            return create_access_token(s.get(User, user_id))

    return make


@pytest.fixture
def auth(token):
    def headers(user_id: int) -> dict:
        return {"Authorization": f"Bearer {token(user_id)}"}

    return headers


@pytest.fixture
def scripted_model():
    return ScriptedChatModel()
