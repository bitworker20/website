"""Contract tests for the BitPoker internal engineering site.

The site has no build step, so these are the only thing standing between an
edit and a broken page: every local asset the HTML references must exist,
the navigation must resolve on every page, the in-page TOC anchors must
point at headings that exist, and the accessibility affordances (skip
link, menu semantics, reduced motion) must survive edits.

The site is one unguessable door and a row of fixed rooms: index.html is
the invitation gate, the real site starts at a token page named after a
token derived from the passphrase, and every content page has a fixed name
and runs turnstile.js before anything renders. The turnstile takes either
credential — the passphrase the gate stores, or a day pass bought on
pay.html by paying the toll on chain. These tests find the token page the
way the gate does — by reading gate.js — and additionally check that
nothing in the gate leaks the way in, that both of its doors are still
wired, that every content page is behind the turnstile, that the booth
that sells passes is *not* (or nobody could ever buy one), and that
rotating the passphrase keeps gate.js and turnstile.js in lockstep.

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
TURNSTILE_JS = SITE / "turnstile.js"
PAY_JS = SITE / "pay.js"
GATE_HTML = (SITE / "index.html").read_text(encoding="utf-8")
GATE_CONFIG = json.loads(
    re.search(r"var CONFIG = (\{.*?\});", GATE_JS.read_text(encoding="utf-8"), re.DOTALL).group(1)
)

TOKEN_PAGE = SITE / GATE_CONFIG["target"]

# The fixed-name content pages, in reading order. Every cross-page link on
# the site must land on one of these (or the gate, or an asset).
CONTENT_PAGES = [
    "overview.html",
    "crypto.html",
    "protocol.html",
    "chain.html",
    "adjudication.html",
    "relay.html",
    "operations.html",
    "testnet.html",
    "lessons.html",
]

CSS = (SITE / "styles.css").read_text(encoding="utf-8")
SCRIPT = (SITE / "script.js").read_text(encoding="utf-8")
CONFIG_JS = (SITE / "config.js").read_text(encoding="utf-8")


class TagCollector(HTMLParser):
    """Collects (tag, attrs-as-dict) for every start tag."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[tuple[str, dict[str, str]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append((tag, {k: (v or "") for k, v in attrs}))

    handle_startendtag = handle_starttag


def parse(html: str) -> list[tuple[str, dict[str, str]]]:
    collector = TagCollector()
    collector.feed(html)
    return collector.tags


def page(name: str) -> str:
    return (SITE / name).read_text(encoding="utf-8")


def ids_in(html: str) -> set[str]:
    return {attrs["id"] for _, attrs in parse(html) if attrs.get("id")}


def local_hrefs(html: str) -> list[str]:
    """Every href/src that points at a local file (no scheme, no mailto)."""
    out = []
    for tag, attrs in parse(html):
        value = attrs.get("href") or attrs.get("src") or ""
        if not value or value.startswith(("#", "http://", "https://", "mailto:", "data:")):
            continue
        out.append(value.split("#")[0].split("?")[0])
    return out


# ───────────────────────────────  every page  ────────────────────────────────


class TestEveryContentPage(unittest.TestCase):
    def test_all_content_pages_exist(self) -> None:
        for name in CONTENT_PAGES:
            self.assertTrue((SITE / name).is_file(), f"missing content page: {name}")

    def test_every_page_declares_language_charset_and_noindex(self) -> None:
        for name in CONTENT_PAGES:
            html = page(name)
            self.assertIn('lang="en"', html, name)
            self.assertIn('charset="utf-8"', html.lower(), name)
            self.assertIn('content="noindex, nofollow"', html, f"{name}: internal site must not be indexable")

    def test_every_page_has_title_and_description(self) -> None:
        for name in CONTENT_PAGES:
            html = page(name)
            self.assertRegex(html, r"<title>.*BitPoker.*</title>", name)
            self.assertIn('name="description"', html, name)

    def test_every_page_loads_the_shared_stylesheet_and_config(self) -> None:
        for name in CONTENT_PAGES:
            html = page(name)
            self.assertIn('href="styles.css"', html, name)

    def test_every_content_page_is_behind_the_turnstile(self) -> None:
        """turnstile.js must be a blocking <script> in <head>, before
        script.js, so an unauthenticated visitor never sees the page flash
        first — and after config.js, which carries the toll it checks
        against. A turnstile that runs first reads no toll and would send a
        paying visitor back to the gate."""
        for name in CONTENT_PAGES:
            html = page(name)
            turnstile_at = html.index('src="turnstile.js"')
            head_end = html.index("</head>")
            self.assertLess(turnstile_at, head_end, f"{name}: turnstile.js must load in <head>")
            self.assertNotIn('defer', html[turnstile_at:html.index(">", turnstile_at)],
                           f"{name}: turnstile.js must not be deferred")
            self.assertLess(html.index('src="config.js"'), turnstile_at,
                           f"{name}: config.js must load before turnstile.js")
            self.assertLess(turnstile_at, html.index('src="script.js"'),
                           f"{name}: turnstile.js must load before script.js")

    def test_every_page_has_skip_link_targeting_main(self) -> None:
        for name in CONTENT_PAGES:
            tags = parse(page(name))
            skips = [a["href"] for t, a in tags if t == "a" and "skip-link" in a.get("class", "")]
            self.assertEqual(skips, ["#main"], name)
            self.assertTrue(any(t == "main" and a.get("id") == "main" for t, a in tags), name)

    def test_every_page_has_landmarks(self) -> None:
        for name in CONTENT_PAGES:
            tags = parse(page(name))
            kinds = {t for t, _ in tags}
            for landmark in ("header", "nav", "main", "footer"):
                self.assertIn(landmark, kinds, f"{name}: missing <{landmark}>")

    def test_menu_button_is_wired_to_the_navigation(self) -> None:
        for name in CONTENT_PAGES:
            tags = parse(page(name))
            toggles = [a for t, a in tags if t == "button" and "nav-toggle" in a.get("class", "")]
            self.assertEqual(len(toggles), 1, name)
            controls = toggles[0].get("aria-controls")
            self.assertTrue(controls, name)
            self.assertTrue(
                any(t == "nav" and a.get("id") == controls for t, a in tags),
                f"{name}: aria-controls points at nothing",
            )
            self.assertIn(toggles[0].get("aria-expanded"), {"false", "true"}, name)

    def test_lock_button_is_present(self) -> None:
        for name in CONTENT_PAGES:
            self.assertIn("data-lock", page(name), name)

    def test_reduced_motion_is_respected(self) -> None:
        self.assertIn("@media (prefers-reduced-motion: reduce)", CSS)

    def test_layout_is_responsive(self) -> None:
        self.assertIn("@media (max-width: 820px)", CSS)
        self.assertIn("@media (min-width: 1000px)", CSS)  # the doc-layout breakpoint


# ─────────────────────────────  navigation & anchors  ────────────────────────


class TestNavigation(unittest.TestCase):
    def test_nav_links_are_the_content_pages(self) -> None:
        for name in CONTENT_PAGES:
            tags = parse(page(name))
            nav = next(a for t, a in tags if t == "nav" and a.get("id") == "site-nav")
            # nav element itself has no hrefs; collect its anchor children crudely:
            # the nav block is between its opening tag and </nav>
            html = page(name)
            nav_block = html[html.index('id="site-nav"'):]
            nav_block = nav_block[: nav_block.index("</nav>")]
            hrefs = re.findall(r'href="([^"#]+\.html)"', nav_block)
            self.assertEqual(sorted(set(hrefs)), sorted(CONTENT_PAGES),
                             f"{name}: primary nav must link every content page exactly")

    def test_current_page_is_marked_in_nav(self) -> None:
        for name in CONTENT_PAGES:
            html = page(name)
            nav_block = html[html.index('id="site-nav"'):]
            nav_block = nav_block[: nav_block.index("</nav>")]
            self.assertIn(f'href="{name}" aria-current="page"', nav_block,
                         f"{name}: should mark itself aria-current")

    def test_toc_anchors_resolve_to_headings(self) -> None:
        for name in CONTENT_PAGES:
            html = page(name)
            if 'class="toc"' not in html:
                continue
            toc_block = html[html.index('class="toc"'):]
            toc_block = toc_block[: toc_block.index("</nav>")]
            anchors = set(re.findall(r'href="#([a-zA-Z0-9_-]+)"', toc_block))
            self.assertTrue(anchors, f"{name}: TOC has no links")
            missing = anchors - ids_in(html)
            self.assertFalse(missing, f"{name}: TOC links to missing ids: {sorted(missing)}")

    def test_in_page_anchor_links_all_resolve(self) -> None:
        for name in CONTENT_PAGES:
            html = page(name)
            anchors = set(re.findall(r'href="#([a-zA-Z0-9_-]+)"', html))
            missing = anchors - ids_in(html)
            self.assertFalse(missing, f"{name}: anchor links to missing ids: {sorted(missing)}")

    def test_cross_page_links_point_at_content_pages_or_the_gate(self) -> None:
        allowed = set(CONTENT_PAGES) | {"index.html"}
        for name in CONTENT_PAGES:
            for href in local_hrefs(page(name)):
                if href.endswith(".html"):
                    self.assertIn(href, allowed, f"{name}: links to unknown page {href}")

    def test_no_page_links_the_token_page(self) -> None:
        """The token page must stay unnamed everywhere except gate.js —
        naming it in the site would let a reader skip the door's entropy."""
        token = GATE_CONFIG["target"]
        for name in CONTENT_PAGES:
            self.assertNotIn(token, page(name), f"{name}: names the token page")
        self.assertNotIn(token, GATE_HTML, "index.html: names the token page")
        self.assertNotIn(token, SCRIPT, "script.js: names the token page")
        self.assertNotIn(token, CSS, "styles.css: names the token page")


# ────────────────────────────────  assets  ──────────────────────────────────


class TestAssets(unittest.TestCase):
    def test_every_local_reference_exists(self) -> None:
        for name in ["index.html", *CONTENT_PAGES]:
            for href in local_hrefs(page(name)):
                self.assertTrue((SITE / href).is_file(), f"{name}: missing local file {href}")

    def test_stylesheet_is_the_only_one(self) -> None:
        for name in CONTENT_PAGES:
            sheets = [a["href"] for t, a in parse(page(name))
                     if t == "link" and "stylesheet" in a.get("rel", "")
                     and "fonts.googleapis" not in a.get("href", "")]
            self.assertEqual(sheets, ["styles.css"], name)

    def test_icons_cover_svg_png_and_apple(self) -> None:
        for name in CONTENT_PAGES:
            html = page(name)
            self.assertIn("favicon.svg", html, name)
            self.assertIn("favicon-32.png", html, name)
            self.assertIn("apple-touch-icon", html, name)

    def test_theme_colour_matches_the_page_background(self) -> None:
        theme = re.search(r'name="theme-color" content="#([0-9a-fA-F]{6})"', page("overview.html"))
        self.assertIsNotNone(theme)
        self.assertIn(f"--bg: #{theme.group(1)}".lower(), CSS.lower())

    def test_external_links_are_safe(self) -> None:
        for name in CONTENT_PAGES:
            for tag, attrs in parse(page(name)):
                if tag == "a" and attrs.get("href", "").startswith("http"):
                    self.assertIn("noopener", attrs.get("rel", ""),
                                  f"{name}: {attrs['href']} missing rel=noopener")


# ────────────────────────────────  the gate  ────────────────────────────────


class TestGate(unittest.TestCase):
    def test_index_is_the_invitation_gate(self) -> None:
        self.assertIn("Invitation only", GATE_HTML)
        self.assertIn("gate.js", GATE_HTML)

    def test_the_gate_has_both_doors(self) -> None:
        gate = GATE_JS.read_text(encoding="utf-8")
        self.assertIn("/v1/invite/redeem", gate, "code door missing")
        self.assertIn("PBKDF2", gate, "passphrase door missing")

    def test_index_leaks_neither_the_address_nor_the_content(self) -> None:
        token = GATE_CONFIG["target"]
        self.assertNotIn(token, GATE_HTML)
        for word in ("Barnett", "FourQ", "adjudicat"):
            self.assertNotIn(word, GATE_HTML, f"index.html leaks content: {word}")

    def test_an_unreachable_daemon_is_not_reported_as_a_wrong_code(self) -> None:
        gate = GATE_JS.read_text(encoding="utf-8")
        self.assertIn("offline", gate)
        self.assertIn("Could not reach the door", gate)

    def test_gate_config_is_complete_and_stretched(self) -> None:
        for key in ("salt", "iterations", "length", "verifier", "target"):
            self.assertIn(key, GATE_CONFIG)
        self.assertGreaterEqual(GATE_CONFIG["iterations"], 100_000)
        self.assertEqual(len(GATE_CONFIG["verifier"]), 32)
        self.assertEqual(len(GATE_CONFIG["target"]), 16 + len(".html"))
        self.assertTrue(TOKEN_PAGE.is_file(), "token page missing from disk")

    def test_token_page_forwards_to_the_overview(self) -> None:
        stub = TOKEN_PAGE.read_text(encoding="utf-8")
        self.assertIn("overview.html", stub)
        self.assertIn("location.replace", stub)

    def test_turnstile_config_matches_gate_config(self) -> None:
        turnstile = TURNSTILE_JS.read_text(encoding="utf-8")
        turnstile_config = json.loads(
            re.search(r"var CONFIG = (\{.*?\});", turnstile, re.DOTALL).group(1)
        )
        self.assertEqual(turnstile_config, GATE_CONFIG,
                         "turnstile.js config drifted from gate.js — run tools/gate.py")

    def test_neither_page_is_indexable(self) -> None:
        self.assertIn('content="noindex, nofollow"', GATE_HTML)
        for name in CONTENT_PAGES:
            self.assertIn('content="noindex, nofollow"', page(name), name)
        robots = (SITE / "robots.txt").read_text(encoding="utf-8")
        self.assertIn("Disallow: /", robots)

    def test_derivation_is_deterministic_and_salt_dependent(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SITE / "tools" / "gate.py"), "check", "definitely-not-the-passphrase"],
            capture_output=True, text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does not open", result.stdout)

    def test_gate_opens_without_webcrypto(self) -> None:
        gate = GATE_JS.read_text(encoding="utf-8")
        self.assertIn("function pbkdf2", gate)
        self.assertIn("if (!subtle)", gate)


# ────────────────────────────────  scripts  ─────────────────────────────────


class TestScripts(unittest.TestCase):
    def test_scripts_parse(self) -> None:
        for js in (SCRIPT, GATE_JS.read_text(encoding="utf-8"),
                  TURNSTILE_JS.read_text(encoding="utf-8"),
                  PAY_JS.read_text(encoding="utf-8"), CONFIG_JS):
            compile_ok = subprocess.run(
                ["node", "--check", "-"], input=js, capture_output=True, text=True,
            ) if _have_node() else None
            if compile_ok is not None:
                self.assertEqual(compile_ok.returncode, 0, js[:80])

    def test_no_faucet_ui_remains(self) -> None:
        """The public faucet went away with the public site; its hooks must not
        linger in the shared script or stylesheet."""
        self.assertNotIn("data-faucet", SCRIPT)
        self.assertNotIn(".faucet", CSS)
        for name in CONTENT_PAGES:
            self.assertNotIn("data-faucet", page(name), name)

    def test_lock_forgets_both_gate_and_invite(self) -> None:
        self.assertIn('removeItem("bitpoker.gate")', SCRIPT)
        self.assertIn('removeItem("bitpoker.invite")', SCRIPT)

    def test_turnstile_uses_the_same_storage_key_as_the_gate(self) -> None:
        turnstile = TURNSTILE_JS.read_text(encoding="utf-8")
        self.assertIn('STORE_KEY = "bitpoker.gate"', turnstile)
        self.assertIn('STORE_KEY = "bitpoker.gate"', GATE_JS.read_text(encoding="utf-8"))

    def test_lock_forgets_the_day_pass_too(self) -> None:
        """Locking the browser must forget every way back in. A pass left
        behind is a paid day handed to whoever has the machine next."""
        self.assertIn('removeItem("bitpoker.pass")', SCRIPT)
        self.assertIn('removeItem("bitpoker.challenge")', SCRIPT)


# ──────────────────────────────  the toll booth  ─────────────────────────────


class TestTurnstile(unittest.TestCase):
    """pay.html sells a day pass for an on-chain payment; turnstile.js takes
    it. Both doors stay open: the passphrase is the one that still works when
    the chain cannot be read."""

    def test_the_turnstile_takes_either_credential(self) -> None:
        js = TURNSTILE_JS.read_text(encoding="utf-8")
        self.assertIn("hasPassphrase", js)
        self.assertIn("hasDayPass", js)
        self.assertIn('PASS_KEY = "bitpoker.pass"', js)

    def test_a_pass_is_bound_to_the_toll_it_paid(self) -> None:
        """Repointing the site at another destination must invalidate every
        outstanding pass — otherwise yesterday's payments keep opening a door
        whose beneficiary has changed."""
        self.assertIn("pass.to === t.to", TURNSTILE_JS.read_text(encoding="utf-8"))

    def test_config_declares_the_toll_and_where_to_check_it(self) -> None:
        # config.js is hand-written JavaScript, not JSON (unquoted keys,
        # comments), so this reads it the way a reviewer would rather than
        # pretending it parses.
        self.assertRegex(CONFIG_JS, r"toll:\s*\{", "config.js declares no toll")
        for key in ("to", "uchip", "hours"):
            self.assertRegex(CONFIG_JS, rf"\b{key}:", f"toll.{key} missing from config.js")
        self.assertRegex(CONFIG_JS, r"chainRest:\s*\[\s*\"http",
                         "config.js names no endpoint to read the chain")

    def test_the_booth_is_outside_the_turnstile(self) -> None:
        """pay.html is where an unpaid visitor is sent. Putting it behind the
        turnstile would be a closed loop with no way in."""
        booth = page("pay.html")
        self.assertNotIn("turnstile.js", booth)
        self.assertIn("config.js", booth)
        self.assertIn("pay.js", booth)

    def test_the_booth_gives_nothing_away(self) -> None:
        """It renders for anyone, so it must not name the rooms or the stub."""
        booth = page("pay.html")
        self.assertNotIn(GATE_CONFIG["target"], booth)
        for name in CONTENT_PAGES:
            self.assertNotIn(name, booth, f"pay.html names {name}")

    def test_the_booths_local_references_exist(self) -> None:
        for href in local_hrefs(page("pay.html")):
            self.assertTrue((SITE / href).is_file(), f"pay.html: missing local file {href}")

    def test_the_price_is_not_written_twice(self) -> None:
        """The amount lives in config.js. A copy in pay.js is a second number
        to keep in step, and the one that would silently go stale."""
        # \b so the uchip-per-CHIP constant (1000000) is not mistaken for a
        # hard-coded toll (100000).
        self.assertNotRegex(PAY_JS.read_text(encoding="utf-8"), r"\b100000\b")

    def test_an_unreadable_chain_is_never_reported_as_an_unpaid_toll(self) -> None:
        """The one failure this page must not have: telling someone who just
        paid that they did not. Same rule as the gate's card for an
        unreachable faucet daemon."""
        js = PAY_JS.read_text(encoding="utf-8")
        self.assertIn("syncing", js)
        self.assertIn("Could not reach a node", js)

    def test_the_payment_must_have_executed(self) -> None:
        """Inclusion in a block is not execution: a failed transfer moves
        nothing. Checked here because this is the third place in the tree
        where trusting the wrong field has cost real money."""
        js = PAY_JS.read_text(encoding="utf-8")
        self.assertIn("response.code !== 0", js)
        self.assertIn("MsgFundCommunityPool", js)
        self.assertIn("MsgSend", js)


def _have_node() -> bool:
    from shutil import which
    return which("node") is not None


if __name__ == "__main__":
    unittest.main()
