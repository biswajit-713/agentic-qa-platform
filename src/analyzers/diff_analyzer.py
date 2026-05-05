"""
src/analyzers/diff_analyzer.py

Parses a git diff and maps changed Saleor source files to affected GraphQL operations.
"""

import logging
import re
import subprocess
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


class ChangeType(str, Enum):
    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"
    RENAMED = "renamed"


class CodeChange(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    file_path: str
    change_type: ChangeType
    added_lines: list[str] = Field(default_factory=list)
    removed_lines: list[str] = Field(default_factory=list)
    context_lines: list[str] = Field(default_factory=list)


class DiffAnalysis(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    changed_files: list[CodeChange] = Field(default_factory=list)
    affected_operations: list[str] = Field(default_factory=list)
    untraced_changes: list[str] = Field(default_factory=list)


# Patterns that identify Saleor GraphQL layer files
_MUTATION_FILE_RE = re.compile(r"saleor/graphql/[^/]+/mutations/[^/]+\.py$")
_RESOLVER_FILE_RE = re.compile(r"saleor/graphql/[^/]+/resolvers\.py$")
_MODEL_FILE_RE = re.compile(r"saleor/[^/]+/models\.py$")

# Class-based mutation: class FooBar(BaseMutation) or (ModelMutation), etc.
_MUTATION_CLASS_RE = re.compile(r"^class\s+([A-Z][A-Za-z0-9]+)\s*\(")
# Resolver function: def resolve_foo_bar(...)
_RESOLVER_FN_RE = re.compile(r"^def\s+(resolve_[a-z_][a-z0-9_]*)\s*\(")
# Django model: class FooBar(Model) or (models.Model)
_MODEL_CLASS_RE = re.compile(r"^class\s+([A-Z][A-Za-z0-9]+)\s*\(")


def _snake_to_camel(name: str) -> str:
    """resolve_foo_bar → fooBar (GraphQL resolver convention)."""
    parts = name.split("_")
    # drop leading 'resolve'
    if parts and parts[0] == "resolve":
        parts = parts[1:]
    if not parts:
        return name
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


def _parse_diff(diff_text: str) -> list[CodeChange]:
    """Parse unified diff text into CodeChange objects."""
    changes: list[CodeChange] = []
    current_file: Optional[str] = None
    current_type: ChangeType = ChangeType.MODIFIED
    prev_minus_path: Optional[str] = None  # path from '--- a/...' line
    added: list[str] = []
    removed: list[str] = []
    context: list[str] = []

    def flush() -> None:
        path = current_file or prev_minus_path
        if path is not None:
            changes.append(
                CodeChange(
                    file_path=path,
                    change_type=current_type,
                    added_lines=added[:],
                    removed_lines=removed[:],
                    context_lines=context[:],
                )
            )

    for raw_line in diff_text.splitlines():
        if raw_line.startswith("diff --git "):
            flush()
            added = []
            removed = []
            context = []
            current_type = ChangeType.MODIFIED
            current_file = None
            prev_minus_path = None

        elif raw_line.startswith("--- "):
            # '--- a/path/to/file.py' or '--- /dev/null'
            path_part = raw_line[4:].strip()
            if path_part != "/dev/null":
                prev_minus_path = path_part[2:] if path_part.startswith("a/") else path_part

        elif raw_line.startswith("+++ "):
            # '+++ b/path/to/file.py' or '+++ /dev/null'
            path_part = raw_line[4:].strip()
            if path_part == "/dev/null":
                current_file = None  # deletion: use prev_minus_path in flush()
            else:
                current_file = path_part[2:] if path_part.startswith("b/") else path_part

        elif raw_line.startswith("new file"):
            current_type = ChangeType.ADDED

        elif raw_line.startswith("deleted file"):
            current_type = ChangeType.DELETED

        elif raw_line.startswith("rename to ") or raw_line.startswith("rename from "):
            current_type = ChangeType.RENAMED

        elif raw_line.startswith("+") and not raw_line.startswith("+++"):
            added.append(raw_line[1:])

        elif raw_line.startswith("-") and not raw_line.startswith("---"):
            removed.append(raw_line[1:])

        elif raw_line.startswith(" "):
            context.append(raw_line[1:])

    flush()
    return changes


def _operations_from_mutation_file(change: CodeChange) -> list[str]:
    """Extract mutation operation names from added+removed lines of a mutations/*.py file."""
    ops: list[str] = []
    all_lines = change.added_lines + change.removed_lines
    for line in all_lines:
        m = _MUTATION_CLASS_RE.match(line.strip())
        if m:
            ops.append(m.group(1))
    return ops


def _operations_from_resolver_file(change: CodeChange) -> list[str]:
    """Extract resolver function names and convert to camelCase operation names."""
    ops: list[str] = []
    all_lines = change.added_lines + change.removed_lines
    for line in all_lines:
        m = _RESOLVER_FN_RE.match(line.strip())
        if m:
            ops.append(_snake_to_camel(m.group(1)))
    return ops


def _operations_from_model_file(change: CodeChange) -> list[str]:
    """Return model type names that may surface as GraphQL types."""
    type_names: list[str] = []
    # Include context lines so existing model classes in a touched file are captured.
    all_lines = change.added_lines + change.removed_lines + change.context_lines
    for line in all_lines:
        m = _MODEL_CLASS_RE.match(line.strip())
        if m:
            type_names.append(m.group(1))
    return type_names


def _map_to_operations(changes: list[CodeChange]) -> tuple[list[str], list[str]]:
    """
    Return (affected_operations, untraced_changes).

    affected_operations: operation / type names derived from heuristics
    untraced_changes: file paths that didn't match any known heuristic
    """
    affected: list[str] = []
    untraced: list[str] = []

    for change in changes:
        path = change.file_path
        matched = False

        if _MUTATION_FILE_RE.search(path):
            ops = _operations_from_mutation_file(change)
            affected.extend(ops)
            matched = bool(ops) or True  # file itself is traced even if no class found

        if _RESOLVER_FILE_RE.search(path):
            ops = _operations_from_resolver_file(change)
            affected.extend(ops)
            matched = True

        if _MODEL_FILE_RE.search(path):
            types = _operations_from_model_file(change)
            affected.extend(types)
            matched = True

        if not matched:
            untraced.append(path)

    return list(dict.fromkeys(affected)), untraced


class DiffAnalyzer:
    """Runs git diff against a repo and maps changed files to GraphQL operations."""

    def __init__(self, repo_path: Optional[Path] = None) -> None:
        self._repo_path = repo_path or Path(".")

    def analyze_diff_text(self, diff_text: str) -> DiffAnalysis:
        """Parse an already-fetched diff string and return a DiffAnalysis."""
        changes = _parse_diff(diff_text)
        affected, untraced = _map_to_operations(changes)
        return DiffAnalysis(
            changed_files=changes,
            affected_operations=affected,
            untraced_changes=untraced,
        )
