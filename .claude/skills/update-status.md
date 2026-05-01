---
name: update-status
description: Update the "Built So Far" section in CLAUDE.md to track daily completion
---

# Update Status

Record what you've completed today in CLAUDE.md's "Built So Far" section with an automatic timestamp.

## Usage

```
/update-status Day X: <description of what was built>
```

## Examples

```
/update-status Day 1: Repo setup, docker-compose running, Saleor health check passing
/update-status Day 5: Test runner complete with pytest integration, 50+ tests passing
/update-status Day 10: Full agent loop working, diff analysis, risk scoring, automated reporting
```

## What Happens

Each update is automatically timestamped and added to CLAUDE.md:

```
## Built So Far
- [2026-05-01 14:30] Day 1: Repo setup, docker-compose running, Saleor health check passing
- [2026-05-02 15:45] Day 2: GraphQL schema analyzer complete with introspection
- [2026-05-03 16:20] Day 3: LLM test generator with structured output working
```

This creates an audit trail of your daily progress. At the end of each session, run this before you commit to keep CLAUDE.md up to date for the next session.

## Command

```sh
python .claude/skills-lib/update_status.py $@
```
