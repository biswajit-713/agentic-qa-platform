#!/usr/bin/env python3
"""
Parse daily plans from agentic-qa-platform-plan.md.
Usage: python .claude/skills-lib/parse_plan.py <day_number>
"""

import re
import sys
from pathlib import Path


def extract_day_content(plan_file: str, day: int) -> dict:
    """Extract a specific day's content from the plan."""
    with open(plan_file, 'r') as f:
        content = f.read()

    # Pattern to find a day section (e.g., "#### Day 1 — Environment & Repo Setup")
    day_pattern = rf"#### Day {day} —(.*?)(?=#### Day |\Z)"
    match = re.search(day_pattern, content, re.DOTALL)

    if not match:
        return None

    day_block = match.group(0)

    # Extract title
    title_match = re.search(r"#### Day \d+ —(.+?)$", day_block, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else f"Day {day}"

    # Extract outcome
    outcome_match = re.search(r"\*\*Outcome\*\*:\s*(.+?)(?=\n\n|\n\*\*)", day_block, re.DOTALL)
    if outcome_match:
        outcome = outcome_match.group(1).strip()
    else:
        outcome = "No outcome specified"

    # Extract tasks section
    tasks_match = re.search(r"\*\*Tasks\*\*:(.+?)(?=\*\*Claude Code|$)", day_block, re.DOTALL)
    tasks = tasks_match.group(1).strip() if tasks_match else "No tasks specified"

    # Extract Claude Code prompt
    prompt_match = re.search(r"\*\*Claude Code prompt.*?\*\*:\s*```(.+?)```", day_block, re.DOTALL)
    prompt = prompt_match.group(1).strip() if prompt_match else "No prompt specified"

    return {
        "day": day,
        "title": title,
        "outcome": outcome,
        "tasks": tasks,
        "claude_prompt": prompt,
    }


def format_day_plan(day_content: dict) -> str:
    """Format day content for display."""
    if not day_content:
        return f"Day {sys.argv[1]} not found in the plan."

    output = f"""
╔════════════════════════════════════════════════════════════════╗
║ Day {day_content['day']} — {day_content['title']}
╚════════════════════════════════════════════════════════════════╝

📌 GOAL
{day_content['outcome']}

✅ TASKS
{day_content['tasks']}

💻 CLAUDE CODE PROMPT
```
{day_content['claude_prompt']}
```
"""
    return output


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python .claude/skills-lib/parse_plan.py <day_number>")
        sys.exit(1)

    try:
        day_num = int(sys.argv[1])
    except ValueError:
        print(f"Error: {sys.argv[1]} is not a valid day number.")
        sys.exit(1)

    plan_path = Path(__file__).parent.parent.parent / "agentic-qa-platform-plan.md"

    if not plan_path.exists():
        print(f"Error: Plan file not found at {plan_path}")
        sys.exit(1)

    day_content = extract_day_content(str(plan_path), day_num)
    print(format_day_plan(day_content))
