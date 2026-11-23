# Folding Subagents into Skills vs. Model-Routed Delegation

A migration and evaluation toolkit (`fold_check.py`) for auditing an existing multi-subagent setup (`agents/*.md`), folding connected domain subagents into on-demand Skills (`skills/shipping-sla/SKILL.md`), keeping high-noise leaf search (`fast`) and zero-memory independent checks (`deep`) behind `model_map.json`, and catching silent `PASS -> FAIL` task flips against `cases.json`.

## Folder Structure

Every file in this folder is used on screen in the episode:

- `agents/`: Four legacy subagent Markdown files (`order-refund-agent.md`, `shipping-agent.md`, `log-scanner-agent.md`, `security-reviewer-agent.md`) representing the pre-fold setup.
- `skills/shipping-sla/SKILL.md`: The on-demand Skill migrated from `agents/shipping-agent.md`, with an explicit trigger description and the three required carrier SLA rules.
- `model_map.json`: Named delegation routes (`fast` -> `gemini-4-hydrogen` with `read_only: true`, `deep` -> `claude-opus-5.5` with `read_only: true` and `zero_memory: true`) for the two subagents worth keeping.
- `cases.json`: Five test cases (`T1` through `T5`) storing expected skill triggers, delegation routes, required rules, and pre-fold `baseline_passed` states.
- `fold_check.py`: Zero-dependency CLI tool (`audit`, `check`, `route`) with configurable `--agents-dir`, `--skills-dir`, `--model-map`, and `--cases` flags so you can run it on your own repo.

## Run on this example

```bash
cd fold-subagents-into-skills
python3 fold_check.py audit
python3 fold_check.py check
python3 fold_check.py route
```

## Run on your own project

Point `fold_check.py` at your own subagent folder (`.claude/agents`) and Skills folder (`.cursor/skills` or `.claude/skills`):

```bash
python3 fold_check.py audit --agents-dir .claude/agents
python3 fold_check.py check --skills-dir .cursor/skills --model-map model_map.json --cases cases.json
```
