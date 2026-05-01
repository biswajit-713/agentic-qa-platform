#!/usr/bin/env python3
"""
Update the "Built So Far" section in CLAUDE.md
Usage: python .claude/skills-lib/update_status.py "Day X: Description of what was built"
"""

import sys
import re
from pathlib import Path
from datetime import datetime


def update_claude_md(message: str) -> bool:
    """Update the Built So Far section in CLAUDE.md with a new completion entry."""
    claude_md_path = Path(__file__).parent.parent.parent / "CLAUDE.md"

    if not claude_md_path.exists():
        print(f"Error: CLAUDE.md not found at {claude_md_path}")
        return False

    with open(claude_md_path, 'r') as f:
        content = f.read()

    # Pattern to find the "Built So Far" section
    # Match everything from "## Built So Far" to the next section or end of file
    pattern = r"(## Built So Far\n)(.*?)(\n(?=##|\Z))"

    # Check if section exists
    match = re.search(pattern, content, re.MULTILINE | re.DOTALL)

    if not match:
        print("Error: Could not find 'Built So Far' section in CLAUDE.md")
        print("Make sure the section exists with '## Built So Far' header")
        return False

    # Get current timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Create new entry
    new_entry = f"- [{timestamp}] {message}"

    # Get existing content and clean it
    existing_content = match.group(2).strip()

    # Remove "Nothing yet" lines
    existing_lines = [line for line in existing_content.split('\n') if line.strip() and 'Nothing yet' not in line]

    # Reconstruct with new entry at the top
    if existing_lines:
        updated_content = new_entry + "\n" + "\n".join(existing_lines)
    else:
        updated_content = new_entry

    # Replace in content
    new_content = content[: match.start(2)] + "\n" + updated_content + content[match.start(3) :]

    # Write back
    with open(claude_md_path, 'w') as f:
        f.write(new_content)

    print(f"✅ Updated CLAUDE.md")
    print(f"   {new_entry}")
    return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python .claude/skills-lib/update_status.py \"Day X: Description\"")
        print("Example: python .claude/skills-lib/update_status.py \"Day 1: Repo setup, docker-compose, health check\"")
        sys.exit(1)

    message = " ".join(sys.argv[1:])  # Handle multi-word arguments

    if update_claude_md(message):
        sys.exit(0)
    else:
        sys.exit(1)
