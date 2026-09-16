"""Behavioural tests for the turnstile and the toll booth.

test_site.py is a contract suite: it reads the files as text and checks that
the pieces are present and wired. That cannot catch the failures that matter
here, which are all about *what the code decides* — who gets let through, and
which payments count. An expired pass that still opens the door, or a failed
transfer accepted as payment, would pass every string assertion in the other
file.

So these run the real turnstile.js and pay.js in node, on stubbed browser
objects, and assert the decisions. Skipped where node is not installed — it is
not a build dependency of the site, only of checking it (test_site.py uses it
the same way for `node --check`).

Both toll destinations are exercised, because they read different messages out
of the same transaction: the community pool takes MsgFundCommunityPool, an
address takes MsgSend. A deployment configured for one must not accept the
other — paying the pool would otherwise open a site whose toll goes to an
account, and vice versa.

Run from the repository root:

    python3 -m unittest discover -s website/tests -v
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent
NODE = shutil.which("node")


def run_harness(js: str) -> dict:
    """Run one harness script in node and return the JSON it prints."""
    with tempfile.TemporaryDirectory() as tmp:
        script = Path(tmp) / "harness.js"
        script.write_text(js.replace("__SITE__", str(SITE)), encoding="utf-8")
        result = subprocess.run(
            [NODE, str(script)], capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            raise AssertionError(f"harness failed:\n{result.stderr}")
        return json.loads(result.stdout)


TURNSTILE_HARNESS = r"""
const fs = require("fs"), vm = require("vm");
const src = fs.readFileSync("__SITE__/turnstile.js", "utf8");
const VERIFIER = JSON.parse(/var CONFIG = (\{[\s\S]*?\});/.exec(src)[1]).verifier;
const TOLL = { to: "community", uchip: 100000, hours: 24 };
const now = Math.floor(Date.now() / 1000);

function visit(store, toll, pathname) {
  let replaced = null;
  const sandbox = {};
  sandbox.window = {
    localStorage: { getItem: (k) => (k in store ? store[k] : null) },
    location: { pathname: pathname || "/overview.html", replace: (u) => { replaced = u; } },
    BITPOKER: toll ? { toll: toll } : {},
  };
  vm.createContext(sandbox);
  vm.runInContext(src, sandbox);
  return replaced;
}

const pass = (over) =>
  JSON.stringify(Object.assign({ v: 1, to: TOLL.to, expires: now + 3600 }, over));

console.log(JSON.stringify({
  no_credential: visit({}, TOLL),
  no_credential_no_toll: visit({}, null),
  passphrase: visit({ "bitpoker.gate": VERIFIER }, TOLL),
  valid_pass: visit({ "bitpoker.pass": pass({}) }, TOLL),
  expired_pass: visit({ "bitpoker.pass": pass({ expires: now - 1 }) }, TOLL),
  pass_for_another_toll: visit({ "bitpoker.pass": pass({ to: "xpoker1someone" }) }, TOLL),
  pool_pass_at_an_address_toll: visit({ "bitpoker.pass": pass({}) },
                                      { to: "xpoker1someone", uchip: 100000, hours: 24 }),
  pass_without_a_toll: visit({ "bitpoker.pass": pass({}) }, null),
  corrupt_pass: visit({ "bitpoker.pass": "{not json" }, TOLL),
  odd_path: visit({}, TOLL, "/evil.example/x.html"),
}));
"""


PAY_HARNESS = r"""
const fs = require("fs"), vm = require("vm");
const src = fs.readFileSync("__SITE__/pay.js", "utf8");
const POOL_TOLL = { to: "community", uchip: 100000, hours: 24 };
const ADDRESS_TOLL = { to: "xpoker1toll", uchip: 100000, hours: 24 };
const CHALLENGE = "ABCD1234EFGH";
const SELECTORS = ["[data-deck]", "[data-face]", "[data-pip]", "[data-suit]", "[data-note]",
                   "[data-form]", "[data-hash]", "[data-submit]", "[data-amount]",
                   "[data-address]", "[data-command]", "[data-challenge]"];

function element() {
  return {
    textContent: "", innerHTML: "", value: "", handlers: {},
    classList: { toggle() {}, add() {}, remove() {} },
    addEventListener(type, fn) { this.handlers[type] = fn; },
  };
}

async function buy(respond, toll) {
  const store = { "bitpoker.challenge": CHALLENGE };
  const nodes = {};
  SELECTORS.forEach((s) => { nodes[s] = element(); });
  let redirected = null;
  const sandbox = { console: console };
  sandbox.window = {
    BITPOKER: { toll: toll || POOL_TOLL, chainRest: ["https://chain.example/rest"] },
    localStorage: {
      getItem: (k) => (k in store ? store[k] : null),
      setItem: (k, v) => { store[k] = v; },
    },
    location: { search: "?next=chain.html", replace: (u) => { redirected = u; } },
    setTimeout: (fn) => setTimeout(fn, 0),
    clearTimeout: clearTimeout,
    crypto: { getRandomValues: (a) => { a.fill(7); return a; } },
    fetch: (url) => {
      const reply = respond(url);
      return reply instanceof Error
        ? Promise.reject(reply)
        : Promise.resolve({ status: reply.status, json: () => Promise.resolve(reply.body) });
    },
  };
  sandbox.document = {
    readyState: "complete",
    querySelector: (s) => nodes[s] || null,
    querySelectorAll: () => [],
  };
  sandbox.AbortController = function () { this.signal = {}; this.abort = function () {}; };
  sandbox.navigator = {};
  vm.createContext(sandbox);
  vm.runInContext(src, sandbox);

  nodes["[data-hash]"].value = "A".repeat(64);
  await nodes["[data-form]"].handlers.submit({ preventDefault() {} });
  await new Promise((r) => setTimeout(r, 30));
  return {
    note: nodes["[data-note]"].textContent,
    command: nodes["[data-command]"].textContent,
    destination: nodes["[data-address]"].textContent,
    pass: store["bitpoker.pass"] ? JSON.parse(store["bitpoker.pass"]) : null,
    redirected: redirected,
  };
}

const fund = (over) => ({
  "@type": "/cosmos.distribution.v1beta1.MsgFundCommunityPool",
  depositor: "xpoker1payer",
  amount: [{ denom: "uchip", amount: "100000" }],
  ...over,
});

const send = (over) => ({
  "@type": "/cosmos.bank.v1beta1.MsgSend",
  to_address: ADDRESS_TOLL.to,
  from_address: "xpoker1payer",
  amount: [{ denom: "uchip", amount: "100000" }],
  ...over,
});

const tx = (messages, over) => ({
  status: 200,
  body: {
    tx_response: {
      txhash: "A".repeat(64), code: 0, timestamp: "2026-09-15T00:00:00Z", ...((over || {}).resp || {}),
    },
    tx: { body: { memo: CHALLENGE, messages: messages, ...((over || {}).body || {}) } },
  },
});

(async () => {
  const out = {};
  out.paid = await buy(() => tx([fund({})]));
  out.failed_tx = await buy(() => tx([fund({})], { resp: { code: 7 } }));
  out.wrong_memo = await buy(() => tx([fund({})], { body: { memo: "WRONGMEMO123" } }));
  out.short = await buy(() => tx([fund({ amount: [{ denom: "uchip", amount: "40000" }] })]));
  out.wrong_denom = await buy(() => tx([fund({ amount: [{ denom: "ustake", amount: "999999" }] })]));
  out.two_messages = await buy(() => tx([
    send({ to_address: "xpoker1elsewhere", amount: [{ denom: "uchip", amount: "900000" }] }),
    fund({ amount: [{ denom: "uchip", amount: "60000" }] }),
    fund({ amount: [{ denom: "uchip", amount: "40000" }] }),
  ]));
  out.transfer_at_a_pool_toll = await buy(() => tx([send({})]));
  out.unreachable = await buy(() => new Error("no route to host"));
  out.catching_up = await buy((u) => (u.includes("syncing") ? { status: 200, body: { syncing: true } } : { status: 404, body: {} }));
  out.not_yet = await buy((u) => (u.includes("syncing") ? { status: 200, body: { syncing: false } } : { status: 404, body: {} }));

  out.address_mode = await buy(() => tx([send({})]), ADDRESS_TOLL);
  out.address_mode_wrong_account = await buy(
    () => tx([send({ to_address: "xpoker1someoneelse", amount: [{ denom: "uchip", amount: "999999" }] })]),
    ADDRESS_TOLL);
  out.pool_payment_at_an_address_toll = await buy(() => tx([fund({})]), ADDRESS_TOLL);
  console.log(JSON.stringify(out));
})();
"""


@unittest.skipUnless(NODE, "node is not installed")
class TestTurnstileDecisions(unittest.TestCase):
    """Who gets through, and where the rest are sent."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.result = run_harness(TURNSTILE_HARNESS)

    def test_a_visitor_with_neither_credential_is_sent_to_the_booth(self) -> None:
        self.assertEqual(self.result["no_credential"], "pay.html?next=overview.html")

    def test_with_no_toll_configured_the_passphrase_is_the_only_door(self) -> None:
        """An unconfigured deployment must behave like the site did before the
        toll existed — and must never send anyone to a booth that has nothing
        to sell."""
        self.assertEqual(self.result["no_credential_no_toll"], "index.html")
        self.assertEqual(self.result["pass_without_a_toll"], "index.html")

    def test_either_credential_opens_the_page(self) -> None:
        self.assertIsNone(self.result["passphrase"])
        self.assertIsNone(self.result["valid_pass"])

    def test_a_pass_stops_working_when_it_should(self) -> None:
        self.assertEqual(self.result["expired_pass"], "pay.html?next=overview.html")
        self.assertEqual(self.result["pass_for_another_toll"], "pay.html?next=overview.html")
        self.assertEqual(self.result["corrupt_pass"], "pay.html?next=overview.html")

    def test_repointing_the_toll_invalidates_the_passes_it_sold(self) -> None:
        """A pass bought when the toll funded the community pool must not keep
        opening the site after the toll becomes someone's account."""
        self.assertEqual(self.result["pool_pass_at_an_address_toll"],
                         "pay.html?next=overview.html")

    def test_the_return_address_cannot_be_pointed_off_site(self) -> None:
        """`next` is handed to location.replace on a page anyone can link to."""
        self.assertEqual(self.result["odd_path"], "pay.html?next=x.html")


@unittest.skipUnless(NODE, "node is not installed")
class TestPaymentJudgements(unittest.TestCase):
    """Which payments buy a day, and what the booth says about the rest."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.result = run_harness(PAY_HARNESS)

    def test_a_good_payment_buys_exactly_one_day_from_the_block(self) -> None:
        paid = self.result["paid"]
        self.assertIsNotNone(paid["pass"])
        self.assertEqual(paid["pass"]["expires"] - paid["pass"]["paidAt"], 24 * 3600)
        self.assertEqual(paid["pass"]["payer"], "xpoker1payer")
        self.assertEqual(paid["pass"]["to"], "community")
        self.assertEqual(paid["redirected"], "chain.html")

    def test_the_booth_hands_over_a_command_that_pays_the_right_toll(self) -> None:
        """A visitor should not have to work out the message type themselves."""
        paid = self.result["paid"]
        self.assertIn("fund-community-pool 100000uchip", paid["command"])
        self.assertIn("--note ABCD1234EFGH", paid["command"])
        self.assertIn("community pool", paid["destination"])
        self.assertIn("bank send", self.result["address_mode"]["command"])

    def test_a_transaction_that_failed_on_chain_is_not_a_payment(self) -> None:
        """Inclusion in a block is not execution."""
        failed = self.result["failed_tx"]
        self.assertIsNone(failed["pass"])
        self.assertIn("code 7", failed["note"])

    def test_someone_elses_payment_does_not_open_this_browser(self) -> None:
        self.assertIsNone(self.result["wrong_memo"]["pass"])
        self.assertIn("memo", self.result["wrong_memo"]["note"])

    def test_the_amount_must_reach_the_toll_in_the_right_denom(self) -> None:
        self.assertIsNone(self.result["short"]["pass"])
        self.assertIn("short", self.result["short"]["note"])
        self.assertIsNone(self.result["wrong_denom"]["pass"])

    def test_only_what_reached_the_toll_counts_towards_it(self) -> None:
        """One transaction, three messages: a large transfer somewhere else
        plus two small fundings that together make the toll."""
        self.assertIsNotNone(self.result["two_messages"]["pass"])

    def test_each_destination_refuses_the_other_ones_payment(self) -> None:
        self.assertIsNone(self.result["transfer_at_a_pool_toll"]["pass"])
        self.assertIsNone(self.result["pool_payment_at_an_address_toll"]["pass"])
        self.assertIsNone(self.result["address_mode_wrong_account"]["pass"])
        self.assertIsNotNone(self.result["address_mode"]["pass"])

    def test_an_unreadable_chain_is_not_reported_as_an_unpaid_toll(self) -> None:
        """The failure this booth must not have: telling someone who just paid
        that they did not."""
        unreachable = self.result["unreachable"]
        self.assertIsNone(unreachable["pass"])
        self.assertIn("Could not reach a node", unreachable["note"])

    def test_a_node_behind_the_chain_says_so(self) -> None:
        """A catching-up node honestly reports 'never seen it' about a
        transaction that is already committed."""
        self.assertIn("catching up", self.result["catching_up"]["note"])
        self.assertIn("No such transaction", self.result["not_yet"]["note"])
