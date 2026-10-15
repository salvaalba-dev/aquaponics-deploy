"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(
  path.join(__dirname, "../proposals/notebooklm-wake.candidate.js"), "utf8");
const binding = Object.freeze({chrome_service: "chrome-alma", cdp_port: 18802});

function harness({uid = 1059, failure = false, health = {ok: true}, noGetuid = false} = {}) {
  const calls = [];
  const context = vm.createContext({
    process: noGetuid ? {} : {getuid: () => uid},
    checkChrome: async (port) => {
      calls.push({operation: "health", port});
      return health;
    },
    require: (name) => {
      assert.equal(name, "node:child_process");
      return {execFileSync: (program, argv, options) => {
        calls.push({operation: "start", program,
          argv: Array.from(argv), options: {...options}});
        if (failure) throw new Error("private subprocess diagnostic");
      }};
    },
  });
  vm.runInContext(source, context);
  return {calls, wake: context.wakeAndCheck};
}

test("uses a fixed generic client argv before probing the approved browser", async () => {
  const h = harness();
  assert.equal((await h.wake(binding)).ok, true);
  assert.deepEqual(h.calls, [
    {operation: "start", program: "/usr/bin/python3",
      argv: ["-I", "/usr/local/libexec/persona_service_control.py", "client",
        "--config", "/etc/persona-service-control/alma-browser.json"],
      options: {timeout: 40000, stdio: "ignore"}},
    {operation: "health", port: 18802},
  ]);
});

test("an already healthy browser still requires the root-managed control path", async () => {
  const health = {ok: true, chromeVersion: "fake"};
  const h = harness({health});
  assert.equal(await h.wake(binding), health);
  assert.equal(h.calls[0].operation, "start");
  assert.equal(h.calls.filter(c => c.operation === "start").length, 1);
});

test("controller failure neither probes Chrome nor leaks diagnostics or uses sudo", async () => {
  const h = harness({failure: true});
  const result = await h.wake(binding);
  assert.equal(result.ok, false);
  assert.equal(result.error, "SERVICE_CONTROL_UNAVAILABLE");
  assert.equal(h.calls.length, 1);
  assert.equal(h.calls[0].program, "/usr/bin/python3");
});

test("rejects another mapping before any service call or localhost probe", async () => {
  for (const cfg of [null, {}, {...binding, chrome_service: "chrome-paco"},
    {...binding, cdp_port: 18803}, {...binding, cdp_port: "18802"}]) {
    const h = harness();
    assert.equal((await h.wake(cfg)).error, "UNEXPECTED_BROWSER_BINDING");
    assert.deepEqual(h.calls, []);
  }
});

test("rejects another UID, root execution or an unsupported platform", async () => {
  for (const options of [{uid: 0}, {uid: 1060}, {noGetuid: true}]) {
    const h = harness(options);
    assert.equal((await h.wake(binding)).error, "UNEXPECTED_BROWSER_BINDING");
    assert.deepEqual(h.calls, []);
  }
});

test("a successful start does not manufacture browser health or query approval", async () => {
  const health = {ok: false, error: "fake browser down"};
  const h = harness({health});
  assert.equal(await h.wake(binding), health);
  assert.equal(h.calls.length, 2);
});
