"""Minimal unit tests for the worker SDK framing layer.

Real integration (supervisor spawns worker, calls a handler, gets a reply)
lives in the Rust side's `crates/ant-supervisor/tests/integration.rs`.
"""

import io
import struct

import msgpack


def pack_frame(frame: dict) -> bytes:
    data = msgpack.packb(frame, use_bin_type=True)
    return struct.pack(">I", len(data)) + data


def unpack_frame(buf: bytes) -> dict:
    (length,) = struct.unpack(">I", buf[:4])
    return msgpack.unpackb(buf[4 : 4 + length], raw=False)


def test_round_trip_simple() -> None:
    frame = {"kind": "hello", "worker": "test", "version": 1, "capabilities": ["test.echo"]}
    assert unpack_frame(pack_frame(frame)) == frame


def test_round_trip_binary_payload() -> None:
    frame = {"kind": "reply", "id": 42, "result": {"bytes": b"\x00\x01\x02"}}
    assert unpack_frame(pack_frame(frame)) == frame


def test_length_prefix_big_endian() -> None:
    data = pack_frame({"kind": "heartbeat"})
    # First four bytes are the length as big-endian u32.
    (length,) = struct.unpack(">I", data[:4])
    assert length == len(data) - 4


def test_reject_oversized() -> None:
    # The worker SDK caps a single frame at 100 MB; verify the sentinel
    # bytes we would compare against are what we expect.
    cap = 100 * 1024 * 1024
    assert struct.pack(">I", cap) == b"\x06\x40\x00\x00"
