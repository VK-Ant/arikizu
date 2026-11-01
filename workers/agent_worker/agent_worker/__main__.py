"""Arikizu agent worker: custom chatbots with capability routing.

Capabilities:

- agent.create         Create a new agent (name, system prompt, policy)
- agent.update         Edit an existing agent
- agent.delete         Remove an agent and its conversations
- agent.list           List all agents
- agent.get            Full detail for one agent (prompt, policy, capabilities)
- agent.chat           One chat turn: user says X -> model responds +
                         (optional) tool calls dispatched through policy
- agent.conversation   Full conversation history
- agent.conversation_list  Conversations for one agent
- agent.allowed_caps   Which capabilities an agent is allowed to call
- agent.policy_default Which policy a brand-new agent gets by default
- agent.backends       Reasoning worker reachable? MCP server up?
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import httpx

from arikizu_worker import Worker

from . import agents, policy as policy_mod, tools


def _reasoning_call(system_prompt: str, user_message: str,
                    conversation_history: list[dict],
                    max_tokens: int = 400) -> str:
    """One LLM call to the local reasoning worker over HTTP.

    We route through the HTTP router (same as any browser), so the
    reasoning backend selection (local-gguf vs HTTP vs builtin-kb) is
    reused without re-implementation.
    """
    # Flatten the history into a single context string. The reasoning
    # worker signature takes question/context/max_tokens.
    hist_lines = [f"[{t['role']}] {t['content']}" for t in conversation_history]
    context = system_prompt + "\n\n" + "\n".join(hist_lines) if hist_lines else system_prompt
    url = f"{agents.ARIKIZU_HTTP}/api/v1/call/reasoning/answer"
    try:
        r = httpx.post(url, json={"payload": {
            "question": user_message, "context": context, "max_tokens": max_tokens,
        }}, timeout=120)
        r.raise_for_status()
        body = r.json()
        return body.get("answer", "") or ""
    except Exception as e:
        return f"[reasoning backend unreachable: {e}]"


def _chat_turn(agent: agents.Agent, conversation_id: str,
               user_message: str, max_iterations: int = 3) -> dict[str, Any]:
    """One agent chat turn with up to `max_iterations` tool-call rounds.

    Flow:
      1. Store user message.
      2. Build system prompt + conversation history.
      3. Call reasoning for an assistant response.
      4. If the assistant emitted <tool_call> blocks, dispatch each
         through policy, feed the results back, loop up to max_iterations.
      5. Store the final assistant turn (with tool_call records).
    """
    agents.add_turn(conversation_id, "user", user_message)
    conv = agents.get_conversation(conversation_id)
    history = conv["turns"] if conv else []

    # Build the effective system prompt. The agent's own prompt plus a
    # footer describing which tools it may call and the output format for
    # tool invocations.
    allowed = policy_mod.allowed_capabilities(agent.policy)
    tool_doc_lines = [f"- {cap}" for cap in sorted(allowed["auto"] + allowed["ask"])][:40]
    tool_doc = "\n".join(tool_doc_lines) if tool_doc_lines else "(no tools allowed)"
    system = (
        f"{agent.system_prompt}\n\n"
        "You run inside Arikizu. You may call Arikizu capabilities when you need "
        "them. To call a tool, emit a block exactly like:\n"
        '<tool_call>{"capability": "worker.operation", "payload": {...}}</tool_call>\n'
        "Multiple tool calls are allowed per message. The system will run each "
        "allowed tool and return its result. Capabilities you may call:\n"
        f"{tool_doc}\n\n"
        "Capabilities marked ASK require human approval before running; do not "
        "promise the user the result will be immediate. Capabilities not in the "
        "list are DENIED; do not try to call them."
    )

    all_tool_results: list[dict] = []
    final_prose = ""
    for iteration in range(max_iterations):
        assistant_raw = _reasoning_call(system, user_message, history[:-1])
        prose, calls = tools.extract_tool_calls(assistant_raw)
        if not calls:
            final_prose = prose
            break
        results = tools.dispatch_all(calls, agent.policy)
        all_tool_results.extend(results)
        # If any call is awaiting approval, stop iterating and return now;
        # the next user turn will resume once operator approves.
        if any(r.get("awaiting_approval") for r in results):
            final_prose = prose + "\n\n(awaiting human approval on one or more tool calls)"
            break
        # Feed tool results back into the next loop as a system note
        user_message = (
            "Tool results:\n" + tools.format_tool_results(results) +
            "\n\nContinue answering the user's original question."
        )
        if iteration == max_iterations - 1:
            # Last iteration: wrap up
            final_prose = prose + "\n\n[tool call limit reached]"

    agents.add_turn(conversation_id, "assistant", final_prose, all_tool_results)
    return {
        "conversation_id": conversation_id,
        "assistant_message": final_prose,
        "tool_calls": all_tool_results,
    }


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-5s %(name)s - %(message)s",
    )
    logger = logging.getLogger("agent")

    worker = Worker("agent")

    # -------------------------------------------------------------------
    # Agent CRUD
    # -------------------------------------------------------------------

    @worker.handler("agent.create")
    def create(name: str = "", description: str = "",
               system_prompt: str = "",
               policy: dict | None = None) -> dict[str, Any]:
        if not name:
            return {"error": "name is required"}
        if not system_prompt:
            return {"error": "system_prompt is required"}
        policy = policy or {}
        problems = policy_mod.validate_policy(policy)
        if problems:
            return {"error": "policy invalid", "problems": problems}
        a = agents.create_agent(name, description, system_prompt, policy)
        logger.info("created agent %s (%s)", a.id, a.name)
        return a.to_dict()

    @worker.handler("agent.update")
    def update(agent_id: str = "", name: str | None = None,
               description: str | None = None,
               system_prompt: str | None = None,
               policy: dict | None = None) -> dict[str, Any]:
        if policy is not None:
            problems = policy_mod.validate_policy(policy)
            if problems:
                return {"error": "policy invalid", "problems": problems}
        a = agents.update_agent(agent_id, name, description, system_prompt, policy)
        if a is None:
            return {"error": f"agent {agent_id} not found"}
        return a.to_dict()

    @worker.handler("agent.delete")
    def delete(agent_id: str = "") -> dict[str, Any]:
        if agents.delete_agent(agent_id):
            return {"deleted": True, "agent_id": agent_id}
        return {"error": f"agent {agent_id} not found"}

    @worker.handler("agent.import")
    def import_json(definition: dict | None = None,
                    file_path: str = "") -> dict[str, Any]:
        """Create an agent from a JSON definition (dict or file path).

        definition: direct dict with {name, system_prompt, description?, policy?}
        file_path: path to a .json file with the same shape (relative to the
                   project root, so examples/agents/safety-inspector.json works)
        """
        if definition is None and file_path:
            try:
                from pathlib import Path
                root = Path(agents._project_root() if hasattr(agents, "_project_root")
                            else ".")
                p = Path(file_path)
                if not p.is_absolute():
                    p = root / file_path
                definition = json.loads(p.read_text())
            except Exception as e:
                return {"error": f"could not read {file_path}: {e}"}
        if not isinstance(definition, dict):
            return {"error": "definition must be a dict or file_path must point at JSON"}
        name = str(definition.get("name", "")).strip()
        prompt = str(definition.get("system_prompt", "")).strip()
        if not name or not prompt:
            return {"error": "name and system_prompt required"}
        policy = definition.get("policy") or {}
        problems = policy_mod.validate_policy(policy)
        if problems:
            return {"error": "policy invalid", "problems": problems}
        a = agents.create_agent(
            name=name,
            description=str(definition.get("description", "")),
            system_prompt=prompt,
            policy=policy,
        )
        logger.info("imported agent %s (%s)", a.id, a.name)
        return a.to_dict()

    @worker.handler("agent.list")
    def list_all(limit: int = 50) -> dict[str, Any]:
        return {"agents": [a.to_dict() for a in agents.list_agents(limit=limit)]}

    @worker.handler("agent.get")
    def get(agent_id: str = "") -> dict[str, Any]:
        a = agents.get_agent(agent_id)
        if a is None:
            return {"error": f"agent {agent_id} not found"}
        caps = policy_mod.allowed_capabilities(a.policy)
        return {**a.to_dict(), "allowed_capabilities": caps}

    # -------------------------------------------------------------------
    # Policy
    # -------------------------------------------------------------------

    @worker.handler("agent.policy_default")
    def policy_default() -> dict[str, Any]:
        return {
            "default_policy": policy_mod.DEFAULT_POLICY,
            "hard_deny": sorted(policy_mod.HARD_DENY),
            "actions": ["auto", "ask", "deny"],
        }

    @worker.handler("agent.allowed_caps")
    def allowed_caps(agent_id: str = "") -> dict[str, Any]:
        a = agents.get_agent(agent_id)
        if a is None:
            return {"error": f"agent {agent_id} not found"}
        return {"agent_id": agent_id,
                "allowed_capabilities": policy_mod.allowed_capabilities(a.policy)}

    # -------------------------------------------------------------------
    # Chat
    # -------------------------------------------------------------------

    @worker.handler("agent.chat")
    def chat(agent_id: str = "", conversation_id: str = "",
             message: str = "", max_iterations: int = 3) -> dict[str, Any]:
        if not message:
            return {"error": "message is required"}
        a = agents.get_agent(agent_id)
        if a is None:
            return {"error": f"agent {agent_id} not found"}
        if not conversation_id:
            conversation_id = agents.start_conversation(agent_id,
                title=message[:40])
        return _chat_turn(a, conversation_id, message,
                          max_iterations=int(max_iterations))

    @worker.handler("agent.conversation")
    def conversation(conversation_id: str = "") -> dict[str, Any]:
        c = agents.get_conversation(conversation_id)
        if c is None:
            return {"error": f"conversation {conversation_id} not found"}
        return c

    @worker.handler("agent.conversation_list")
    def conversation_list(agent_id: str = "", limit: int = 50) -> dict[str, Any]:
        return {"conversations": agents.list_conversations(agent_id, limit=int(limit))}

    # -------------------------------------------------------------------
    # Backends
    # -------------------------------------------------------------------

    @worker.handler("agent.backends")
    def backends() -> dict[str, Any]:
        """Report reasoning worker reachability and policy state."""
        try:
            r = httpx.get(f"{agents.ARIKIZU_HTTP}/api/v1/status", timeout=3)
            status = r.status_code
            reasoning_up = status == 200
        except Exception as e:
            reasoning_up = False
            status = 0
        return {
            "arikizu_http": agents.ARIKIZU_HTTP,
            "arikizu_reachable": reasoning_up,
            "http_status": status,
            "default_policy_size": len(policy_mod.DEFAULT_POLICY),
            "hard_deny_size": len(policy_mod.HARD_DENY),
        }

    asyncio.run(worker.run())


if __name__ == "__main__":
    main()
