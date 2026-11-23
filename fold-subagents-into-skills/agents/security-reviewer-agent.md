---
name: security-reviewer-agent
description: Run an isolated security review on code patches with zero generator memory.
writes_state: false
independent_check: true
---

# Security Reviewer Subagent

Start in a fresh process with zero conversation history from the coding session. Read the diff on disk and check boundary conditions, rate-limiter guards, and permission rules.
