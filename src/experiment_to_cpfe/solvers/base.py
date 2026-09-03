"""Shared solver status vocabulary."""

from enum import Enum


class SolverStatus(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
