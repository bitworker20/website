from __future__ import annotations

import re
import unittest
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse


SITE_ROOT = Path(__file__).resolve().parents[1]


class SiteParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: list[str] = []
        self.attributes: list[tuple[str, dict[str, str]]] = []
        self.text_parts: list[str] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        self.tags.append(tag)
        self.attributes.append(
            (tag, {name: value or "" for name, value in attrs})
        )

    def handle_data(self, data: str) -> None:
        normalized = " ".join(data.split())
        if normalized:
            self.text_parts.append(normalized)


class HomepageContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.index_path = SITE_ROOT / "index.html"
        cls.css_path = SITE_ROOT / "styles.css"
        cls.section_css_path = SITE_ROOT / "sections.css"
        cls.responsive_css_path = SITE_ROOT / "responsive.css"
        cls.script_path = SITE_ROOT / "script.js"
        cls.html = cls.index_path.read_text(encoding="utf-8")
        css_paths = [cls.css_path, cls.section_css_path, cls.responsive_css_path]
        cls.css = "\n".join(path.read_text(encoding="utf-8") for path in css_paths)
        cls.script = cls.script_path.read_text(encoding="utf-8")
        cls.parser = SiteParser()
        cls.parser.feed(cls.html)
        cls.page_text = " ".join(cls.parser.text_parts)

    def test_expected_site_files_exist(self) -> None:
        required = [
            self.index_path,
            self.css_path,
            self.section_css_path,
            self.responsive_css_path,
            self.script_path,
        ]
        self.assertTrue(all(path.is_file() for path in required))

    def test_document_language_is_english(self) -> None:
        self.assertRegex(self.html, r'<html[^>]+lang="en"')

    def test_page_has_exactly_one_h1(self) -> None:
        self.assertEqual(self.parser.tags.count("h1"), 1)

    def test_page_uses_semantic_landmarks(self) -> None:
        self.assertTrue({"header", "nav", "main", "footer"}.issubset(self.parser.tags))

    def test_primary_sections_are_linkable(self) -> None:
        ids = {
            attrs.get("id")
            for _, attrs in self.parser.attributes
            if attrs.get("id")
        }
        self.assertTrue({"technology", "stack", "testnet", "developers"}.issubset(ids))

    def test_homepage_states_the_product_positioning(self) -> None:
        required_copy = (
            "Poker without a dealer",
            "engineering testnet",
            "untrusted relay",
            "deterministic",
        )
        self.assertTrue(all(copy.lower() in self.page_text.lower() for copy in required_copy))

    def test_homepage_names_verified_project_surfaces(self) -> None:
        required_terms = (
            "C++20",
            "Cosmos SDK",
            "Texas Hold’em",
            "Zha Jin Hua",
            "WebAssembly",
            "Explorer",
        )
        self.assertTrue(all(term in self.page_text for term in required_terms))

    def test_metadata_is_complete(self) -> None:
        required_metadata = (
            'name="description"',
            'property="og:title"',
            'property="og:description"',
            'name="theme-color"',
        )
        self.assertTrue(all(item in self.html for item in required_metadata))

    def test_images_have_alt_text(self) -> None:
        images = [attrs for tag, attrs in self.parser.attributes if tag == "img"]
        self.assertTrue(all("alt" in image for image in images))

    def test_local_references_resolve(self) -> None:
        references: list[str] = []
        for tag, attrs in self.parser.attributes:
            if tag == "a" and attrs.get("href"):
                references.append(attrs["href"])
            if tag in {"img", "script"} and attrs.get("src"):
                references.append(attrs["src"])
            if tag == "link" and attrs.get("href"):
                references.append(attrs["href"])
        local_paths = [
            SITE_ROOT / urlparse(reference).path
            for reference in references
            if not urlparse(reference).scheme
            and not reference.startswith(("#", "mailto:", "tel:"))
        ]
        self.assertTrue(all(path.is_file() for path in local_paths))

    def test_external_new_tab_links_are_safe(self) -> None:
        external_links = [
            attrs
            for tag, attrs in self.parser.attributes
            if tag == "a"
            and attrs.get("target") == "_blank"
            and urlparse(attrs.get("href", "")).scheme in {"http", "https"}
        ]
        self.assertTrue(all("noopener" in link.get("rel", "") for link in external_links))

    def test_mobile_navigation_exposes_state(self) -> None:
        menu_buttons = [
            attrs
            for tag, attrs in self.parser.attributes
            if tag == "button" and attrs.get("data-menu-toggle") == ""
        ]
        self.assertTrue(
            len(menu_buttons) == 1
            and menu_buttons[0].get("aria-expanded") == "false"
            and bool(menu_buttons[0].get("aria-controls"))
        )

    def test_css_defines_brand_tokens(self) -> None:
        required_tokens = ("--ink", "--gold", "--felt", "--surface", "--line")
        self.assertTrue(all(token in self.css for token in required_tokens))

    def test_css_contains_responsive_layout(self) -> None:
        self.assertRegex(self.css, r"@media\s*\([^)]*max-width")

    def test_css_respects_reduced_motion(self) -> None:
        self.assertIn("prefers-reduced-motion: reduce", self.css)

    def test_javascript_has_no_debug_logging(self) -> None:
        self.assertIsNone(re.search(r"console\.(log|debug)\s*\(", self.script))


if __name__ == "__main__":
    unittest.main()
