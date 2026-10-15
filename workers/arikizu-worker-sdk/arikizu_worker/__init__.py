"""Arikizu worker SDK.

Thin IPC shim that each worker imports to connect back to the Rust
supervisor over a Unix socket, register handlers for capabilities,
and emit events.

Also exposes `arikizu_worker.backend` for model loading with runtime
auto-selection (ONNX / TFLite / OpenVINO / TensorRT / CoreML / PyTorch).
"""

from __future__ import annotations

import asyncio
import logging
import os
import struct
import sys
from collections.abc import Awaitable, Callable
from typing import Any

import msgpack

from . import backend as backend  # re-exported module

PROTOCOL_VERSION = 1

logger = logging.getLogger("arikizu_worker")


class Worker:
    """A single worker instance.

    Example:
        from arikizu_worker import Worker

        worker = Worker("test")

        @worker.handler("test.echo")
        def echo(message: str) -> str:
            return message

        asyncio.run(worker.run())
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self.handlers: dict[str, Callable[..., Any]] = {}
        self.socket_path = os.environ.get("ARIKIZU_SOCKET")
        if not self.socket_path:
            raise RuntimeError(
                "ARIKIZU_SOCKET env var not set; "
                "this worker must be spawned by the Arikizu supervisor"
            )

    def handler(self, capability: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator to register a handler for a capability."""
        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            self.handlers[capability] = fn
            logger.info("registered handler for %s", capability)
            return fn
        return decorator

    async def run(self) -> None:
        """Connect to the supervisor and serve capability calls indefinitely."""
        reader, writer = await asyncio.open_unix_connection(self.socket_path)
        logger.info("connected to supervisor via %s", self.socket_path)

        # Send Hello
        await self._write_frame(writer, {
            "kind": "hello",
            "worker": self.name,
            "version": PROTOCOL_VERSION,
            "capabilities": list(self.handlers.keys()),
        })

        # Start a background heartbeat task
        asyncio.create_task(self._heartbeat_loop(writer))

        # Main loop: read frames, dispatch calls
        try:
            while True:
                frame = await self._read_frame(reader)
                await self._handle_frame(frame, writer)
        except (asyncio.IncompleteReadError, ConnectionResetError):
            logger.info("supervisor disconnected")
        finally:
            writer.close()
            await writer.wait_closed()

    async def _handle_frame(
        self, frame: dict[str, Any], writer: asyncio.StreamWriter
    ) -> None:
        kind = frame.get("kind")
        if kind == "call":
            await self._handle_call(frame, writer)
        elif kind == "heartbeat":
            pass  # supervisor-initiated, ignore
        else:
            logger.warning("unknown frame kind: %s", kind)

    async def _handle_call(
        self, frame: dict[str, Any], writer: asyncio.StreamWriter
    ) -> None:
        call_id = frame["id"]
        capability = frame["capability"]
        payload = frame.get("payload", {})

        handler = self.handlers.get(capability)
        if handler is None:
            await self._write_frame(writer, {
                "kind": "error",
                "id": call_id,
                "error": f"no handler registered for `{capability}`",
            })
            return

        try:
            if asyncio.iscoroutinefunction(handler):
                if isinstance(payload, dict):
                    result = await handler(**payload)
                else:
                    result = await handler(payload)
            else:
                if isinstance(payload, dict):
                    result = handler(**payload)
                else:
                    result = handler(payload)

            await self._write_frame(writer, {
                "kind": "reply",
                "id": call_id,
                "result": result,
            })
        except Exception as exc:
            logger.exception("handler for %s raised", capability)
            await self._write_frame(writer, {
                "kind": "error",
                "id": call_id,
                "error": f"{type(exc).__name__}: {exc}",
            })

    async def _heartbeat_loop(self, writer: asyncio.StreamWriter) -> None:
        while True:
            try:
                await asyncio.sleep(1.0)
                await self._write_frame(writer, {
                    "kind": "heartbeat",
                    "memory_rss_mb": self._memory_rss_mb(),
                    "queue_depth": 0,
                    "in_flight": 0,
                    "resident_models": [],
                })
            except (ConnectionResetError, BrokenPipeError):
                return

    def _memory_rss_mb(self) -> int:
        try:
            import resource
            # ru_maxrss is in KB on Linux, bytes on macOS
            rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            if sys.platform == "darwin":
                return rss // (1024 * 1024)
            return rss // 1024
        except ImportError:
            return 0

    async def _write_frame(
        self, writer: asyncio.StreamWriter, frame: dict[str, Any]
    ) -> None:
        data = msgpack.packb(frame, use_bin_type=True)
        writer.write(struct.pack(">I", len(data)))
        writer.write(data)
        await writer.drain()

    async def _read_frame(self, reader: asyncio.StreamReader) -> dict[str, Any]:
        length_bytes = await reader.readexactly(4)
        (length,) = struct.unpack(">I", length_bytes)
        if length > 100 * 1024 * 1024:
            raise ValueError(f"frame too large: {length}")
        data = await reader.readexactly(length)
        return msgpack.unpackb(data, raw=False)

    async def emit_event(
        self,
        subject: str,
        payload: dict[str, Any],
        writer: asyncio.StreamWriter | None = None,
    ) -> None:
        """Publish an event to the supervisor's event bus."""
        if writer is None:
            # In practice, workers would hold a reference to writer; omitted here
            raise NotImplementedError(
                "emit_event requires passing the writer; "
                "see test_worker/__main__.py for the pattern"
            )
        await self._write_frame(writer, {
            "kind": "event",
            "subject": subject,
            "payload": payload,
        })


__all__ = ["Worker", "PROTOCOL_VERSION"]
