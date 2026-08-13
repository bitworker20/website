"""Contract tests for the BitPoker site.

The site has no build step, so these are the only thing standing between an edit
and a broken page: every local asset the HTML references must exist, the
metadata a link preview needs must be present, the install commands on the page
must be ones install.sh actually accepts, and the accessibility affordances
(skip link, menu semantics, image alt text, reduced motion) must survive edits.

The real page is not index.html — index.html is the coming-soon gate, and the
page it opens is named after a token derived from the passphrase. These tests
find it the way the gate does, by reading gate.js, and additionally check that
nothing in the gate leaks the way in.

Run from the repository root:

    python3 -m unittest discover -s website/tests -v
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import unittest
from html.parser import HTMLParser
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent
GATE_JS = SITE / "gate.js"
GATE_HTML = (SITE / "index.html").read_text(encoding="utf-8")
GATE_CONFIG = json.loads(
    re.search(r"var CONFIG = (\{.*?\});", GATE_JS.read_text(encoding="utf-8"), re.DOTALL).group(1)
)

INDEX = SITE / GATE_CONFIG["target"]
HTML = INDEX.read_text(encoding="utf-8")
CSS = (SITE / "styles.css").read_text(encoding="utf-8")
INSTALL = SITE / "install.sh"


class TagCollector(HTMLParser):
    """Collects (tag, attrs-as-dict) for every start tag."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[tuple[str, dict[str, str]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append((tag, {k: (v or "") for k, v in attrs}))

    handle_startendtag = handle_starttag


def parse() -> list[tuple[str, dict[str, str]]]:
    collector = TagCollector()
    collector.feed(HTML)
    return collector.tags


TAGS = parse()


def tags_named(name: str) -> list[dict[str, str]]:
    return [attrs for tag, attrs in TAGS if tag == name]


def meta_content(**match: str) -> str | None:
    for attrs in tags_named("meta"):
        if all(attrs.get(key) == value for key, value in match.items()):
            return attrs.get("content")
    return None


class TestDocument(unittest.TestCase):
    def test_declares_language_and_charset(self) -> None:
        self.assertIn('<html lang="en">', HTML)
        self.assertIn("charset", {key for attrs in tags_named("meta") for key in attrs})

    def test_has_title_and_description(self) -> None:
        self.assertIn("<title>BitPoker", HTML)
        description = meta_content(name="description")
        self.assertIsNotNone(description)
        self.assertGreater(len(description or ""), 80)

    def test_states_what_the_project_is(self) -> None:
        # The page is the front door: these are the claims it must keep making.
        for phrase in (
            "mental cryptography",
            "escrow",
            "consensus",
            "relay",
            "whitepaper",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, HTML.lower())

    def test_sections_the_navigation_points_at_all_exist(self) -> None:
        ids = {attrs["id"] for _, attrs in TAGS if "id" in attrs}
        for href in (
            attrs["href"]
            for attrs in tags_named("a")
            if attrs.get("href", "").startswith("#")
        ):
            with self.subTest(href=href):
                self.assertIn(href[1:], ids)

    def test_required_sections_present(self) -> None:
        # "node" is deliberately absent: the one-line installer section is
        # commented out until install.sh and the published release assets agree.
        for section in ("protocol", "engineering", "clients", "downloads"):
            with self.subTest(section=section):
                self.assertIn(f'id="{section}"', HTML)


class TestMetadata(unittest.TestCase):
    def test_open_graph_and_twitter_card(self) -> None:
        self.assertEqual(meta_content(property="og:type"), "website")
        self.assertTrue(meta_content(property="og:title"))
        self.assertTrue(meta_content(property="og:description"))
        self.assertEqual(meta_content(property="og:image"), "assets/og-image.png")
        self.assertEqual(meta_content(property="og:image:width"), "1200")
        self.assertEqual(meta_content(property="og:image:height"), "630")
        self.assertTrue(meta_content(property="og:image:alt"))
        self.assertEqual(meta_content(name="twitter:card"), "summary_large_image")

    def test_icons_cover_svg_png_and_apple(self) -> None:
        rels = {attrs.get("rel"): attrs for attrs in tags_named("link")}
        self.assertIn("apple-touch-icon", rels)
        icon_hrefs = [
            attrs["href"] for attrs in tags_named("link") if attrs.get("rel") == "icon"
        ]
        self.assertIn("assets/favicon.svg", icon_hrefs)
        self.assertTrue(any(href.endswith(".png") for href in icon_hrefs))

    def test_theme_colour_matches_the_page_background(self) -> None:
        theme = (meta_content(name="theme-color") or "").lower()
        background = re.search(r"--bg:\s*(#[0-9a-f]{6})", CSS)
        self.assertIsNotNone(background)
        self.assertEqual(theme, background.group(1).lower())


class TestAssets(unittest.TestCase):
    def local_refs(self) -> list[str]:
        refs = []
        for tag, attrs in TAGS:
            for key in ("href", "src"):
                value = attrs.get(key)
                if not value or value.startswith(("#", "http", "mailto:", "data:")):
                    continue
                refs.append(value)
        return refs

    def test_every_local_reference_exists(self) -> None:
        for ref in self.local_refs():
            with self.subTest(ref=ref):
                self.assertTrue((SITE / ref).exists(), f"missing file: {ref}")

    def test_stylesheet_is_the_only_one(self) -> None:
        sheets = [
            attrs["href"]
            for attrs in tags_named("link")
            if attrs.get("rel") == "stylesheet" and not attrs["href"].startswith("http")
        ]
        self.assertEqual(sheets, ["styles.css"])

    def test_screenshots_are_referenced_with_alt_text_and_dimensions(self) -> None:
        images = tags_named("img")
        self.assertTrue(images)
        for attrs in images:
            with self.subTest(src=attrs.get("src")):
                self.assertIn("alt", attrs)
                if "assets/screenshots/" in attrs.get("src", ""):
                    # Decorative marks carry alt=""; screenshots must describe
                    # what is on screen, and must not reflow the page as they load.
                    self.assertGreater(len(attrs["alt"]), 40)
                    self.assertIn("width", attrs)
                    self.assertIn("height", attrs)

    def test_whitepaper_is_downloadable_from_the_page(self) -> None:
        self.assertIn("assets/bitpoker-whitepaper.pdf", HTML)
        self.assertTrue((SITE / "assets/bitpoker-whitepaper.pdf").exists())


class TestLinks(unittest.TestCase):
    def test_external_links_are_safe(self) -> None:
        for attrs in tags_named("a"):
            href = attrs.get("href", "")
            if not href.startswith("http"):
                continue
            with self.subTest(href=href):
                self.assertTrue(href.startswith("https://"), "external links must be https")
                if attrs.get("target") == "_blank":
                    rel = attrs.get("rel", "")
                    self.assertIn("noopener", rel)
                    self.assertIn("noreferrer", rel)

    def test_release_downloads_point_at_a_release_asset(self) -> None:
        release_links = [
            attrs["href"]
            for attrs in tags_named("a")
            if "releases" in attrs.get("href", "")
        ]
        self.assertGreaterEqual(len(release_links), 3)
        for href in release_links:
            with self.subTest(href=href):
                self.assertIn("/releases/", href)
                self.assertTrue(href.endswith((".apk", ".AppImage", ".tar.gz", ".txt")))

    def test_the_three_client_packages_are_offered(self) -> None:
        # An AppImage, an APK and the server/CLI tarball — the asset names must
        # be the unversioned ones, because /releases/latest/download/<name>
        # only resolves a name that does not move between releases.
        hrefs = " ".join(
            attrs.get("href", "") for attrs in tags_named("a") if "releases" in attrs.get("href", "")
        )
        for asset in (
            "bitpoker-android-arm64.apk",
            "BitPoker-x86_64.AppImage",
            "bitpoker-bin-ubuntu-x64.tar.gz",
        ):
            with self.subTest(asset=asset):
                self.assertIn(f"/releases/latest/download/{asset}", hrefs)


class TestInstaller(unittest.TestCase):
    def test_script_is_present_and_executable(self) -> None:
        self.assertTrue(INSTALL.exists())
        self.assertTrue(INSTALL.stat().st_mode & 0o111, "install.sh must be executable")
        self.assertTrue(INSTALL.read_text(encoding="utf-8").startswith("#!/bin/sh"))

    def test_script_parses(self) -> None:
        result = subprocess.run(
            ["sh", "-n", str(INSTALL)], capture_output=True, text=True, check=False
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_page_commands_use_roles_the_script_accepts(self) -> None:
        # Commented-out markup is not on the page, so the install section being
        # hidden means no commands to check — but the moment it comes back, its
        # roles have to be ones the script dispatches on.
        visible = re.sub(r"<!--.*?-->", "", HTML, flags=re.DOTALL)
        commands = re.findall(r"curl -fsSL \S+/install\.sh \| sh -s -- (\w+)", visible)
        script = INSTALL.read_text(encoding="utf-8")
        accepted = re.search(r"^\s*([\w|]+)\) ;;$", script, re.MULTILINE)
        self.assertIsNotNone(accepted)
        self.assertLessEqual(set(commands), set(accepted.group(1).split("|")))

    def test_the_installer_section_is_hidden(self) -> None:
        # Guards the pair: while the page offers no installer, nothing should
        # link to #node either (a dead in-page anchor scrolls nowhere).
        visible = re.sub(r"<!--.*?-->", "", HTML, flags=re.DOTALL)
        self.assertNotIn("install.sh", visible)
        self.assertNotIn('href="#node"', visible)

    def test_script_refuses_unknown_roles(self) -> None:
        result = subprocess.run(
            ["sh", str(INSTALL), "definitely-not-a-role"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("unknown role", result.stderr)


class TestGate(unittest.TestCase):
    def test_index_is_the_coming_soon_page(self) -> None:
        self.assertIn("Coming soon", GATE_HTML)
        self.assertIn("gate.js", GATE_HTML)

    def test_index_leaks_neither_the_address_nor_the_content(self) -> None:
        token = GATE_CONFIG["target"].split(".")[0]
        self.assertNotIn(token, GATE_HTML)
        for word in ("whitepaper", "download", "install.sh", "relay", "escrow"):
            with self.subTest(word=word):
                self.assertNotIn(word, GATE_HTML.lower())

    def test_nothing_in_the_site_links_back_to_the_gated_page_by_name(self) -> None:
        # Any file that names the target hands out the address for free.
        target = GATE_CONFIG["target"]
        for path in SITE.rglob("*"):
            if not path.is_file() or path.name in {target, "gate.js"}:
                continue
            if path.suffix not in {".html", ".css", ".js", ".txt", ".md", ".sh"}:
                continue
            if path.is_relative_to(SITE / "tests"):
                continue
            with self.subTest(path=path.name):
                self.assertNotIn(target, path.read_text(encoding="utf-8", errors="ignore"))

    def test_gate_config_is_complete_and_stretched(self) -> None:
        self.assertEqual(len(GATE_CONFIG["salt"]), 32)
        self.assertEqual(len(GATE_CONFIG["verifier"]), 32)
        self.assertGreaterEqual(GATE_CONFIG["iterations"], 100_000)
        self.assertGreater(GATE_CONFIG["length"], 5)
        self.assertRegex(GATE_CONFIG["target"], r"^[0-9a-f]{16}\.html$")
        self.assertTrue((SITE / GATE_CONFIG["target"]).is_file())

    def test_neither_page_is_indexable(self) -> None:
        for name, source in (("gate", GATE_HTML), ("site", HTML)):
            with self.subTest(page=name):
                self.assertIn('name="robots"', source)
                self.assertIn("noindex", source)
        robots = (SITE / "robots.txt").read_text(encoding="utf-8")
        self.assertIn("Disallow: /", robots)

    def test_shared_link_preview_says_nothing(self) -> None:
        card = re.search(r'og:image" content="([^"]+)"', GATE_HTML)
        self.assertIsNotNone(card)
        self.assertEqual(card.group(1), "assets/og-card-soon.png")
        self.assertTrue((SITE / card.group(1)).is_file())

    def test_derivation_is_deterministic_and_salt_dependent(self) -> None:
        sys.path.insert(0, str(SITE / "tools"))
        try:
            import gate  # noqa: PLC0415 — the tool under test
        finally:
            sys.path.pop(0)

        first = gate.derive("a passphrase", "00" * 16)
        self.assertEqual(first, gate.derive("a passphrase", "00" * 16))
        self.assertNotEqual(first, gate.derive("a passphrase", "11" * 16))
        self.assertNotEqual(first, gate.derive("another passphrase", "00" * 16))
        verifier, token = first
        self.assertEqual((len(verifier), len(token)), (32, 16))
        self.assertNotIn(token, verifier)

    def test_gate_opens_without_webcrypto(self) -> None:
        # crypto.subtle is absent outside a secure context — over plain http on
        # a LAN address, or from disk — which is exactly how the gate gets
        # tested first. Without the fallback it would silently never open.
        source = GATE_JS.read_text(encoding="utf-8")
        self.assertIn("if (!subtle) {", source)
        self.assertIn("function sha256(", source)
        self.assertIn("function pbkdf2(", source)
        self.assertNotIn("if (!subtle || !CONFIG.verifier)", source)

    def test_wrong_passphrase_is_rejected_by_the_tool(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SITE / "tools/gate.py"), "check", "not-the-passphrase"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("does not open", result.stdout)


class TestAccessibility(unittest.TestCase):
    def test_skip_link_targets_main(self) -> None:
        self.assertIn('class="skip-link" href="#main"', HTML)
        self.assertIn('id="main"', HTML)

    def test_landmarks(self) -> None:
        for landmark in ("<header", "<main", "<footer", "<nav"):
            with self.subTest(landmark=landmark):
                self.assertIn(landmark, HTML)

    def test_menu_button_is_wired_to_the_navigation(self) -> None:
        buttons = [
            attrs for attrs in tags_named("button") if "nav-toggle" in attrs.get("class", "")
        ]
        self.assertEqual(len(buttons), 1)
        self.assertEqual(buttons[0].get("aria-expanded"), "false")
        self.assertEqual(buttons[0].get("aria-controls"), "site-nav")
        self.assertIn('id="site-nav"', HTML)

    def test_copy_buttons_reference_existing_command_elements(self) -> None:
        targets = re.findall(r'data-copy-target="([^"]+)"', HTML)
        self.assertTrue(targets)
        for target in targets:
            with self.subTest(target=target):
                self.assertIn(f'id="{target}"', HTML)

    def test_reduced_motion_is_respected(self) -> None:
        self.assertIn("prefers-reduced-motion: reduce", CSS)

    def test_layout_is_responsive(self) -> None:
        self.assertIsNotNone(meta_content(name="viewport"))
        self.assertGreaterEqual(CSS.count("@media"), 2)


if __name__ == "__main__":
    unittest.main()
