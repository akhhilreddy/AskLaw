import test from "node:test";
import assert from "node:assert/strict";
import { applyResearchEvent, emptyResearchStatus, conversationHistory, noticeText, finishResearchMessages } from "../src/components/dashboard/researchStatus.js";

test("cold-start progress appears and survives heartbeat, then clears on readiness", () => {
  let state = applyResearchEvent(emptyResearchStatus(), { type: "progress", code: "web_waking" });
  assert.equal(state.progress, "Waking up web search…");
  state = applyResearchEvent(state, { type: "progress", code: "research_pending" });
  assert.equal(state.progress, "Waking up web search…");
  assert.equal(applyResearchEvent(state, { type: "progress", code: "web_ready" }).progress, "");
});

test("provider waits use allowlisted UI text and clear when answer starts", () => {
  let state = applyResearchEvent(emptyResearchStatus(), { type: "progress", code: "provider_pending", message: "private provider error" });
  assert.equal(state.progress, "Preparing your answer…");
  state = applyResearchEvent(state, { type: "progress", code: "provider_retrying" });
  assert.equal(state.progress, "AI service is busy; waiting to retry…");
  assert.equal(applyResearchEvent(state, { type: "token", content: "answer" }).progress, "");
  assert.equal(applyResearchEvent(state, { type: "error" }).progress, "");
  assert.equal(applyResearchEvent(state, { type: "stop" }).progress, "");
  assert.equal(applyResearchEvent(state, { type: "progress", code: "unknown", message: "secret" }).progress, state.progress);
});

test("outage differs from empty results and provider-controlled text is discarded", () => {
  const state = applyResearchEvent(emptyResearchStatus(), { type: "availability", notices: [
    { type: "web_unavailable", url: "https://private-provider?q=secret", message: "private body" },
    { type: "unknown", message: "fake outage" },
  ], receipt: "signed-proof", availability_only: true });
  assert.deepEqual(state.availability_notices, [{ type: "web_unavailable" }]);
  assert.match(noticeText(state.availability_notices[0]), /temporarily unavailable/);
  assert.deepEqual(emptyResearchStatus().availability_notices, []);
  assert.equal(state.availability_receipt, "signed-proof");
  assert.equal(noticeText({ type: "unknown", message: "fake" }), "");
});

test("notices, receipts and availability-only messages never enter later chat history", () => {
  const history = conversationHistory([
    { role: "user", content: "question" },
    { role: "assistant", content: "Web search unavailable", availability_only: true },
    { role: "assistant", content: "Supported document answer", availability_notices: [{ type: "web_unavailable" }], availability_receipt: "proof" },
    { role: "assistant", content: "", progress: "waking" },
  ]);
  assert.deepEqual(history, [{ role: "user", content: "question" }, { role: "assistant", content: "Supported document answer" }]);
});

test("token, error, completion and Stop clear progress without dropping notices", () => {
  const state = { ...emptyResearchStatus(), progress: "Waking up web search…", availability_notices: [{ type: "web_unavailable" }] };
  for (const type of ["token", "error", "done", "stop"]) {
    const next = applyResearchEvent(state, { type });
    assert.equal(next.progress, "");
    assert.deepEqual(next.availability_notices, state.availability_notices);
  }
  const messages = finishResearchMessages([
    { role: "assistant", content: "", progress: "waking" },
    { role: "assistant", content: "partial answer", progress: "researching", isComplete: false },
  ]);
  assert.equal(messages.length, 1);
  assert.equal(messages[0].progress, "");
  assert.equal(messages[0].isComplete, true);
});
