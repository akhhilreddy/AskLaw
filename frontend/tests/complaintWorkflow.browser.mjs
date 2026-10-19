// Browser regression without a new package/runtime dependency. The caller supplies
// a Playwright Page and the real offline backend builder. No live account writes.
import assert from "node:assert/strict";

export async function runComplaintWorkflowRegression(page, { fixture, buildPack, width }) {
  let saved = null;
  let failRefresh = false;
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("dialog", (dialog) => dialog.accept());
  await page.route("**/*", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.port === "5173") return route.continue();
    let body = { status: "healthy" };
    let status = 200;
    if (request.method() === "OPTIONS") body = {};
    else if (url.pathname === "/auth/me") body = { _id: "fixture-owner", name: "Fictional browser test", is_guest: false };
    else if (url.pathname === "/complaints/documents") {
      if (failRefresh) { status = 503; body = { detail: "Document library temporarily unavailable" }; }
      else body = fixture.documents;
    } else if (url.pathname === "/complaints/intake") body = fixture.narrativeResult;
    else if (url.pathname === "/complaints/import") body = fixture.pdfResult;
    else if (url.pathname === "/complaints" && request.method() === "GET") body = saved ? [{ case_id: saved.case_id, title: saved.data.title }] : [];
    else if (url.pathname === "/complaints" && request.method() === "POST") {
      saved = { case_id: "a".repeat(24), revision: 1, data: request.postDataJSON() }; body = saved;
    } else if (url.pathname.endsWith("/pack")) body = buildPack(saved.data, fixture.pdfResult.suggestions);
    else if (url.pathname.startsWith("/complaints/") && request.method() === "PUT") {
      saved = { ...saved, revision: saved.revision + 1, data: request.postDataJSON().data }; body = saved;
    } else if (url.pathname.startsWith("/complaints/") && request.method() === "GET") body = saved;
    else if (url.pathname !== "/health") return route.abort();
    return route.fulfill({ status, contentType: "application/json", headers: {
      "access-control-allow-origin": "http://localhost:5173", "access-control-allow-credentials": "true",
      "access-control-allow-headers": "authorization,content-type", "access-control-allow-methods": "GET,POST,PUT,OPTIONS",
    }, body: JSON.stringify(body) });
  });

  await page.goto("http://localhost:5173/complaints");
  await page.getByLabel("Explain the consumer problem", { exact: true }).fill(fixture.narrative);
  await page.getByLabel(/I agree to send this description/).check();
  await page.getByRole("button", { name: "Prepare my complaint", exact: true }).click();
  await page.getByLabel(/I reviewed the selected suggestions/).check();
  await page.getByRole("button", { name: "Apply reviewed suggestions", exact: true }).click();
  await page.getByLabel("Answer missing detail", { exact: true }).fill("Pending name answer");
  await page.getByRole("button", { name: "Refresh lists", exact: true }).click();
  await page.getByRole("button", { name: "Refresh lists", exact: true }).waitFor();
  assert.equal(await page.getByLabel("Answer missing detail", { exact: true }).inputValue(), "Pending name answer");
  assert.equal(await page.getByLabel("Explain the consumer problem", { exact: true }).inputValue(), fixture.narrative);

  failRefresh = true;
  await page.getByRole("button", { name: "Refresh lists", exact: true }).click();
  await page.getByRole("alert").filter({ hasText: "Document library temporarily unavailable" }).waitFor();
  assert.equal(await page.getByLabel("Answer missing detail", { exact: true }).inputValue(), "Pending name answer");
  failRefresh = false;
  await page.getByRole("button", { name: "Refresh lists", exact: true }).click();
  await page.getByRole("button", { name: "Refresh lists", exact: true }).waitFor();
  await page.getByRole("button", { name: "I don't know / skip", exact: true }).click();
  assert.match(await page.getByLabel("Answer missing detail", { exact: true }).locator("..").innerText(), /seller email/);

  await page.getByRole("button", { name: "Save complaint", exact: true }).click();
  await page.getByText("Saved revision 1.", { exact: false }).waitFor();
  assert.equal(await page.getByLabel("Explain the consumer problem", { exact: true }).inputValue(), fixture.narrative);
  assert.match(await page.getByLabel("Answer missing detail", { exact: true }).locator("..").innerText(), /seller email/);

  for (const doc of fixture.documents) await page.getByLabel(doc.filename, { exact: true }).check();
  await page.getByRole("button", { name: "Suggest fields & timeline", exact: true }).click();
  await page.getByText(/12 suggestions/).waitFor();
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
  for (const [index, doc] of fixture.documents.entries()) {
    const group = page.getByRole("group", { name: `Review document: ${doc.filename}`, exact: true });
    const button = group.getByRole("button", { name: "Apply reviewed document", exact: true });
    assert.equal(await button.isDisabled(), true);
    if (index === 1) {
      const mode = group.getByLabel(`Handle description in ${doc.filename}`, { exact: true });
      assert.equal(await mode.inputValue(), "keep");
      await mode.selectOption("combine");
      await group.getByLabel("Combined description", { exact: true }).fill("Reviewed combination preview.");
      await mode.selectOption("keep");
    }
    await group.getByLabel(/I reviewed the selected fields/).check();
    if (index === 0) {
      await page.getByLabel("Seller / company", { exact: true }).fill("Changed after review");
      assert.equal(await button.isDisabled(), true);
      await page.getByLabel("Seller / company", { exact: true }).fill("Sample Electronics");
      await group.getByLabel(/I reviewed the selected fields/).check();
    }
    await button.click();
  }
  assert.equal(await page.getByLabel(/^What went wrong\?/).inputValue(), fixture.narrative);
  assert.equal(await page.locator("form input[type=date]").count(), 5);
  await page.getByLabel(/I checked the names/).check();
  await page.getByRole("button", { name: "Save complaint", exact: true }).click();
  await page.getByText("Saved revision 2.", { exact: false }).waitFor();
  assert.equal(saved.data.events.length, 5);
  assert.equal(saved.data.evidence.length, 10);
  assert.equal(saved.data.description, fixture.narrative);
  assert.equal(saved.data.events.filter((event) => event.evidence_ids.length).length, 4);
  await page.getByRole("button", { name: "Build checklist & draft", exact: true }).click();
  await page.getByLabel("Editable complaint letter", { exact: true }).waitFor();
  assert.match(await page.getByLabel("Editable complaint letter", { exact: true }).inputValue(), /Seller response \(as recorded\)/);
  assert.deepEqual(errors, []);
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
  await page.getByRole("heading", { name: "Start from your PDFs", exact: true }).scrollIntoViewIfNeeded();
  await page.screenshot({ path: `/private/tmp/asklaw-complaint-improvements-${width}.png` });

  // Reverse order: PDFs first, narrative second. Keep the existing source links.
  await page.getByRole("button", { name: "New complaint", exact: true }).click();
  for (const doc of fixture.documents) await page.getByLabel(doc.filename, { exact: true }).check();
  await page.getByRole("button", { name: "Suggest fields & timeline", exact: true }).click();
  await page.getByText(/12 suggestions/).waitFor();
  for (const doc of fixture.documents) {
    const group = page.getByRole("group", { name: `Review document: ${doc.filename}`, exact: true });
    await group.getByLabel(/I reviewed the selected fields/).check();
    await group.getByRole("button", { name: "Apply reviewed document", exact: true }).click();
  }
  assert.equal(await page.locator("form input[type=date]").count(), 4);
  await page.getByLabel("Explain the consumer problem", { exact: true }).fill(fixture.narrative);
  await page.getByLabel(/I agree to send this description/).check();
  await page.getByRole("button", { name: "Prepare my complaint", exact: true }).click();
  await page.getByLabel(/I reviewed the selected suggestions/).check();
  await page.getByRole("button", { name: "Apply reviewed suggestions", exact: true }).click();
  assert.equal(await page.locator("form input[type=date]").count(), 5);
  await page.getByLabel(/I checked the names/).check();
  await page.getByRole("button", { name: "Save complaint", exact: true }).click();
  await page.getByText("Saved revision 1.", { exact: false }).waitFor();
  assert.equal(saved.data.events.length, 5);
  assert.equal(saved.data.events.filter((event) => event.evidence_ids.length).length, 4);
  assert.equal(saved.data.evidence.length, 10);
  return { width, events: saved.data.events.length, source_references: saved.data.evidence.length,
    refresh_and_save_preserved_intake: true, grouped_review: true, narrative_preserved: true, reverse_import_order: true, errors: 0 };
}
