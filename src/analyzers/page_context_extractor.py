"""
src/analyzers/page_context_extractor.py

Visits pages with Playwright and extracts pruned accessibility trees.
Used to ground UI test generation in real page structure rather than LLM guesses.
"""

import logging
from typing import Optional

from playwright.sync_api import sync_playwright

logger = logging.getLogger(__name__)

# Roles worth keeping — interactive elements, landmarks, and headings
_KEEP_ROLES = frozenset({
    "button", "link", "textbox", "searchbox", "combobox", "listbox",
    "option", "checkbox", "radio", "switch", "menuitem", "tab",
    "heading", "navigation", "main", "form", "banner", "contentinfo",
    "dialog", "alert", "img",
})

# Roles that add no signal — skip unless they have useful children
_SKIP_ROLES = frozenset({"none", "presentation", "generic"})

_MAX_DEPTH = 6
_MAX_CHILDREN = 20  # per node, to cap runaway lists


def _prune(node: dict, depth: int = 0) -> Optional[dict]:
    """Recursively prune an accessibility tree node.

    Drops purely decorative nodes, caps depth, and limits children per node.
    Returns None if the node has no useful content.
    """
    if depth > _MAX_DEPTH:
        return None

    role = (node.get("role") or "").lower()
    name = (node.get("name") or "").strip()
    raw_children = node.get("children") or []

    pruned_children = []
    for child in raw_children[:_MAX_CHILDREN]:
        result = _prune(child, depth + 1)
        if result is not None:
            pruned_children.append(result)

    # Keep node if it has a useful role or any surviving children
    if role in _SKIP_ROLES and not pruned_children:
        return None
    if role not in _KEEP_ROLES and not name and not pruned_children:
        return None

    out: dict = {"role": role}
    if name:
        out["name"] = name
    value = node.get("value")
    if value:
        out["value"] = value
    if pruned_children:
        out["children"] = pruned_children
    return out


class PageContextExtractor:
    """Extracts pruned accessibility snapshots from live pages using Playwright."""

    def __init__(self, timeout_ms: int = 10_000):
        """
        Args:
            timeout_ms: Navigation timeout in milliseconds.
        """
        self.timeout_ms = timeout_ms

    def extract(self, url: str) -> dict:
        """Visit a URL and return a pruned accessibility tree.

        Args:
            url: Page URL to visit.

        Returns:
            Pruned accessibility snapshot dict (empty dict on failure).
        """
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(url, timeout=self.timeout_ms, wait_until="domcontentloaded")
                snapshot = page.accessibility.snapshot() or {}
                browser.close()

            pruned = _prune(snapshot) or {}
            logger.info(f"Extracted accessibility tree from {url} ({_count_nodes(pruned)} nodes)")
            return pruned

        except Exception as e:
            logger.warning(f"Could not extract page context from {url}: {e}")
            return {}

    def extract_flow(self, urls: list[str]) -> dict[str, dict]:
        """Visit multiple URLs and return a snapshot per URL.

        Useful for multi-step flows where each step lands on a different page.

        Args:
            urls: Ordered list of page URLs to visit.

        Returns:
            Dict mapping each URL to its pruned accessibility snapshot.
        """
        results: dict[str, dict] = {}
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                for url in urls:
                    try:
                        page.goto(url, timeout=self.timeout_ms, wait_until="domcontentloaded")
                        snapshot = page.accessibility.snapshot() or {}
                        pruned = _prune(snapshot) or {}
                        results[url] = pruned
                        logger.info(f"Extracted {_count_nodes(pruned)} nodes from {url}")
                    except Exception as e:
                        logger.warning(f"Skipping {url}: {e}")
                        results[url] = {}
                browser.close()
        except Exception as e:
            logger.error(f"Browser launch failed during flow extraction: {e}")

        return results


def _count_nodes(node: dict) -> int:
    """Count total nodes in a pruned tree (for logging)."""
    if not node:
        return 0
    return 1 + sum(_count_nodes(c) for c in node.get("children", []))
