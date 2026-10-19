import test from "node:test";
import assert from "node:assert/strict";
import { checkServerReadiness } from "../src/services/serverReadiness.js";

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
