---
name: status
description: Show overall project progress - completed days, weekly breakdown, and next day to implement
---

# Status

Display your overall progress through the 28-day agentic QA platform project.

## Usage

```
/status
```

No arguments needed. Shows:
- Days completed so far
- Overall progress bar (0-28 days)
- Weekly breakdown (Weeks 1-4)
- Next day to implement with quick commands

## Example Output

```
╔════════════════════════════════════════════════════════════════╗
║                    PROJECT STATUS
╚════════════════════════════════════════════════════════════════╝

📊 PROGRESS
Days completed: 5 / 28
Progress: [█████░░░░░] 18%

✅ COMPLETED DAYS
1, 2, 3, 4, 5

📅 WEEKLY BREAKDOWN
Week 1 (Days 1-7):    5/7 ██░░░░░
Week 2 (Days 8-14):   0/7 ░░░░░░░
Week 3 (Days 15-21):  0/7 ░░░░░░░
Week 4 (Days 22-28):  0/7 ░░░░░░░

🚀 NEXT STEP
Run: /plan 6
Then: /implement 6
```

## How It Works

Reads completed days from your CLAUDE.md "Built So Far" section (populated by `/update-status`) and calculates:
- Total days done
- Overall progress percentage
- Per-week breakdown
- Next unfinished day

Run this at the start of each session to see where you left off!

## Command

```sh
python .claude/skills-lib/get_status.py
```
