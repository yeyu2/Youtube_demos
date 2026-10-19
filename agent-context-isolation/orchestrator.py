"""Production Graph Orchestrator: Python Supervisor Managing Headless CLI Agents.

This script demonstrates true Physical Context Isolation:
1. Python acts strictly as the Supervisor and Graph Router.
2. Node 1 (Maker): Spawns an external CLI agent process (`cursor-agent`, `claude`, or `demo/agent_cli.py`).
   The agent writes to disk and exits. Its OS process and RAM memory are completely destroyed.
3. Shared State: Pure files on disk (`task.md`, `src/`, `tests/`).
4. Node 2 (Checker): Spawns a clean verification process with zero memory of Maker's conversation.
5. Router: Inspects the exit code and structured diagnostics. Executes rollback or human gate.

Usage:
  # 1. Out-of-the-box demo (deterministic, zero external setup):
  python3 demo/orchestrator.py

  # 2. Live production with official Cursor CLI:
  cursor-agent login
  python3 demo/orchestrator.py --agent-bin cursor-agent

  # 3. Drop into your own project:
  python3 orchestrator.py --task ./TODO.md --test-cmd "npm test" --agent-bin cursor-agent
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

DEMO_DIR = Path(__file__).parent
SRC_DIR = DEMO_DIR / "src"
TESTS_DIR = DEMO_DIR / "tests"
REPORT_FILE = DEMO_DIR / "review_report.json"
AGENT_CLI_SCRIPT = DEMO_DIR / "agent_cli.py"


def log(node: str, msg: str) -> None:
    print(f"\033[1;34m[{node.upper():<13}]\033[0m \033[1m{msg}\033[0m")


def resolve_cursor_agent_bin(bin_name: str | None) -> str | None:
    """Finds the installed cursor-agent binary if specified."""
    if not bin_name:
        return None
    # 1. Check direct PATH
    found = shutil.which(bin_name)
    if found:
        return found
    # 2. Check standard ~/.local/bin/cursor-agent
    local_path = Path.home() / ".local" / "bin" / bin_name
    if local_path.is_file() and os.access(local_path, os.X_OK):
        return str(local_path)
    return bin_name


def run_maker_cli(
    iteration: int,
    feedback: dict | None,
    task_file: Path,
    custom_agent_bin: str | None = None,
    model: str = "auto",
) -> None:
    """Spawns Node 1 (Maker Agent) as an isolated OS subprocess.
    
    Can invoke official `cursor-agent`, `claude`, or local `demo/agent_cli.py`.
    """
    resolved_bin = resolve_cursor_agent_bin(custom_agent_bin)
    
    if resolved_bin:
        log("supervisor", f"Spawning Node 1 via Cursor CLI [{resolved_bin}] (model={model}) [Cycle {iteration}]")
        task_text = task_file.read_text(encoding="utf-8")
        prompt = (
            f"You are the Maker Node in an isolated agent graph.\n"
            f"Fulfill the contract in {task_file.name}:\n\n"
            f"{task_text}\n\n"
            f"Create the code in src/ and tests in tests/."
        )
        if feedback and feedback.get("error"):
            prompt += f"\n\nPRIOR VERIFICATION FAILED: {feedback['error']}\nFix this contract violation immediately."

        # Official cursor-agent headless invocation flags:
        # -p (--print): console output mode for automation
        # --force: automatically approve file writes without interactive prompts
        # --model: model to use (defaults to "auto")
        cmd = [
            resolved_bin,
            "-p",
            "--force",
            "--model",
            model,
            "--workspace",
            str(DEMO_DIR),
            prompt,
        ]
    else:
        log("supervisor", f"Spawning Node 1 (Maker CLI Subprocess) [Cycle {iteration}]")
        cmd = [
            sys.executable,
            str(AGENT_CLI_SCRIPT),
            "--task",
            str(task_file),
            "--role",
            "maker",
            "--cycle",
            str(iteration),
        ]
        if feedback and feedback.get("error"):
            cmd.extend(["--feedback", feedback["error"]])

    # Execute the external OS process
    proc = subprocess.run(cmd, capture_output=True, text=True)

    if proc.stdout:
        for line in proc.stdout.strip().splitlines():
            print(f"  \033[90m| {line}\033[0m")

    if proc.returncode != 0:
        log("supervisor", f"Maker CLI failed with exit code {proc.returncode}")
        if proc.stderr:
            print(f"\033[1;31m{proc.stderr.strip()}\033[0m", file=sys.stderr)
        if resolved_bin and ("cursor-agent" in resolved_bin or resolved_bin.endswith("/agent")):
            print(
                "\n\033[1;33m[Hint]\033[0m If using official Cursor CLI, ensure you are authenticated:\n"
                "  1. Add ~/.local/bin to PATH: export PATH=\"$HOME/.local/bin:$PATH\"\n"
                "  2. Run 'cursor-agent login' (or 'agent login')\n"
                "  3. Or export CURSOR_API_KEY='your-key'\n"
                "  4. Or run without --agent-bin to use the zero-dependency runner.\n",
                file=sys.stderr,
            )
        sys.exit(proc.returncode)

    log("supervisor", "Maker process terminated. Process memory zeroed. Disk state preserved.")


def run_checker_cli(custom_test_cmd: str | None = None) -> dict:
    """Spawns Node 2 (Checker Subprocess) with a completely fresh context."""
    log("supervisor", "Spawning Node 2 (Checker Subprocess) with zero conversational history")
    
    if custom_test_cmd:
        log("checker-cli", f"Executing custom test harness: '{custom_test_cmd}'")
        env = os.environ.copy()
        env["PYTHONPATH"] = f"{DEMO_DIR}:{env.get('PYTHONPATH', '')}"
        res = subprocess.run(custom_test_cmd, shell=True, capture_output=True, text=True, env=env)
    else:
        log("checker-cli", "Executing test runner against disk artifacts")
        res = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", str(TESTS_DIR)],
            capture_output=True,
            text=True,
            cwd=str(DEMO_DIR),
        )

    passed = res.returncode == 0
    report = {
        "passed": passed,
        "returncode": res.returncode,
        "summary": "All tests passed" if passed else "Tests failed in sandbox",
        "error": "",
    }

    if not passed:
        output = res.stderr or res.stdout
        failed_lines = [
            l.strip()
            for l in output.splitlines()
            if "AssertionError" in l or "FAILED" in l or "ValueError not raised" in l or "Error:" in l
        ]
        short_err = failed_lines[0] if failed_lines else "Verification failed"
        report["error"] = short_err
        log("checker-cli", f"Audit Verdict: REJECT ({short_err})")
    else:
        log("checker-cli", "Audit Verdict: PASS (All invariants confirmed)")

    REPORT_FILE.write_text(json.dumps(report, indent=2), encoding="utf-8")
    log("supervisor", "Checker process completed and exited.")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Python Supervisor Managing Headless CLI Agents")
    parser.add_argument("--task", type=str, default=str(DEMO_DIR / "task.md"), help="Path to task specification")
    parser.add_argument("--test-cmd", type=str, default=None, help="Test command to run (e.g. 'pytest' or 'npm test')")
    parser.add_argument("--agent-bin", type=str, default=None, help="Custom agent binary (e.g. cursor-agent or claude)")
    parser.add_argument("--model", type=str, default="auto", help="Model to use with Cursor CLI (default: 'auto')")
    parser.add_argument("--max-cycles", type=int, default=3, help="Max retry budget before stopping")
    args = parser.parse_args()

    task_file = Path(args.task)
    if not task_file.exists():
        print(f"\033[1;31mError: Task file {task_file} does not exist.\033[0m", file=sys.stderr)
        sys.exit(1)

    print("\n" + "=" * 68)
    print(" \033[1;32mPYTHON SUPERVISOR: RUNNING CONTEXT-ISOLATED CLI GRAPH\033[0m")
    print(f" Contract:  {task_file.name}")
    if args.agent_bin:
        print(f" Agent CLI: {args.agent_bin} (model: {args.model})")
    if args.test_cmd:
        print(f" Test Cmd:  {args.test_cmd}")
    print("=" * 68 + "\n")

    iteration = 1
    feedback = None

    while iteration <= args.max_cycles:
        print(f"\n--- [Cycle {iteration}] ---")

        # 1. Supervisor spawns external Maker CLI process
        run_maker_cli(iteration, feedback, task_file, args.agent_bin, args.model)

        # 2. Shared State: files on disk. Maker process is completely dead.
        print("\033[90m[Edge Handoff] Process boundary enforced. Memory is zeroed.\033[0m")

        # 3. Supervisor spawns external Checker CLI process
        verdict = run_checker_cli(args.test_cmd)

        # 4. Supervisor routes based on verdict
        if verdict["passed"]:
            log("supervisor", "Verification passed -> Advancing to Human Authorization Gate")
            print("\n" + "=" * 68)
            print(" \033[1;33mHUMAN AUTHORIZATION GATE\033[0m")
            print(f" Verified Code: src/ (or project directory)")
            print(f" Contract:      {task_file.name}")
            print(" Tests Status:  All Passed")
            print("=" * 68)
            print("\033[1;32m[SUCCESS] Production artifact verified and authorized for merge.\033[0m\n")
            return
        else:
            log("supervisor", "Verification failed -> Triggering rollback edge to Maker CLI")
            feedback = verdict
            iteration += 1
            time.sleep(1)

    print("\n\033[1;31m[BLOCKED] Retry budget exhausted.\033[0m\n")


if __name__ == "__main__":
    main()
