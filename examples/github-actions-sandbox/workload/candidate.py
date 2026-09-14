"""Deterministic stand-in for agent-generated code; replace with your agent's output.

Task: remove duplicate values while preserving their first-occurrence order.
"""


def unique_in_order(values):
    return list(dict.fromkeys(values))
