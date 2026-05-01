---
name: implement
description: Execute the implementation plan for a specific day from the 28-day project roadmap
---

# Implement Day

This skill extracts and executes the Claude Code prompt for a specific day's implementation task.

## Usage

```
/implement <day_number>
```

## How It Works

1. You read the plan: `/plan 5`
2. You invoke: `/implement 5`
3. The script extracts Day 5's Claude Code prompt from the plan
4. Claude automatically starts implementing that day's task

## Examples

```
/implement 1     # Implement Day 1 — Environment & Repo Setup
/implement 10    # Implement Day 10 — Full Agent Loop  
/implement 20    # Implement Day 20 — Performance Testing
```

## Command

```sh
python .claude/skills-lib/get_day_prompt.py $1
```

This extracts the Claude Code prompt for the specified day and submits it for implementation.
