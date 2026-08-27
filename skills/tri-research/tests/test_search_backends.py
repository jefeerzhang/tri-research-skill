"""Regression tests for search_backends.py option mapping.

Bug: TavilyBackend.search forwarded the CLI flag dest ``depth`` verbatim to
``TavilyClient.search``. The Tavily API parameter is ``search_depth``; the
SDK accepts unknown ``**kwargs`` without forwarding them, so
``--depth advanced`` was silently dropped while the JSON output metadata
still claimed ``"search_depth": "advanced"``.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from _test_helpers import load_module

SCRIPTS_DIR = Path(__file__).parents[1] / "scripts"


class _FakeTavilyClient:
    """Captures the exact kwargs TavilyClient.search would receive."""

    def __init__(self) -> None:
        self.kwargs: dict = {}

    def search(self, **kwargs):
        self.kwargs = kwargs
        return {"results": []}


class TavilyOptionMappingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.backends = load_module(SCRIPTS_DIR / "search_backends.py", "sb_mapping_test")

    def test_depth_flag_maps_to_search_depth(self) -> None:
        client = _FakeTavilyClient()
        output = self.backends.TAVILY_BACKEND.search(client, "q", {"max_results": 5, "depth": "advanced"})
        self.assertEqual(client.kwargs.get("search_depth"), "advanced")
        self.assertNotIn("depth", client.kwargs)
        # Output metadata must keep reporting the applied depth.
        self.assertEqual(output["search_depth"], "advanced")

    def test_depth_omitted_when_not_passed(self) -> None:
        client = _FakeTavilyClient()
        self.backends.TAVILY_BACKEND.search(client, "q", {"max_results": 5})
        self.assertNotIn("depth", client.kwargs)
        self.assertNotIn("search_depth", client.kwargs)

    def test_domain_flags_are_split_into_lists(self) -> None:
        client = _FakeTavilyClient()
        self.backends.TAVILY_BACKEND.search(
            client,
            "q",
            {"include_domains": "a.com,b.com", "exclude_domains": "c.com"},
        )
        self.assertEqual(client.kwargs["include_domains"], ["a.com", "b.com"])
        self.assertEqual(client.kwargs["exclude_domains"], ["c.com"])


if __name__ == "__main__":
    unittest.main()
