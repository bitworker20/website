// The toll booth.
//
// Buying a day pass is three facts the visitor has to put on chain — an
// amount, an address and a memo — and one fact this page has to read back out
// of it: that the transaction executed, carried that memo, and moved at least
// that much to that address. Everything below is those two halves.
//
// What it refuses to do is guess. If no endpoint answers, or the node it
// reached is still catching up, the card stays face down and the note says the
// chain could not be read — never "you did not pay". Someone who just spent
// 0.1 CHIP and is told they did not is the one failure this page must not
// have, and it is the same rule the invitation card follows for an unreachable
// faucet daemon.

(function () {
  "use strict";

  var CONFIG = window.BITPOKER || {};
  var TOLL = CONFIG.toll || {};
  var RESTS = (CONFIG.chainRest || []).slice();

  var PASS_KEY = "bitpoker.pass";
  var CHALLENGE_KEY = "bitpoker.challenge";
  var UCHIP_PER_CHIP = 1000000;
  var REQUEST_TIMEOUT_MS = 12000;

  // Where the toll goes. The community pool is the default because it needs
  // no account: no key to keep, no balance to sweep, and nobody who can spend
  // it without a governance proposal — so "who is collecting this?" has an
  // answer nobody has to be trusted for. Any other value is an address, and
  // the toll becomes an ordinary transfer to it.
  var COMMUNITY = TOLL.to === "community";
  var FUND_POOL = "/cosmos.distribution.v1beta1.MsgFundCommunityPool";
  var BANK_SEND = "/cosmos.bank.v1beta1.MsgSend";

  // Crockford base32 minus the letters that misread (I, L, O, U) — the same
  // alphabet the invitation codes use, so the two things a visitor may be
  // asked to type look like they come from the same system.
  var ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ";

  var deck = document.querySelector("[data-deck]");
  var face = document.querySelector("[data-face]");
  var pip = document.querySelector("[data-pip]");
  var suit = document.querySelector("[data-suit]");
  var note = document.querySelector("[data-note]");
  var form = document.querySelector("[data-form]");
  var hashField = document.querySelector("[data-hash]");
  var submit = document.querySelector("[data-submit]");

  function say(text, bad) {
    if (!note) {
      return;
    }
    note.textContent = text;
    note.classList.toggle("bad", !!bad);
  }

  // Face down = not judged. Ace = paid. Seven = judged and refused.
  function turn(card) {
    if (!deck || !face) {
      return;
    }
    if (!card) {
      deck.classList.remove("flipped");
      return;
    }
    if (pip) {
      pip.textContent = card === "ace" ? "A" : "7";
    }
    if (suit) {
      suit.innerHTML = card === "ace" ? "&spades;" : "&diams;";
    }
    face.classList.toggle("is-bad", card !== "ace");
    deck.classList.add("flipped");
  }

  function stored(key) {
    try {
      return window.localStorage.getItem(key);
    } catch (error) {
      return null;
    }
  }

  function remember(key, value) {
    try {
      window.localStorage.setItem(key, value);
    } catch (error) {
      /* storage blocked: the pass lasts this page load only */
    }
  }

  function randomCode() {
    var bytes = new Uint8Array(12);
    if (window.crypto && window.crypto.getRandomValues) {
      window.crypto.getRandomValues(bytes);
    } else {
      for (var i = 0; i < bytes.length; ++i) {
        bytes[i] = Math.floor(Math.random() * 256);
      }
    }
    var out = "";
    for (var j = 0; j < bytes.length; ++j) {
      out += ALPHABET[bytes[j] % ALPHABET.length];
    }
    return out;
  }

  // The challenge is what binds a payment to *this* browser. Without it anyone
  // watching the chain could take someone else's payment for their own pass:
  // every transfer to the toll address is public the moment it lands.
  function challenge() {
    var existing = stored(CHALLENGE_KEY);
    if (existing && /^[0-9A-Z]{12}$/.test(existing)) {
      return existing;
    }
    var fresh = randomCode();
    remember(CHALLENGE_KEY, fresh);
    return fresh;
  }

  function grouped(code) {
    return code.replace(/(.{4})(?=.)/g, "$1-");
  }

  function normalizeMemo(text) {
    return String(text || "").toUpperCase().replace(/[^0-9A-Z]/g, "");
  }

  function chip(uchip) {
    var whole = Math.floor(uchip / UCHIP_PER_CHIP);
    var fraction = String(uchip % UCHIP_PER_CHIP).padStart(6, "0").replace(/0+$/, "");
    return fraction ? whole + "." + fraction : String(whole);
  }

  function nextPage() {
    var match = /[?&]next=([^&]+)/.exec(window.location.search || "");
    var raw = match ? decodeURIComponent(match[1]) : "";
    return /^[A-Za-z0-9._-]+\.html$/.test(raw) ? raw : "overview.html";
  }

  function getJSON(base, path) {
    var controller = typeof AbortController === "function" ? new AbortController() : null;
    var timer = window.setTimeout(function () {
      if (controller) {
        controller.abort();
      }
    }, REQUEST_TIMEOUT_MS);
    var options = controller ? { signal: controller.signal } : {};
    return window.fetch(base.replace(/\/+$/, "") + path, options).then(function (response) {
      window.clearTimeout(timer);
      return response.json().then(function (body) {
        return { status: response.status, body: body };
      }, function () {
        return { status: response.status, body: null };
      });
    }, function (error) {
      window.clearTimeout(timer);
      throw error;
    });
  }

  // Tries the configured endpoints in order and returns the first that
  // answers at all — a 404 is an answer (that transaction is not on chain
  // yet), a dead host is not.
  function askChain(path) {
    var index = 0;
    function attempt() {
      if (index >= RESTS.length) {
        return Promise.reject(new Error("no endpoint answered"));
      }
      var base = RESTS[index++];
      return getJSON(base, path).catch(attempt);
    }
    return attempt();
  }

  // One transaction can carry several messages and several coins; only what
  // actually reached the toll counts, in the denom the toll is priced in.
  function reachesTheToll(message) {
    return COMMUNITY
      ? message["@type"] === FUND_POOL
      : message["@type"] === BANK_SEND && message.to_address === TOLL.to;
  }

  function sumToToll(messages) {
    var total = 0;
    (messages || []).forEach(function (message) {
      if (!reachesTheToll(message)) {
        return;
      }
      (message.amount || []).forEach(function (coin) {
        if (coin.denom === "uchip") {
          total += parseInt(coin.amount, 10) || 0;
        }
      });
    });
    return total;
  }

  function payerOf(messages) {
    var found = "";
    (messages || []).forEach(function (message) {
      if (!found && reachesTheToll(message)) {
        found = (COMMUNITY ? message.depositor : message.from_address) || "";
      }
    });
    return found;
  }

  function commandFor(code) {
    var amount = TOLL.uchip + "uchip";
    return COMMUNITY
      ? "pokerchaind tx distribution fund-community-pool " + amount + " --note " + code + " --from <key>"
      : "pokerchaind tx bank send <key> " + TOLL.to + " " + amount + " --note " + code;
  }

  // A node that is still replaying blocks can honestly say "I have never seen
  // that transaction" about one that is already committed. Asking first is the
  // difference between "not yet" and a lie.
  function syncing() {
    return askChain("/cosmos/base/tendermint/v1beta1/syncing").then(function (reply) {
      return !!(reply.body && reply.body.syncing);
    }, function () {
      return false;
    });
  }

  function grant(txhash, payer, paidAt) {
    var hours = TOLL.hours || 24;
    var pass = {
      v: 1,
      to: TOLL.to,
      txhash: txhash,
      payer: payer,
      memo: challenge(),
      paidAt: paidAt,
      expires: paidAt + hours * 3600
    };
    remember(PASS_KEY, JSON.stringify(pass));
    turn("ace");
    say("Paid. " + hours + " hours from the block that carried it.");
    window.setTimeout(function () {
      window.location.replace(nextPage());
    }, 1200);
  }

  function judge(txhash) {
    var wanted = challenge();
    return askChain("/cosmos/tx/v1beta1/txs/" + txhash).then(function (reply) {
      var response = reply.body && reply.body.tx_response;
      if (reply.status === 404 || !response || !response.txhash) {
        return syncing().then(function (behind) {
          turn(null);
          say(behind
            ? "The node is still catching up, so it cannot see that transaction yet. Try again in a moment."
            : "No such transaction on chain yet. If you have just sent it, give it a block.");
        });
      }
      if (response.code !== 0) {
        turn("seven");
        say("That transaction failed on chain (code " + response.code + "), so nothing moved.");
        return undefined;
      }

      var body = (reply.body.tx && reply.body.tx.body) || {};
      var memo = normalizeMemo(body.memo);
      if (memo !== wanted) {
        turn("seven");
        say(memo
          ? "That payment carries the memo " + grouped(memo) + ", not " + grouped(wanted) + "."
          : "That payment has no memo. It needs " + grouped(wanted) + " to count for this browser.");
        return undefined;
      }

      var paid = sumToToll(body.messages);
      if (paid < TOLL.uchip) {
        turn("seven");
        say("That payment is " + chip(TOLL.uchip - paid) + " CHIP short — send the difference and check again.");
        return undefined;
      }

      var seconds = Math.floor(Date.parse(response.timestamp) / 1000);
      grant(response.txhash, payerOf(body.messages), isNaN(seconds) ? Math.floor(Date.now() / 1000) : seconds);
      return undefined;
    }, function () {
      // Nothing answered. Not judged, so not refused.
      turn(null);
      say("Could not reach a node to check. Your payment, if you made one, is unaffected — try again, or use the passphrase.", true);
    });
  }

  function start() {
    var code = challenge();
    var amount = document.querySelector("[data-amount]");
    var address = document.querySelector("[data-address]");
    var command = document.querySelector("[data-command]");
    var memo = document.querySelector("[data-challenge]");

    if (!TOLL.to || !TOLL.uchip) {
      say("No toll is configured for this deployment — the passphrase is the only way in.", true);
      if (submit) {
        submit.disabled = true;
      }
      return;
    }

    if (amount) {
      amount.textContent = chip(TOLL.uchip) + " CHIP";
    }
    if (address) {
      address.textContent = COMMUNITY
        ? "the community pool — no account holds it, and only governance can spend it"
        : TOLL.to;
    }
    if (command) {
      command.textContent = commandFor(code);
    }
    if (memo) {
      memo.textContent = grouped(code);
    }

    document.querySelectorAll("[data-copy]").forEach(function (button) {
      button.addEventListener("click", function () {
        var value = button.getAttribute("data-copy") === "command" ? commandFor(code) : code;
        if (navigator.clipboard && window.isSecureContext) {
          navigator.clipboard.writeText(value).then(function () {
            button.textContent = "copied";
            window.setTimeout(function () { button.textContent = "copy"; }, 1200);
          });
        }
      });
    });

    if (form) {
      form.addEventListener("submit", function (event) {
        event.preventDefault();
        var value = (hashField && hashField.value ? hashField.value : "").trim().toUpperCase();
        if (!/^[0-9A-F]{64}$/.test(value)) {
          turn("seven");
          say("A transaction hash is 64 hex characters. Your client prints it after the send.");
          return;
        }
        turn(null);
        say("Reading the chain…");
        judge(value);
      });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
