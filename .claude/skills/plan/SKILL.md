---
name: plan
description: Display the goal, tasks, and Claude Code prompt for a specific day in the agentic QA platform project plan
---

# Plan Skill

Shows the day's goal, task breakdown, and implementation prompt from the 28-day project plan.

## Usage

```
/plan <day_number>
```

Where `<day_number>` is a number from 1 to 28.

## Examples

- `/plan 1` — Show Day 1 (Environment & Repo Setup)
- `/plan 5` — Show Day 5 (Test Runner)
- `/plan 15` — Show Day 15 (Failure Classifier)

## What You'll See

For each day:
- **Goal** — The outcome for that day
- **Tasks** — Checkbox list of what to build
- **Claude Code Prompt** — The exact prompt to use in your next Claude Code session

```sh
python .claude/skills-lib/parse_plan.py $1
```
