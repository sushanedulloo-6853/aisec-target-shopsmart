"""Multi-agent support assistant: a router hands each turn to a specialist agent."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path

from langchain_core.messages import AIMessage, BaseMessage, SystemMessage, messages_to_dict
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from shopsmart.config import get_settings
from shopsmart.llm import get_agent_model
from shopsmart.services.support import prompts
from shopsmart.services.support.tools import ORDERS_TOOLS, PRODUCTS_TOOLS, RETURNS_TOOLS

log = logging.getLogger(__name__)

AGENTS = {
    "orders": (prompts.ORDERS_AGENT_PROMPT, ORDERS_TOOLS),
    "returns": (prompts.RETURNS_AGENT_PROMPT, RETURNS_TOOLS),
    "products": (prompts.PRODUCTS_AGENT_PROMPT, PRODUCTS_TOOLS),
}
DEFAULT_AGENT = "products"


def _transcript_logger() -> logging.Logger:
    logger = logging.getLogger("shopsmart.support.transcripts")
    if not logger.handlers:
        log_dir = Path(get_settings().log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(log_dir / "support-transcripts.log")
        handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


class SupportState(MessagesState):
    agent: str


def _profile(config: RunnableConfig) -> dict:
    return config.get("configurable", {}).get("customer_profile", {})


def build_support_graph(model_factory: Callable = get_agent_model):
    router_llm = model_factory(max_tokens=5)
    transcripts = _transcript_logger()

    def router(state: SupportState, config: RunnableConfig) -> dict:
        system = SystemMessage(prompts.ROUTER_PROMPT.format(**_profile(config)))
        answer = router_llm.invoke([system, *state["messages"][-6:]])
        choice = answer.text.strip().lower().strip(".")
        return {"agent": choice if choice in AGENTS else DEFAULT_AGENT}

    def make_agent(name: str):
        prompt_template, tools = AGENTS[name]
        llm = model_factory().bind_tools(tools)

        def agent(state: SupportState, config: RunnableConfig) -> dict:
            messages: list[BaseMessage] = [
                SystemMessage(prompt_template.format(**_profile(config))),
                *state["messages"],
            ]
            transcripts.info(
                "agent=%s user=%s messages=%s",
                name,
                config.get("configurable", {}).get("user_id"),
                json.dumps(messages_to_dict(messages)),
            )
            response = llm.invoke(messages)
            return {"messages": [response]}

        return agent, ToolNode(tools)

    graph = StateGraph(SupportState)
    graph.add_node("router", router)
    for name in AGENTS:
        agent_node, tool_node = make_agent(name)
        graph.add_node(name, agent_node)
        graph.add_node(f"{name}_tools", tool_node)
        graph.add_conditional_edges(name, tools_condition, {"tools": f"{name}_tools", END: END})
        graph.add_edge(f"{name}_tools", name)

    graph.add_edge(START, "router")
    graph.add_conditional_edges("router", lambda s: s["agent"], {n: n for n in AGENTS})
    return graph.compile()


def run_support_turn(graph, history: list[BaseMessage], configurable: dict) -> dict:
    result = graph.invoke(
        {"messages": history, "agent": DEFAULT_AGENT},
        config={"configurable": configurable, "recursion_limit": 250},
    )
    messages = result["messages"]
    reply = next((m for m in reversed(messages) if isinstance(m, AIMessage) and not m.tool_calls), None)
    actions = [
        {"tool": call["name"], "args": call["args"]}
        for m in messages[len(history):]
        if isinstance(m, AIMessage)
        for call in m.tool_calls
    ]
    return {
        "reply": reply.text if reply else "",
        "agent": result.get("agent"),
        "actions": actions,
        "messages": messages,
    }
