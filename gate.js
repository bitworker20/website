// The coming-soon gate.
//
// The passphrase is never stored here. PBKDF2 stretches it into two halves: one
// the gate compares against (so a wrong guess fails locally, silently, with no
// request that could confirm a near miss), and one that *is* the filename of
// the real page. Nothing here names that page, and nothing links to it — the
// passphrase is the address.
//
// Rotate it with tools/gate.py; see that file for what this does and does not
// protect against.

(function () {
  "use strict";

  /* gate:config */ var CONFIG = {
      "salt": "71651cb87e61df4d993b4a6866fd0dbc",
      "iterations": 250000,
      "length": 12,
      "verifier": "c31f973a89eb8315c4e4edf2e21cb40d",
      "target": "1d191d99475b63e3.html"
  };

  var STORE_KEY = "bitpoker.gate";
  var subtle = window.crypto && window.crypto.subtle;

  function hexToBytes(hex) {
    var out = new Uint8Array(hex.length / 2);
    for (var i = 0; i < out.length; i++) {
      out[i] = parseInt(hex.substr(i * 2, 2), 16);
    }
    return out;
  }

  function bytesToHex(bytes) {
    var out = "";
    for (var i = 0; i < bytes.length; i++) {
      out += (bytes[i] < 16 ? "0" : "") + bytes[i].toString(16);
    }
    return out;
  }

  // Constant-time-ish compare. The attack this matters against is not really
  // available in a browser, but the habit costs nothing.
  function equal(a, b) {
    if (a.length !== b.length) return false;
    var diff = 0;
    for (var i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
    return diff === 0;
  }

  // ── PBKDF2 without WebCrypto ───────────────────────────────────────────────
  //
  // crypto.subtle exists only in a secure context: https, or localhost. Serve
  // this over plain http on a LAN address — which is exactly how someone tests
  // it first — and subtle is undefined, so the gate would silently never open.
  // This is the same derivation in plain JavaScript, sliced across timeouts so
  // the page does not freeze while it runs. Slower, identical output.

  var K = [
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1,
    0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
    0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786,
    0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147,
    0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
    0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b,
    0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a,
    0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
    0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2
  ];

  function rotr(x, n) { return (x >>> n) | (x << (32 - n)); }

  function sha256(bytes) {
    var h = [
      0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
      0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19
    ];
    var length = bytes.length;
    var padded = new Uint8Array((((length + 8) >> 6) + 1) << 6);
    padded.set(bytes);
    padded[length] = 0x80;

    var view = new DataView(padded.buffer);
    view.setUint32(padded.length - 8, Math.floor(length / 0x20000000));
    view.setUint32(padded.length - 4, (length << 3) >>> 0);

    var w = new Uint32Array(64);
    for (var offset = 0; offset < padded.length; offset += 64) {
      var i;
      for (i = 0; i < 16; i++) w[i] = view.getUint32(offset + i * 4);
      for (i = 16; i < 64; i++) {
        var x = w[i - 15];
        var y = w[i - 2];
        var s0 = rotr(x, 7) ^ rotr(x, 18) ^ (x >>> 3);
        var s1 = rotr(y, 17) ^ rotr(y, 19) ^ (y >>> 10);
        w[i] = (w[i - 16] + s0 + w[i - 7] + s1) | 0;
      }

      var a = h[0], b = h[1], c = h[2], d = h[3];
      var e = h[4], f = h[5], g = h[6], hh = h[7];

      for (i = 0; i < 64; i++) {
        var t1 = (hh + (rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25)) +
                  ((e & f) ^ (~e & g)) + K[i] + w[i]) | 0;
        var t2 = ((rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22)) +
                  ((a & b) ^ (a & c) ^ (b & c))) | 0;
        hh = g; g = f; f = e; e = (d + t1) | 0;
        d = c; c = b; b = a; a = (t1 + t2) | 0;
      }

      h[0] = (h[0] + a) | 0; h[1] = (h[1] + b) | 0;
      h[2] = (h[2] + c) | 0; h[3] = (h[3] + d) | 0;
      h[4] = (h[4] + e) | 0; h[5] = (h[5] + f) | 0;
      h[6] = (h[6] + g) | 0; h[7] = (h[7] + hh) | 0;
    }

    var out = new Uint8Array(32);
    var outView = new DataView(out.buffer);
    for (var j = 0; j < 8; j++) outView.setUint32(j * 4, h[j] >>> 0);
    return out;
  }

  // HMAC with the key blocks prepared once: this runs half a million times.
  function hmacWith(keyBytes) {
    var key = keyBytes.length > 64 ? sha256(keyBytes) : keyBytes;
    var inner = new Uint8Array(64 + 32);
    var outer = new Uint8Array(64 + 32);
    for (var i = 0; i < 64; i++) {
      var byte = i < key.length ? key[i] : 0;
      inner[i] = byte ^ 0x36;
      outer[i] = byte ^ 0x5c;
    }
    return function (message) {
      var block = new Uint8Array(64 + message.length);
      block.set(inner.subarray(0, 64));
      block.set(message, 64);
      outer.set(sha256(block), 64);
      return sha256(outer);
    };
  }

  function pbkdf2(passphrase, saltBytes, iterations, length) {
    return new Promise(function (resolve) {
      var prf = hmacWith(new TextEncoder().encode(passphrase));
      var seed = new Uint8Array(saltBytes.length + 4);
      seed.set(saltBytes);
      seed[seed.length - 1] = 1;              // block index 1: 24 bytes fit in one

      var u = prf(seed);
      var t = u.slice();
      var done = 1;

      (function slice() {
        var stop = Math.min(iterations, done + 4000);
        for (; done < stop; done++) {
          u = prf(u);
          for (var i = 0; i < 32; i++) t[i] ^= u[i];
        }
        if (done < iterations) window.setTimeout(slice, 0);
        else resolve(t.subarray(0, length));
      })();
    });
  }

  function derive(passphrase) {
    if (!subtle) {
      return pbkdf2(passphrase, hexToBytes(CONFIG.salt), CONFIG.iterations, 24)
        .then(function (bits) {
          var all = bytesToHex(bits);
          return { verifier: all.slice(0, 32), token: all.slice(32) };
        });
    }

    var bytes = new TextEncoder().encode(passphrase);
    return subtle
      .importKey("raw", bytes, "PBKDF2", false, ["deriveBits"])
      .then(function (key) {
        return subtle.deriveBits(
          {
            name: "PBKDF2",
            salt: hexToBytes(CONFIG.salt),
            iterations: CONFIG.iterations,
            hash: "SHA-256"
          },
          key,
          192
        );
      })
      .then(function (bits) {
        var all = bytesToHex(new Uint8Array(bits));
        return { verifier: all.slice(0, 32), token: all.slice(32) };
      });
  }

  function enter() {
    try {
      window.localStorage.setItem(STORE_KEY, CONFIG.verifier);
    } catch (error) {
      /* private mode: the visit still works, it just will not be remembered */
    }
    window.location.replace(CONFIG.target);
  }

  function attempt(passphrase) {
    if (!CONFIG.verifier) return Promise.resolve(false);
    return derive(passphrase).then(function (derived) {
      if (!equal(derived.verifier, CONFIG.verifier)) return false;
      enter();
      return true;
    });
  }

  // A browser that has been through the gate before goes straight in.
  try {
    if (window.localStorage.getItem(STORE_KEY) === CONFIG.verifier && CONFIG.verifier) {
      window.location.replace(CONFIG.target);
      return;
    }
  } catch (error) {
    /* storage blocked — fall through to the knock */
  }

  document.addEventListener("DOMContentLoaded", function () {
    var mark = document.querySelector("[data-knock]");
    var field = document.querySelector("[data-knock-field]");
    var busy = false;

    // One PBKDF2 run takes long enough that a fast typist can finish the
    // passphrase while the previous keystroke is still being checked. Dropping
    // those would mean the correct suffix is never tested, so the newest
    // candidate waits its turn instead.
    var pending = null;

    function tryPassphrase(value) {
      if (!value) return;
      if (busy) {
        pending = value;
        return;
      }
      busy = true;
      attempt(value).then(
        function (ok) {
          busy = false;
          if (!ok && field) {
            // No message: a failure and an idle page look the same.
            field.value = "";
          }
          var next = pending;
          pending = null;
          if (!ok && next && next !== value) tryPassphrase(next);
        },
        function () {
          busy = false;
          pending = null;
        }
      );
    }

    // A link can carry it: /#passphrase — handy for sending someone in.
    if (window.location.hash.length > 1) {
      var fromHash = decodeURIComponent(window.location.hash.slice(1));
      if (window.history && window.history.replaceState) {
        window.history.replaceState(null, "", window.location.pathname);
      }
      tryPassphrase(fromHash);
    }

    // On a keyboard: just type it. Nothing echoes, nothing is focused.
    var buffer = "";
    document.addEventListener("keydown", function (event) {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (document.activeElement === field) return;
      if (event.key.length !== 1) return;
      buffer = (buffer + event.key).slice(-64);
      if (CONFIG.length && buffer.length >= CONFIG.length) {
        tryPassphrase(buffer.slice(-CONFIG.length));
      }
    });

    // On a phone there is no keyboard to type into, so five taps on the mark
    // bring up a field. Five, because nobody taps a logo five times by accident.
    if (mark && field) {
      var taps = 0;
      var timer = null;
      mark.addEventListener("click", function () {
        taps += 1;
        window.clearTimeout(timer);
        timer = window.setTimeout(function () { taps = 0; }, 2000);
        if (taps >= 5) {
          taps = 0;
          field.hidden = false;
          field.focus();
        }
      });

      field.addEventListener("keydown", function (event) {
        if (event.key === "Enter") {
          event.preventDefault();
          tryPassphrase(field.value.trim());
        }
      });
    }
  });
})();
