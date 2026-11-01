"""Arikizu custom agent worker.

Users define agents with: a name, a system prompt, a list of allowed
capabilities, and a per-capability policy (ask / auto / deny). The worker
runs a chat loop that routes user turns through reasoning + capability
calls, enforces policy, and records every tool call to the audit log.
"""
__version__ = "0.1.0"
