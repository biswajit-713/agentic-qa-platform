"""
tests/test_page_context_extractor.py

Unit tests for PageContextExtractor and the _prune helper.
All browser calls are mocked — no live Playwright required.
"""

import pytest
from unittest.mock import MagicMock, patch, call

from src.analyzers.page_context_extractor import (
    PageContextExtractor,
    _prune,
    _count_nodes,
    _MAX_DEPTH,
)


# ---------------------------------------------------------------------------
# _prune
# ---------------------------------------------------------------------------

class TestPrune:
    def test_keeps_button_with_name(self):
        node = {"role": "button", "name": "Add to cart"}
        result = _prune(node)
        assert result == {"role": "button", "name": "Add to cart"}

    def test_keeps_link_with_name(self):
        node = {"role": "link", "name": "Products"}
        assert _prune(node) is not None

    def test_drops_generic_node_without_name_or_children(self):
        node = {"role": "generic"}
        assert _prune(node) is None

    def test_drops_presentation_node(self):
        node = {"role": "presentation"}
        assert _prune(node) is None

    def test_drops_none_role_node(self):
        node = {"role": "none"}
        assert _prune(node) is None

    def test_keeps_generic_if_has_useful_children(self):
        node = {
            "role": "generic",
            "children": [{"role": "button", "name": "Submit"}],
        }
        result = _prune(node)
        assert result is not None
        assert len(result["children"]) == 1

    def test_preserves_value(self):
        node = {"role": "textbox", "name": "Search", "value": "shoes"}
        result = _prune(node)
        assert result["value"] == "shoes"

    def test_omits_empty_value(self):
        node = {"role": "textbox", "name": "Search", "value": ""}
        result = _prune(node)
        assert "value" not in result

    def test_truncates_at_max_depth(self):
        # Build a chain deeper than _MAX_DEPTH
        node: dict = {"role": "button", "name": "deep"}
        for _ in range(_MAX_DEPTH + 3):
            node = {"role": "navigation", "children": [node]}
        result = _prune(node)
        # The chain should be truncated — deepest nodes won't appear
        assert result is not None

    def test_caps_children_per_node(self):
        children = [{"role": "button", "name": f"btn{i}"} for i in range(30)]
        node = {"role": "main", "children": children}
        result = _prune(node)
        assert len(result["children"]) <= 20

    def test_empty_node_returns_none(self):
        assert _prune({}) is None

    def test_heading_kept_without_name(self):
        # headings are in _KEEP_ROLES so kept even without name if role matches
        node = {"role": "heading"}
        result = _prune(node)
        assert result is not None


# ---------------------------------------------------------------------------
# _count_nodes
# ---------------------------------------------------------------------------

class TestCountNodes:
    def test_empty_dict(self):
        assert _count_nodes({}) == 0

    def test_single_node(self):
        assert _count_nodes({"role": "button"}) == 1

    def test_nested(self):
        node = {
            "role": "main",
            "children": [
                {"role": "button"},
                {"role": "link", "children": [{"role": "img"}]},
            ],
        }
        assert _count_nodes(node) == 4


# ---------------------------------------------------------------------------
# PageContextExtractor.extract
# ---------------------------------------------------------------------------

class TestExtract:
    def _make_playwright_mock(self, snapshot: dict):
        """Build a full sync_playwright context manager mock."""
        mock_page = MagicMock()
        mock_page.accessibility.snapshot.return_value = snapshot

        mock_browser = MagicMock()
        mock_browser.new_page.return_value = mock_page

        mock_chromium = MagicMock()
        mock_chromium.launch.return_value = mock_browser

        mock_pw = MagicMock()
        mock_pw.chromium = mock_chromium

        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_pw)
        mock_ctx.__exit__ = MagicMock(return_value=False)

        return mock_ctx, mock_page, mock_browser

    def test_returns_pruned_dict(self):
        snapshot = {
            "role": "WebArea",
            "name": "Storefront",
            "children": [{"role": "button", "name": "Add to cart"}],
        }
        mock_ctx, _, _ = self._make_playwright_mock(snapshot)

        with patch("src.analyzers.page_context_extractor.sync_playwright", return_value=mock_ctx):
            extractor = PageContextExtractor()
            result = extractor.extract("http://localhost:3000")

        assert isinstance(result, dict)
        assert result  # non-empty

    def test_returns_empty_dict_on_playwright_error(self):
        with patch(
            "src.analyzers.page_context_extractor.sync_playwright",
            side_effect=Exception("browser crash"),
        ):
            extractor = PageContextExtractor()
            result = extractor.extract("http://localhost:3000")

        assert result == {}

    def test_returns_empty_dict_when_snapshot_is_none(self):
        mock_ctx, _, _ = self._make_playwright_mock(None)

        with patch("src.analyzers.page_context_extractor.sync_playwright", return_value=mock_ctx):
            extractor = PageContextExtractor()
            result = extractor.extract("http://localhost:3000")

        assert result == {}

    def test_passes_timeout_to_goto(self):
        snapshot = {"role": "button", "name": "Buy"}
        mock_ctx, mock_page, _ = self._make_playwright_mock(snapshot)

        with patch("src.analyzers.page_context_extractor.sync_playwright", return_value=mock_ctx):
            extractor = PageContextExtractor(timeout_ms=5000)
            extractor.extract("http://localhost:3000")

        mock_page.goto.assert_called_once_with(
            "http://localhost:3000", timeout=5000, wait_until="domcontentloaded"
        )

    def test_closes_browser(self):
        snapshot = {"role": "button", "name": "Buy"}
        mock_ctx, _, mock_browser = self._make_playwright_mock(snapshot)

        with patch("src.analyzers.page_context_extractor.sync_playwright", return_value=mock_ctx):
            extractor = PageContextExtractor()
            extractor.extract("http://localhost:3000")

        mock_browser.close.assert_called_once()


# ---------------------------------------------------------------------------
# PageContextExtractor.extract_flow
# ---------------------------------------------------------------------------

class TestExtractFlow:
    def test_returns_dict_keyed_by_url(self):
        snapshot = {"role": "button", "name": "Add to cart"}

        mock_page = MagicMock()
        mock_page.accessibility.snapshot.return_value = snapshot
        mock_browser = MagicMock()
        mock_browser.new_page.return_value = mock_page
        mock_pw = MagicMock()
        mock_pw.chromium.launch.return_value = mock_browser
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_pw)
        mock_ctx.__exit__ = MagicMock(return_value=False)

        urls = ["http://localhost:3000", "http://localhost:3000/cart"]
        with patch("src.analyzers.page_context_extractor.sync_playwright", return_value=mock_ctx):
            extractor = PageContextExtractor()
            result = extractor.extract_flow(urls)

        assert set(result.keys()) == set(urls)

    def test_returns_empty_dict_per_url_on_goto_error(self):
        mock_page = MagicMock()
        mock_page.goto.side_effect = Exception("timeout")
        mock_browser = MagicMock()
        mock_browser.new_page.return_value = mock_page
        mock_pw = MagicMock()
        mock_pw.chromium.launch.return_value = mock_browser
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_pw)
        mock_ctx.__exit__ = MagicMock(return_value=False)

        with patch("src.analyzers.page_context_extractor.sync_playwright", return_value=mock_ctx):
            extractor = PageContextExtractor()
            result = extractor.extract_flow(["http://localhost:3000"])

        assert result == {"http://localhost:3000": {}}

    def test_returns_empty_on_browser_launch_failure(self):
        with patch(
            "src.analyzers.page_context_extractor.sync_playwright",
            side_effect=Exception("no browser"),
        ):
            extractor = PageContextExtractor()
            result = extractor.extract_flow(["http://localhost:3000"])

        assert result == {}
