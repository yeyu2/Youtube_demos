#!/usr/bin/env python3
"""
fold-subagents-into-skills/fold_check.py

Audit existing subagents, check folded on-demand Skills + model_map routes
against a baseline test suite, and preview how each prompt routes.

Commands:
  python3 fold_check.py audit [--agents-dir agents]
  python3 fold_check.py check [--skills-dir skills] [--model-map model_map.json] [--cases cases.json]
  python3 fold_check.py route [--skills-dir skills] [--model-map model_map.json] [--cases cases.json]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

ROOT = Path(__file__).resolve().parent

STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "before", "after",
    "into", "when", "your", "my", "has", "have", "are", "was", "were", "run",
    "handle", "check", "verify",
}


def split_keywords(text: str) -> Set[str]:
    words = re.findall(r"[a-z0-9_]+", text.lower())
    return {w for w in words if len(w) > 2 and w not in STOPWORDS}


def parse_markdown_header(md_path: Path, base: Path) -> Dict[str, str]:
    raw = md_path.read_text(encoding="utf-8")
    if not raw.startswith("---\n"):
        raise ValueError(f"{md_path}: missing YAML header")
    parts = raw.split("---\n", 2)
    if len(parts) < 3:
        raise ValueError(f"{md_path}: unclosed YAML header")
    header, body = parts[1], parts[2]
    meta: Dict[str, str] = {}
    for line in header.strip().splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    meta["body"] = body.strip()
    try:
        meta["path"] = str(md_path.relative_to(base))
    except ValueError:
        meta["path"] = str(md_path)
    return meta


def load_skills(skills_dir: Path) -> Dict[str, Dict[str, str]]:
    catalog: Dict[str, Dict[str, str]] = {}
    for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
        skill = parse_markdown_header(skill_md, skills_dir.parent)
        catalog[skill["name"]] = skill
    return catalog


def match_skills(prompt: str, catalog: Dict[str, Dict[str, str]]) -> List[str]:
    prompt_words = split_keywords(prompt)
    matched: List[str] = []
    for name, skill in catalog.items():
        desc_words = split_keywords(skill.get("description", ""))
        if len(prompt_words & desc_words) >= 2:
            matched.append(name)
    return matched


def select_delegate_route(prompt: str, routes: Dict[str, dict]) -> Optional[str]:
    prompt_words = split_keywords(prompt)
    best_route: Optional[str] = None
    best_score = 0
    for route_name, cfg in routes.items():
        desc_words = split_keywords(cfg.get("description", ""))
        score = len(prompt_words & desc_words)
        if score >= 2 and score > best_score:
            best_score = score
            best_route = route_name
    return best_route


def verify_model_map(model_map: dict) -> List[str]:
    failures: List[str] = []
    routes = model_map.get("routes", {})
    for route_name, cfg in routes.items():
        if not cfg.get("read_only", False):
            failures.append(f"model_map.json: route '{route_name}' must set read_only=true")
    if "deep" in routes and not routes["deep"].get("zero_memory", False):
        failures.append("model_map.json: route 'deep' must set zero_memory=true for independent checks")
    return failures


def evaluate_cases(
    cases: List[dict], catalog: Dict[str, Dict[str, str]], model_map: dict
) -> Tuple[List[str], Dict[str, List[str]]]:
    failures: List[str] = []
    flips: Dict[str, List[str]] = {"FAIL_TO_PASS": [], "PASS_TO_FAIL": [], "PASS_TO_PASS": []}
    routes = model_map.get("routes", {})

    for case in cases:
        cid = case["case_id"]
        prompt = case["prompt"]
        expect_skill = case.get("expect_skill")
        expect_delegate = case.get("expect_delegate")
        required_rules = case.get("required_rules", [])
        baseline_passed = bool(case["baseline_passed"])

        matched_skills = match_skills(prompt, catalog)
        chosen_route = select_delegate_route(prompt, routes)

        case_ok = True
        reasons: List[str] = []

        if expect_skill:
            if expect_skill not in matched_skills:
                case_ok = False
                reasons.append(f"trigger miss for skill '{expect_skill}'")
                failures.append(
                    f"trigger miss: {cid} did not match skills/{expect_skill}/SKILL.md description"
                )
            else:
                body = catalog[expect_skill]["body"]
                for rule in required_rules:
                    if rule not in body:
                        case_ok = False
                        reasons.append(f"missing required rule: {rule}")
                        failures.append(
                            f"missing rule: {catalog[expect_skill]['path']} is missing '{rule}' (needed by {cid})"
                        )
        else:
            if matched_skills:
                case_ok = False
                reasons.append(f"triggered by mistake: {matched_skills}")
                failures.append(
                    f"false trigger: {cid} unexpectedly loaded {', '.join(matched_skills)}"
                )

        if expect_delegate != chosen_route:
            case_ok = False
            reasons.append(f"expected delegate={expect_delegate}, got {chosen_route}")
            failures.append(
                f"route mismatch: {cid} expected '{expect_delegate}', got '{chosen_route}'"
            )

        if not baseline_passed and case_ok:
            flips["FAIL_TO_PASS"].append(cid)
        elif baseline_passed and not case_ok:
            reason_str = "; ".join(reasons)
            flips["PASS_TO_FAIL"].append(f"{cid} ({reason_str})")
            failures.append(f"task flip (PASS -> FAIL): {cid} ({reason_str})")
        elif baseline_passed and case_ok:
            flips["PASS_TO_PASS"].append(cid)

    return failures, flips


def cmd_audit(agents_dir: Path) -> int:
    agent_files = sorted(agents_dir.glob("*.md"))
    if not agent_files:
        print(f"No subagent files found in {agents_dir}")
        return 1

    for md_path in agent_files:
        meta = parse_markdown_header(md_path, agents_dir.parent)
        name = meta.get("name", md_path.stem)
        shares = meta.get("shares_state_with", "").strip("[] ")
        writes = meta.get("writes_state", "false").lower() == "true"
        high_noise = meta.get("high_noise_leaf", "false").lower() == "true"
        indep_check = meta.get("independent_check", "false").lower() == "true"

        if indep_check and not writes:
            verdict = "KEEP -> model_map 'deep'  (read_only=true, zero_memory=true)"
        elif high_noise and not writes:
            verdict = "KEEP -> model_map 'fast'  (read_only=true, leaf summary)"
        elif writes or shares:
            verdict = "FOLD -> main loop + SKILL.md  (shares turn state / writes)"
        else:
            verdict = "FOLD -> main loop"

        print(f"  {name:<26} {verdict}")
    return 0


def cmd_check(skills_dir: Path, model_map_path: Path, cases_path: Path) -> int:
    catalog = load_skills(skills_dir)
    model_map = json.loads(model_map_path.read_text(encoding="utf-8"))
    cases = json.loads(cases_path.read_text(encoding="utf-8"))

    failures: List[str] = []
    failures.extend(verify_model_map(model_map))
    case_failures, flips = evaluate_cases(cases, catalog, model_map)
    failures.extend(case_failures)

    for f in failures:
        print(f"  FAIL  {f}")

    print(
        f"  {len(catalog)} skill(s) checked, "
        f"{len(model_map.get('routes', {}))} model_map route(s), "
        f"{len(flips['FAIL_TO_PASS'])} FAIL->PASS, "
        f"{len(flips['PASS_TO_FAIL'])} PASS->FAIL"
    )
    if failures:
        print("REJECT")
        return 1
    print("PASS")
    return 0


def cmd_route(skills_dir: Path, model_map_path: Path, cases_path: Path) -> int:
    catalog = load_skills(skills_dir)
    model_map = json.loads(model_map_path.read_text(encoding="utf-8"))
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    routes = model_map.get("routes", {})
    main_model = model_map.get("default_loop_model", "main-model")

    for case in cases:
        cid = case["case_id"]
        matched = match_skills(case["prompt"], catalog)
        delegate = select_delegate_route(case["prompt"], routes)
        steps = [f"main_loop({main_model})"]
        for s in matched:
            steps.append(f"load_skill(skills/{s}/SKILL.md)")
        if delegate:
            target = routes[delegate]
            steps.append(
                f"delegate(option='{delegate}' -> {target['model']}, "
                f"read_only={target['read_only']}, zero_memory={target['zero_memory']})"
            )
        print(f"  {cid:<24} {' -> '.join(steps)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit subagents and check folded Skills + model_map routes.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_audit = sub.add_parser("audit", help="Audit subagent Markdown files and recommend FOLD vs KEEP.")
    p_audit.add_argument("--agents-dir", type=Path, default=ROOT / "agents")

    for cmd_name in ("check", "route"):
        p = sub.add_parser(cmd_name)
        p.add_argument("--skills-dir", type=Path, default=ROOT / "skills")
        p.add_argument("--model-map", type=Path, default=ROOT / "model_map.json")
        p.add_argument("--cases", type=Path, default=ROOT / "cases.json")

    args = parser.parse_args()
    if args.command == "audit":
        return cmd_audit(args.agents_dir)
    if args.command == "check":
        return cmd_check(args.skills_dir, args.model_map, args.cases)
    return cmd_route(args.skills_dir, args.model_map, args.cases)


if __name__ == "__main__":
    sys.exit(main())
