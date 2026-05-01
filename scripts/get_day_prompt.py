#!/usr/bin/env python3
"""
Extract the Claude Code prompt for a specific day from the plan.
Usage: python scripts/get_day_prompt.py <day_number>
"""

import re
import sys
from pathlib import Path


def extract_prompt(plan_file: str, day: int) -> str:
    """Extract just the Claude Code prompt for a specific day."""
    with open(plan_file, 'r') as f:
        content = f.read()

    # Pattern to find a day section
    day_pattern = rf"#### Day {day} —(.*?)(?=#### Day |\Z)"
    match = re.search(day_pattern, content, re.DOTALL)

    if not match:
        return None

    day_block = match.group(0)

    # Extract Claude Code prompt (just the content, no markdown fence)
    prompt_match = re.search(r"\*\*Claude Code prompt.*?\*\*:\s*```(.+?)```", day_block, re.DOTALL)
    if prompt_match:
        return prompt_match.group(1).strip()

    return None


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/get_day_prompt.py <day_number>")
        sys.exit(1)

    try:
        day_num = int(sys.argv[1])
    except ValueError:
        print(f"Error: {sys.argv[1]} is not a valid day number.")
        sys.exit(1)

    plan_path = Path(__file__).parent.parent / "agentic-qa-platform-plan.md"

    if not plan_path.exists():
        print(f"Error: Plan file not found at {plan_path}")
        sys.exit(1)

    prompt = extract_prompt(str(plan_path), day_num)
    if prompt:
        print(prompt)
    else:
        print(f"Error: Could not find prompt for Day {day_num}")
        sys.exit(1)
