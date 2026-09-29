import test from "node:test";
import assert from "node:assert/strict";

import { isResearchRoute } from "../src/components/dashboard/chatPresentation.js";

test("recognizes only evidence-producing research routes", () => {
  assert.equal(isResearchRoute("rag"), true);
  assert.equal(isResearchRoute("web"), true);
  assert.equal(isResearchRoute("hybrid"), true);
  assert.equal(isResearchRoute("conversation"), false);
  assert.equal(isResearchRoute(null), false);
});
