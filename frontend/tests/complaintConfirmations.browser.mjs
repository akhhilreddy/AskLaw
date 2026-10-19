import assert from "node:assert/strict";
import { emptyComplaint } from "../src/services/complaintPack.js";

// Caller supplies an isolated Playwright Page. All API responses are fictional.
export async function runComplaintConfirmationRegression(page, { width }) {
  const errors = [];
  const dialogs = [];
  let deletes = 0;
  let reads = 0;
  const caseId = "a".repeat(24);
  const saved = { case_id: caseId, revision: 1, data: { ...emptyComplaint(), title: "Saved fictional complaint", product: "Saved laptop" } };
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("dialog", async (dialog) => { dialogs.push(dialog.type()); await dialog.dismiss(); });
  await page.route("**/*", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.port === "5173") return route.continue();
    let body = { status: "healthy" };
    if (request.method() === "OPTIONS") body = {};
    else if (url.pathname === "/auth/me") body = { _id: "fixture-owner", name: "Fictional test", is_guest: false };
    else if (url.pathname === "/complaints/documents") body = [];
    else if (url.pathname === "/complaints" && request.method() === "GET") body = deletes ? [] : [{ case_id: caseId, title: saved.data.title }];
    else if (url.pathname === "/complaints/intake") body = { supported: true, suggestions: [{ suggestion_id: "product", field: "product", value: "Suggested laptop", quote: "Suggested laptop", origin: "user_report" }] };
    else if (url.pathname === `/complaints/${caseId}` && request.method() === "GET") { reads++; body = saved; }
    else if (url.pathname === `/complaints/${caseId}` && request.method() === "DELETE") { deletes++; body = { deleted: true }; }
    else if (url.pathname !== "/health") return route.abort();
    return route.fulfill({ contentType: "application/json", headers: {
      "access-control-allow-origin": "http://localhost:5173", "access-control-allow-credentials": "true",
      "access-control-allow-headers": "authorization,content-type", "access-control-allow-methods": "GET,POST,DELETE,OPTIONS",
    }, body: JSON.stringify(body) });
  });
  const button = (name) => page.getByRole("button", { name, exact: true });
  const product = page.getByLabel("Product", { exact: true });
  const review = page.getByLabel(/I reviewed the selected suggestions/);
  const replacement = page.getByRole("region", { name: "Replace existing complaint values?", exact: true });
  await page.goto("http://localhost:5173/complaints");
  await product.fill("Original laptop");
  await page.getByLabel("Explain the consumer problem", { exact: true }).fill("Suggested laptop arrived broken.");
  await page.getByLabel(/I agree to send this description/).check();
  await button("Prepare my complaint").click();
  await review.check();
  await button("Apply reviewed suggestions").click();
  await replacement.waitFor();
  assert.match(await replacement.innerText(), /Current: Original laptop/);
  assert.match(await replacement.innerText(), /Suggested: Suggested laptop/);
  await page.screenshot({ path: `/private/tmp/asklaw-inline-confirmation-${width}.png` });
  assert.equal(await replacement.getByRole("button", { name: "Cancel", exact: true }).evaluate((element) => element === document.activeElement), true);
  await replacement.getByRole("button", { name: "Cancel", exact: true }).click();
  assert.equal(await product.inputValue(), "Original laptop");
  await button("Apply reviewed suggestions").click();
  await product.fill("Changed after review");
  assert.equal(await replacement.count(), 0);
  assert.equal(await button("Apply reviewed suggestions").isDisabled(), true);
  await review.check();
  await button("Apply reviewed suggestions").click();
  await replacement.getByRole("button", { name: "Replace values and apply", exact: true }).click();
  assert.equal(await product.inputValue(), "Suggested laptop");
  assert.equal(await page.getByLabel(/I checked the names/).isChecked(), false);
  assert.equal(reads, 0); // Applying suggestions does not save or open a record.

  await button("New complaint").click();
  const discard = page.getByRole("region", { name: "Discard unsaved edits?", exact: true });
  await discard.getByRole("button", { name: "Cancel", exact: true }).click();
  assert.equal(await product.inputValue(), "Suggested laptop");
  await button("New complaint").click();
  await button("Discard edits and start new").click();
  assert.equal(await product.inputValue(), "");

  await button(saved.data.title).click();
  await page.getByText(/Saved revision 1\./).waitFor();
  await product.fill("Unsaved edit");
  await button(saved.data.title).click();
  await discard.getByRole("button", { name: "Cancel", exact: true }).click();
  assert.equal(await product.inputValue(), "Unsaved edit");
  assert.equal(reads, 1);
  await button(saved.data.title).click();
  await button("Discard edits and open complaint").click();
  await page.getByText(/Saved revision 1\./).waitFor();
  assert.equal(await product.inputValue(), "Saved laptop");
  assert.equal(reads, 2);

  await button("Delete complaint").click();
  const deletion = page.getByRole("region", { name: "Delete this complaint?", exact: true });
  assert.match(await deletion.innerText(), /uploaded PDFs will be kept/);
  await deletion.getByRole("button", { name: "Cancel", exact: true }).click();
  assert.equal(deletes, 0);
  await button("Delete complaint").click();
  await product.fill("Changed before deletion");
  assert.equal(await deletion.count(), 0);
  assert.equal(deletes, 0);
  await button("Delete complaint").click();
  await button("Delete saved complaint").click();
  await page.getByText(/Not saved yet\./).waitFor();
  assert.equal(deletes, 1);
  assert.equal(await product.inputValue(), "");
  assert.deepEqual(dialogs, []);
  assert.deepEqual(errors, []);
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
  return { width, replacement: "pass", discard: "pass", open: "pass", delete: "pass", stale_confirmation: "pass", native_dialogs: dialogs.length, errors: errors.length };
}
