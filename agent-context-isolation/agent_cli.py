#!/usr/bin/env python3
"""Autonomous CLI Agent Worker.

This script represents an independent, headless coding agent process
(comparable to `cursor-agent`, `claude`, or `aider`).

Lifecycle:
1. Launched as a standalone OS subprocess by the supervisor.
2. Reads the contract (`task.md`) and any failure feedback from arguments.
3. Synthesizes the required code and writes it directly to disk (`src/rate_limiter.py`).
4. Terminates immediately, zeroing its internal context window from memory.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

DEMO_DIR = Path(__file__).parent
SRC_DIR = DEMO_DIR / "src"
TESTS_DIR = DEMO_DIR / "tests"


def synthesize_code(cycle: int, feedback: str | None) -> tuple[str, str]:
    """Generates the implementation and test harness.
    
    If an LLM API key (e.g. OPENAI_API_KEY) is present, this can call an LLM API.
    By default, it outputs deterministic cycle code to ensure video predictability:
    - Cycle 1: Misses negative capacity boundary check.
    - Cycle 2+: Implements boundary guards based on supervisor feedback.
    """
    if cycle == 1:
        # Cycle 1 candidate: works for happy path, forgets negative capacity guard
        code = '''import time
from collections import defaultdict

class SlidingWindowRateLimiter:
    def __init__(self, capacity: int, window_seconds: float):
        self.capacity = capacity
        self.window_seconds = window_seconds
        self.buckets = defaultdict(list)

    def allow_request(self, tenant_id: str) -> bool:
        now = time.time()
        boundary = now - self.window_seconds
        history = self.buckets[tenant_id]
        while history and history[0] <= boundary:
            history.pop(0)
        if len(history) < self.capacity:
            history.append(now)
            return True
        return False
'''
    else:
        # Cycle 2 patch: strict validation guards enforcing task.md invariants
        code = '''import time
from collections import defaultdict

class SlidingWindowRateLimiter:
    def __init__(self, capacity: int, window_seconds: float):
        if not isinstance(capacity, int) or capacity <= 0:
            raise ValueError("capacity must be a positive integer")
        if not isinstance(window_seconds, (int, float)) or window_seconds <= 0:
            raise ValueError("window_seconds must be a positive number")
        self.capacity = capacity
        self.window_seconds = float(window_seconds)
        self.buckets = defaultdict(list)

    def allow_request(self, tenant_id: str) -> bool:
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise TypeError("tenant_id must be a non-empty string")
        now = time.time()
        boundary = now - self.window_seconds
        history = self.buckets[tenant_id]
        while history and history[0] <= boundary:
            history.pop(0)
        if len(history) < self.capacity:
            history.append(now)
            return True
        return False
'''

    tests = '''import unittest
from src.rate_limiter import SlidingWindowRateLimiter

class TestRateLimiter(unittest.TestCase):
    def test_tenant_isolation(self):
        limiter = SlidingWindowRateLimiter(capacity=1, window_seconds=60)
        self.assertTrue(limiter.allow_request("tenant-a"))
        self.assertFalse(limiter.allow_request("tenant-a"))
        self.assertTrue(limiter.allow_request("tenant-b"))

    def test_invalid_capacity(self):
        with self.assertRaises(ValueError):
            SlidingWindowRateLimiter(capacity=-5, window_seconds=10)
'''
    return code, tests


def main() -> None:
    parser = argparse.ArgumentParser(description="Headless CLI Agent Worker")
    parser.add_argument("--task", type=str, required=True, help="Path to contract specification")
    parser.add_argument("--role", type=str, default="maker", choices=["maker", "checker"])
    parser.add_argument("--cycle", type=int, default=1, help="Current loop iteration")
    parser.add_argument("--feedback", type=str, default=None, help="Verifier failure diagnostics")
    args = parser.parse_args()

    pid = os.getpid()
    task_path = Path(args.task)
    if not task_path.exists():
        print(f"[AGENT PID {pid}] Error: Contract {args.task} not found", file=sys.stderr)
        sys.exit(1)

    print(f"\033[1;36m[AGENT CLI PID {pid}]\033[0m Initialized fresh session. Reading {task_path.name}...")
    if args.feedback:
        print(f"\033[1;36m[AGENT CLI PID {pid}]\033[0m Consuming feedback payload: {args.feedback}")

    SRC_DIR.mkdir(exist_ok=True)
    TESTS_DIR.mkdir(exist_ok=True)

    code, tests = synthesize_code(args.cycle, args.feedback)

    target_code = SRC_DIR / "rate_limiter.py"
    target_tests = TESTS_DIR / "test_rate_limiter.py"

    target_code.write_text(code, encoding="utf-8")
    target_tests.write_text(tests, encoding="utf-8")

    print(f"\033[1;36m[AGENT CLI PID {pid}]\033[0m Wrote {target_code.name} and {target_tests.name} to disk.")
    print(f"\033[1;36m[AGENT CLI PID {pid}]\033[0m Task completed. Exiting process.")
    sys.exit(0)


if __name__ == "__main__":
    main()
