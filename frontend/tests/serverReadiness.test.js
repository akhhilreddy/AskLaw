import test from "node:test";
import assert from "node:assert/strict";
import { checkServerReadiness, READINESS_TIMEOUT_MS } from "../src/services/serverReadiness.js";

const healthy = { ok: true, json: async () => ({ status: "healthy" }) };

test("fast health check does not show waking message or send credentials", async () => {
  let slow = false;
  await checkServerReadiness("https://api.example", {
    onSlow: () => { slow = true; },
    fetcher: async (url, options) => {
      assert.equal(url, "https://api.example/health");
      assert.equal(options.credentials, "omit");
      return healthy;
    },
  });
  assert.equal(slow, false);
});

test("pending health check shows waking message then succeeds", async () => {
  let slow = false;
  await checkServerReadiness("https://api.example", {
    delay: 1, onSlow: () => { slow = true; },
    fetcher: () => new Promise(resolve => setTimeout(() => resolve(healthy), 15)),
  });
  assert.equal(slow, true);
});

test("unhealthy response and disconnect are errors, not false readiness", async () => {
  for (const fetcher of [async () => ({ ok: false }), async () => { throw new Error("offline"); }]) {
    await assert.rejects(checkServerReadiness("https://api.example", { onSlow: () => {}, fetcher }));
  }
});

const untilAborted = (_url, { signal }) => new Promise((_resolve, reject) => {
  if (signal.aborted) reject(new Error("aborted"));
  else signal.addEventListener("abort", () => reject(new Error("aborted")), { once: true });
});

test("73-second cold start succeeds within the 100-second budget", async t => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  let slow = false;
  let probeSignal;
  const pending = checkServerReadiness("https://api.example", {
    onSlow: () => { slow = true; },
    fetcher: (_url, { signal }) => {
      probeSignal = signal;
      return new Promise(resolve => setTimeout(() => resolve(healthy), 73000));
    },
  });
  t.mock.timers.tick(65000);
  assert.equal(slow, true);
  assert.equal(probeSignal.aborted, false);
  t.mock.timers.tick(8000);
  await pending;
  t.mock.timers.tick(100000);
  assert.equal(probeSignal.aborted, false, "successful probe clears deadline");
});

test("health check aborts at 100 seconds and a fresh retry can succeed", async t => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  assert.equal(READINESS_TIMEOUT_MS, 100000);
  const pending = checkServerReadiness("https://api.example", { onSlow: () => {}, fetcher: untilAborted });
  const rejected = assert.rejects(pending, /aborted/);
  t.mock.timers.tick(100000);
  await rejected;
  await checkServerReadiness("https://api.example", { onSlow: () => {}, fetcher: async () => healthy });
});

test("unmount abort cancels the probe and clears the waking timer", async t => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const controller = new AbortController();
  let slow = false;
  const pending = checkServerReadiness("https://api.example", {
    signal: controller.signal, onSlow: () => { slow = true; }, fetcher: untilAborted,
  });
  const rejected = assert.rejects(pending, /aborted/);
  controller.abort();
  await rejected;
  t.mock.timers.tick(100000);
  assert.equal(slow, false);
});
