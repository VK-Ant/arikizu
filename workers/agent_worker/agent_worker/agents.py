"""Agent storage and chat-loop runtime.

Each agent is a persistent object:

    id, name, description, system_prompt, allowed_capabilities,
    policy (dict), created_at, updated_at

The runtime wraps conversations:

    conversation_id (string), agent_id, turns [(role, content, tool_calls)]

A chat turn runs reasoning via the local reasoning_worker (over HTTP against
the Arikizu HTTP router: no cross-worker IPC coupling). If the reasoning
model emits tool calls, we dispatch each one through the policy module and
either run it, queue it for approval, or deny it.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _project_root() -> Path:
    p = Path(os.getcwd()).resolve()
    for parent in [p] + list(p.parents):
        if (parent / "arikizu.yaml.example").exists() or \
           (parent / "capabilities.toml").exists() or \
           (parent / "Cargo.toml").exists():
            return parent
    return p


DB_PATH = os.environ.get("ARIKIZU_AGENT_DB", str(_project_root() / "arikizu.db"))
ARIKIZU_HTTP = os.environ.get("ARIKIZU_HTTP", "http://127.0.0.1:7000")


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH, timeout=5)
    c.row_factory = sqlite3.Row
    c.executescript("""
        CREATE TABLE IF NOT EXISTS agents (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            system_prompt TEXT NOT NULL,
            policy_json TEXT NOT NULL,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS agent_conversations (
            id TEXT PRIMARY KEY,
            agent_id TEXT NOT NULL,
            title TEXT,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            FOREIGN KEY (agent_id) REFERENCES agents(id)
        );
        CREATE TABLE IF NOT EXISTS agent_turns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            tool_calls_json TEXT,
            created_at REAL NOT NULL,
            FOREIGN KEY (conversation_id) REFERENCES agent_conversations(id)
        );
        CREATE INDEX IF NOT EXISTS ix_turns_conv ON agent_turns(conversation_id);
        CREATE INDEX IF NOT EXISTS ix_conv_agent ON agent_conversations(agent_id);
    """)
    return c


# ---------------------------------------------------------------------------
# Agent definition CRUD
# ---------------------------------------------------------------------------

@dataclass
class Agent:
    id: str
    name: str
    description: str
    system_prompt: str
    policy: dict[str, str]
    created_at: float
    updated_at: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _agent_from_row(row: sqlite3.Row) -> Agent:
    return Agent(
        id=row["id"], name=row["name"], description=row["description"] or "",
        system_prompt=row["system_prompt"],
        policy=json.loads(row["policy_json"]) if row["policy_json"] else {},
        created_at=row["created_at"], updated_at=row["updated_at"],
    )


def create_agent(name: str, description: str, system_prompt: str,
                 policy: dict[str, str] | None = None) -> Agent:
    aid = f"agent_{uuid.uuid4().hex[:12]}"
    now = time.time()
    with _conn() as c:
        c.execute(
            """INSERT INTO agents (id, name, description, system_prompt,
                                   policy_json, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (aid, name, description, system_prompt,
             json.dumps(policy or {}), now, now),
        )
    return Agent(aid, name, description, system_prompt, policy or {}, now, now)


def get_agent(agent_id: str) -> Agent | None:
    with _conn() as c:
        row = c.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
    return _agent_from_row(row) if row else None


def list_agents(limit: int = 50) -> list[Agent]:
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM agents ORDER BY updated_at DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
    return [_agent_from_row(r) for r in rows]


def update_agent(agent_id: str, name: str | None = None,
                 description: str | None = None,
                 system_prompt: str | None = None,
                 policy: dict[str, str] | None = None) -> Agent | None:
    cur = get_agent(agent_id)
    if cur is None:
        return None
    fields = []
    values: list[Any] = []
    if name is not None:
        fields.append("name = ?"); values.append(name)
    if description is not None:
        fields.append("description = ?"); values.append(description)
    if system_prompt is not None:
        fields.append("system_prompt = ?"); values.append(system_prompt)
    if policy is not None:
        fields.append("policy_json = ?"); values.append(json.dumps(policy))
    if not fields:
        return cur
    fields.append("updated_at = ?"); values.append(time.time())
    values.append(agent_id)
    with _conn() as c:
        c.execute(f"UPDATE agents SET {', '.join(fields)} WHERE id = ?", values)
    return get_agent(agent_id)


def delete_agent(agent_id: str) -> bool:
    with _conn() as c:
        cur = c.execute("DELETE FROM agents WHERE id = ?", (agent_id,))
        c.execute("DELETE FROM agent_turns WHERE conversation_id IN "
                  "(SELECT id FROM agent_conversations WHERE agent_id = ?)", (agent_id,))
        c.execute("DELETE FROM agent_conversations WHERE agent_id = ?", (agent_id,))
    return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Conversation + turn storage
# ---------------------------------------------------------------------------

def start_conversation(agent_id: str, title: str = "") -> str:
    cid = f"conv_{uuid.uuid4().hex[:12]}"
    now = time.time()
    with _conn() as c:
        c.execute(
            """INSERT INTO agent_conversations (id, agent_id, title, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?)""",
            (cid, agent_id, title or "new conversation", now, now),
        )
    return cid


def add_turn(conversation_id: str, role: str, content: str,
             tool_calls: list[dict] | None = None) -> int:
    with _conn() as c:
        cur = c.execute(
            """INSERT INTO agent_turns (conversation_id, role, content, tool_calls_json, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (conversation_id, role, content,
             json.dumps(tool_calls) if tool_calls else None, time.time()),
        )
        c.execute("UPDATE agent_conversations SET updated_at = ? WHERE id = ?",
                  (time.time(), conversation_id))
    return int(cur.lastrowid)


def get_conversation(conversation_id: str) -> dict[str, Any] | None:
    with _conn() as c:
        row = c.execute("SELECT * FROM agent_conversations WHERE id = ?",
                        (conversation_id,)).fetchone()
        if not row:
            return None
        turns = c.execute(
            """SELECT role, content, tool_calls_json, created_at
               FROM agent_turns WHERE conversation_id = ? ORDER BY id ASC""",
            (conversation_id,),
        ).fetchall()
    return {
        "id": row["id"], "agent_id": row["agent_id"],
        "title": row["title"], "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "turns": [{
            "role": t["role"], "content": t["content"],
            "tool_calls": json.loads(t["tool_calls_json"]) if t["tool_calls_json"] else [],
            "created_at": t["created_at"],
        } for t in turns],
    }


def list_conversations(agent_id: str, limit: int = 50) -> list[dict[str, Any]]:
    with _conn() as c:
        rows = c.execute(
            """SELECT c.id, c.title, c.updated_at, COUNT(t.id) AS n_turns
               FROM agent_conversations c
               LEFT JOIN agent_turns t ON t.conversation_id = c.id
               WHERE c.agent_id = ?
               GROUP BY c.id ORDER BY c.updated_at DESC LIMIT ?""",
            (agent_id, int(limit)),
        ).fetchall()
    return [{"id": r["id"], "title": r["title"],
             "updated_at": r["updated_at"], "n_turns": r["n_turns"]} for r in rows]
