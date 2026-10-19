# Stop Letting Your AI Coding Agent Review Its Own Code

**Video Tutorial:** [https://youtu.be/J16AHEKO66Q](https://youtu.be/J16AHEKO66Q)

An empirical, production-grade reference architecture for AI coding agents.

Demonstrates how to eliminate agent self-review blind spots through **Physical Context Isolation**, **Disk-based Shared State**, and **Explicit Rollback Routing**.

---

## The Core Problem

When an autonomous agent writes code, runs tests, and reviews its own output in a single continuous conversation, it evaluates its work using its own internal reasoning history. The model becomes the defense attorney for its own output, frequently excusing boundary bugs and contract violations.

---

## The Architectural Solution

This repository implements the **Context-Isolated Graph Pattern**:

```text
[task.md] (Immutable Boundary Contract)
    │
    ▼
[Node 1: Maker CLI Subprocess] ── (Independent process: demo/agent_cli.py or cursor-agent)
    │
    ▼
[Edge: Process Destruction] ── (OS terminates Maker process. Memory zeroed. State written to disk)
    │
    ▼
[Node 2: Checker Subprocess] ── (Fresh subprocess with ZERO memory of Maker thoughts)
    │
    ├── FAIL ──► [Rollback Edge] ──► Returns structured error payload to Maker (Iteration 2)
    └── PASS ──► [Human Authorization Gate] ──► Production Merge
```

---

## Project Structure

- `demo/task.md`: The immutable task specification defining strict boundary invariants.
- `demo/agent_cli.py`: Standalone CLI agent worker that can be executed independently.
- `demo/orchestrator.py`: The Python supervisor managing subprocess lifecycles, state handoffs, and rollback routing.
- `demo/src/rate_limiter.py`: Application module produced on disk.
- `demo/tests/test_rate_limiter.py`: Contract verification test harness.
- `demo/review_report.json`: Structured diagnostics passing along the rollback edge.

---

## Connecting the Official Cursor CLI

If you want the supervisor to drive the official Cursor Agent:

1. Install Cursor CLI and add `~/.local/bin` to your `PATH`:
   ```bash
   curl -sS https://cursor.com/install | bash
   echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
   source ~/.zshrc
   ```

2. Authenticate:
   ```bash
   cursor-agent login
   # Or set: export CURSOR_API_KEY="your-key"
   ```

3. Run the supervisor with the agent binary flag:
   ```bash
   python3 demo/orchestrator.py --agent-bin cursor-agent --model auto
   ```

The supervisor calls `cursor-agent -p --force --model auto --workspace . "..."` headlessly, terminating the agent process between review cycles to enforce physical context boundaries.

---

## Drop-in Usage in Your Own Project

You can copy `demo/orchestrator.py` into the root of any existing project and run it with your own contract and test suite:

```bash
# Example for a Node / TypeScript project:
python3 orchestrator.py --task ./TODO.md --test-cmd "npm test" --agent-bin "cursor-agent"

# Example for a Python project:
python3 orchestrator.py --task ./task.md --test-cmd "pytest tests/"

# Example for Go / Rust:
python3 orchestrator.py --task ./SPEC.md --test-cmd "cargo test"
```

The supervisor will enforce process-level context isolation:
1. Spawns your agent in an isolated process to write code based on your spec.
2. Destroys the process and wipes memory.
3. Spawns your test command in a clean subprocess.
4. Automatically triggers rollback with error diagnostics if tests fail, or pauses at the Human Gate if they pass.

---

## How to Run the Demo

1. Run the supervisor (zero external dependencies required):
   ```bash
   python3 demo/orchestrator.py
   ```

2. Optional: Connect directly to an external agent binary (e.g. `cursor-agent`):
   ```bash
   python3 demo/orchestrator.py --agent-bin cursor-agent
   ```

3. Or run the agent CLI directly as a standalone tool:
   ```bash
   python3 demo/agent_cli.py --task demo/task.md --role maker --cycle 1
   ```

Observe the live handoff in `orchestrator.py`:
- **Cycle 1:** Supervisor spawns Maker CLI (`PID xxxxx`). Maker writes files to disk and exits. Chat memory is zeroed. Checker runs in an isolated process and catches a missing negative capacity check. Router triggers rollback.
- **Cycle 2:** Supervisor spawns Maker CLI fresh (`PID yyyyy`) with error feedback. Maker applies validation guards and exits. Checker passes in a fresh context. Router advances to human sign-off.
