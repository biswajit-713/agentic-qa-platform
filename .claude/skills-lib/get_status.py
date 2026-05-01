#!/usr/bin/env python3
"""
Fetch which days are completed and what is the next day to implement.
Usage: python .claude/skills-lib/get_status.py
"""

import re
from pathlib import Path
from typing import List, Tuple


def extract_completed_days(claude_md_path: str) -> Tuple[List[int], int]:
    """
    Extract completed day numbers from CLAUDE.md and return list of done days
    and the next day to implement.
    """
    with open(claude_md_path, 'r') as f:
        content = f.read()

    # Find the "Built So Far" section
    pattern = r"## Built So Far\n(.*?)(?=\n##|\Z)"
    match = re.search(pattern, content, re.MULTILINE | re.DOTALL)

    completed_days = []

    if match:
        built_so_far = match.group(1)

        # Extract all day numbers from entries like "Day X:"
        day_pattern = r"Day (\d+):"
        days = re.findall(day_pattern, built_so_far)

        # Convert to integers and sort
        completed_days = sorted(set(int(d) for d in days if d))

    # Calculate next day
    if completed_days:
        next_day = max(completed_days) + 1
    else:
        next_day = 1

    # Cap at 28 (project ends at day 28)
    if next_day > 28:
        next_day = 28

    return completed_days, next_day


def format_status(completed_days: List[int], next_day: int) -> str:
    """Format the status for display."""
    if not completed_days:
        return f"""
╔════════════════════════════════════════════════════════════════╗
║                    PROJECT STATUS
╚════════════════════════════════════════════════════════════════╝

📊 PROGRESS
Days completed: 0 / 28

🚀 NEXT STEP
Run: /plan {next_day}
Then: /implement {next_day}

"""

    # Calculate progress
    progress_pct = (len(completed_days) / 28) * 100
    filled = len(completed_days) // 3  # ~3 days per filled block (28/10 = 2.8)
    filled = min(filled, 10)
    bar = "█" * filled + "░" * (10 - filled)

    # Format completed days
    completed_str = ", ".join(str(d) for d in completed_days)

    # Weeks breakdown
    week1_done = len([d for d in completed_days if 1 <= d <= 7])
    week2_done = len([d for d in completed_days if 8 <= d <= 14])
    week3_done = len([d for d in completed_days if 15 <= d <= 21])
    week4_done = len([d for d in completed_days if 22 <= d <= 28])

    # Create progress bars for weeks
    def week_bar(done, total=7):
        filled = (done * 7) // total
        return "█" * filled + "░" * (7 - filled)

    output = f"""
╔════════════════════════════════════════════════════════════════╗
║                    PROJECT STATUS
╚════════════════════════════════════════════════════════════════╝

📊 PROGRESS
Days completed: {len(completed_days)} / 28
Progress: [{bar}] {progress_pct:.0f}%

✅ COMPLETED DAYS
{completed_str}

📅 WEEKLY BREAKDOWN
Week 1 (Days 1-7):    {week1_done}/7 {week_bar(week1_done)}
Week 2 (Days 8-14):   {week2_done}/7 {week_bar(week2_done)}
Week 3 (Days 15-21):  {week3_done}/7 {week_bar(week3_done)}
Week 4 (Days 22-28):  {week4_done}/7 {week_bar(week4_done)}

🚀 NEXT STEP
Run: /plan {next_day}
Then: /implement {next_day}
"""

    return output


if __name__ == "__main__":
    claude_md_path = Path(__file__).parent.parent.parent / "CLAUDE.md"

    if not claude_md_path.exists():
        print(f"Error: CLAUDE.md not found at {claude_md_path}")
        exit(1)

    completed_days, next_day = extract_completed_days(str(claude_md_path))
    print(format_status(completed_days, next_day))
