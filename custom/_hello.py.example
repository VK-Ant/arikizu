"""Example user capability.

Copy this file, rename it, and change the handlers to add your own
logic. See custom/README.md for the full guide.
"""
from __future__ import annotations

import time

from arikizu_worker import Worker

worker = Worker.current()


@worker.handler("hello.greet")
def greet(name: str = "friend", language: str = "en") -> dict:
    """Say hello in a few languages. One of 'en', 'ta', 'hi', 'ja'."""
    greetings = {
        "en": f"Hello, {name}!",
        "ta": f"Vanakkam, {name}!",
        "hi": f"Namaste, {name}!",
        "ja": f"Konnichiwa, {name}-san!",
    }
    return {"greeting": greetings.get(language, greetings["en"]),
            "language": language}


@worker.handler("hello.timestamp")
def timestamp() -> dict:
    """Return the current server time."""
    return {"epoch": time.time(), "iso": time.strftime("%Y-%m-%dT%H:%M:%S%z")}


@worker.handler("hello.add")
def add(a: float = 0, b: float = 0) -> dict:
    """Add two numbers. A deliberately trivial example."""
    return {"sum": a + b, "a": a, "b": b}
