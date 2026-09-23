import test from "node:test";
import assert from "node:assert/strict";

import { normalizeSignupError } from "../src/services/authError.js";

test("preserves a plain backend detail string", () => {
  const message = normalizeSignupError({
    response: { data: { detail: "Email already exists" } },
  });

  assert.equal(message, "Email already exists");
});

test("turns a missing email validation error into a readable message", () => {
  const message = normalizeSignupError({
    response: {
      data: {
        detail: [
          { loc: ["body", "email"], msg: "Field required", type: "missing" },
        ],
      },
    },
  });

  assert.equal(message, "Email is required.");
});

test("turns a missing password validation error into a readable message", () => {
  const message = normalizeSignupError({
    response: {
      data: {
        detail: [
          {
            loc: ["body", "password"],
            msg: "Field required",
            type: "missing",
          },
        ],
      },
    },
  });

  assert.equal(message, "Password is required.");
});

test("turns the backend email validation response into a concise message", () => {
  const message = normalizeSignupError({
    response: {
      data: {
        detail: [
          {
            loc: ["body", "email"],
            msg: "value is not a valid email address: An email address must have an @-sign.",
            type: "value_error",
          },
        ],
      },
    },
  });

  assert.equal(message, "Email must be a valid email address.");
});

test("keeps multiple validation messages on separate lines", () => {
  const message = normalizeSignupError({
    response: {
      data: {
        detail: [
          { loc: ["body", "email"], msg: "Field required", type: "missing" },
          {
            loc: ["body", "password"],
            msg: "Field required",
            type: "missing",
          },
        ],
      },
    },
  });

  assert.equal(message, "Email is required.\nPassword is required.");
});

test("reads a message from a generic detail object", () => {
  const message = normalizeSignupError({
    response: { data: { detail: { message: "Registration is unavailable" } } },
  });

  assert.equal(message, "Registration is unavailable.");
});

test("handles a network error without a response", () => {
  const message = normalizeSignupError({
    code: "ERR_NETWORK",
    message: "Network Error",
    request: {},
  });

  assert.equal(
    message,
    "Unable to reach the server. Please check your connection and try again.",
  );
});

test("uses the safe fallback when a backend response has no detail", () => {
  const message = normalizeSignupError({ response: { data: {} } });

  assert.equal(message, "Signup failed. Please try again.");
});

test("always returns renderable text for unusual values", () => {
  const values = [
    null,
    undefined,
    {},
    [],
    { response: { data: { detail: [{ unexpected: { nested: true } }] } } },
  ];

  for (const value of values) {
    assert.equal(typeof normalizeSignupError(value), "string");
    assert.ok(normalizeSignupError(value).length > 0);
  }
});

