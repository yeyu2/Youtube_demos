"""
Context Engineering Demo

A demonstration of context engineering patterns from Google's blog:
"Architecting efficient context-aware multi-agent framework for production"

Patterns demonstrated:
1. Handle Pattern - Store references, load content on-demand
2. State for Data Flow - Tools communicate via context.state
3. State Prefixes - temp:, user:, app: for different scopes
4. Artifacts - Large content stored externally, not in prompt

Usage:
    cd context_demo
    export GOOGLE_API_KEY="your-key"
    adk web

Then open http://localhost:8080 and select ContextDemoAgent.
"""

from .agent import root_agent

__all__ = ["root_agent"]
