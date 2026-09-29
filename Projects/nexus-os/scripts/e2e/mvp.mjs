// The MVP walkthrough, in a real browser against the real API and web app. Run it with
// `python scripts/e2e.py`, which starts everything on free ports with a fresh data folder.
//
// onboarding (connect a model) → command palette → project → an agent uses tools → approval →
// the demo objective (plan, agents, review, verification, deliverable) → memory → search →
// a workflow built in the editor and run twice → audit-log verification → every page at 1440 px
// and 390 px: no horizontal scrolling, basic accessibility checks, no console errors or failed requests.

import { chromium } from "@playwright/test";
import { existsSync, mkdirSync } from "node:fs";

const WEB = process.env.E2E_WEB;
const API = process.env.E2E_API;
const TOKEN = process.env.E2E_TOKEN;
const MODEL_URL = process.env.E2E_MODEL_URL;
const SHOTS = process.env.E2E_SHOTS ?? "e2e-screenshots";
const SKIPPED = 3;
if (!WEB || !API || !TOKEN || !MODEL_URL) {
  console.error("Run this through `python scripts/e2e.py`.");
  process.exit(1);
}
mkdirSync(SHOTS, { recursive: true });

const H = { authorization: `Bearer ${TOKEN}`, "content-type": "application/json" };
async function api(method, path, body) {
  const r = await fetch(`${API}${path}`, { method, headers: H, body: body === undefined ? undefined : JSON.stringify(body) });
  const text = await r.text();
  return { status: r.status, json: text ? JSON.parse(text) : null };
}

async function launch() {
  const args = typeof process.getuid === "function" && process.getuid() === 0 ? ["--no-sandbox"] : [];
  const candidates = [undefined, process.env.NEXUS_E2E_CHROMIUM, "/opt/pw-browsers/chromium"].filter((c, i) => i === 0 || (c && existsSync(c)));
  let last;
  for (const executablePath of candidates) {
    try {
      return await chromium.launch({ executablePath, args });
    } catch (e) {
      last = e;
    }
  }
  console.log(`No browser could be started: ${String(last?.message ?? last).split("\n")[0]}`);
  process.exit(SKIPPED);
}

const browser = await launch();
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await context.newPage();
page.setDefaultTimeout(20_000);
const problems = [];
page.on("console", (m) => m.type() === "error" && problems.push(`console error: ${m.text()}`));
page.on("pageerror", (e) => problems.push(`page error: ${e.message}`));
page.on("response", (r) => r.status() >= 400 && problems.push(`${r.status()} ${r.request().method()} ${r.url().replace(WEB, "")}`));

let failed = false;
const t0 = Date.now();
async function step(name, fn) {
  const started = Date.now();
  try {
    await fn();
    console.log(`  ✓ ${name} (${((Date.now() - started) / 1000).toFixed(1)}s)`);
  } catch (e) {
    failed = true;
    console.log(`  ✗ ${name}: ${String(e?.message ?? e).split("\n")[0]}`);
    await page.screenshot({ path: `${SHOTS}/failed-${name.replace(/\W+/g, "-")}.png`, fullPage: true }).catch(() => {});
    throw e;
  }
}
function expect(condition, message) {
  if (!condition) throw new Error(message);
}
const shot = (name) => page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: true });

const urls = {};
let projectId;

try {
  await step("0. the accessibility audit catches planted problems", async () => {
    const probe = await context.newPage();
    const pixel = "data:image/gif;base64,R0lGODlhAQABAAAAACw=";
    await probe.setContent(`<main><button></button><input><img src="${pixel}"><p id="d">a</p><p id="d">b</p></main>`);
    const found = await probe.evaluate(auditPage);
    await probe.close();
    const has = (prefix) => found.some((f) => f.startsWith(prefix));
    expect(
      has("control without a name") && has("field without a label") && has("image without alt") && has('id "d"') && has("no h1") && has("no page language"),
      `the audit missed something: ${found.join("; ")}`,
    );
  });

  await step("1. launch and onboarding: connect a model", async () => {
    await page.goto(`${WEB}/`);
    await page.getByRole("heading", { name: "Welcome to NEXUS" }).waitFor();
    await shot("01-welcome");
    await page.getByLabel(/What should NEXUS call you/).fill("E2E");
    await page.getByRole("button", { name: "Get started" }).click();
    await page.getByRole("radio", { name: /Balanced/ }).click();
    await page.getByRole("button", { name: "Continue" }).click();
    await page.getByRole("button", { name: /Connect a provider/ }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByRole("radio", { name: /LM Studio/ }).click();
    await dialog.getByLabel(/Base URL/).fill(MODEL_URL);
    await dialog.getByRole("button", { name: "Connect" }).click();
    const status = page.getByRole("status").filter({ hasText: /connected|test failed/ });
    await status.waitFor({ timeout: 30_000 });
    expect(!(await status.textContent()).includes("test failed"), `connection test failed: ${await status.textContent()}`);
    await page.getByRole("button", { name: "Continue" }).click();
    await page.getByRole("heading", { name: "You're set, E2E" }).waitFor();
    await page.getByRole("button", { name: /Go to the Command Center/ }).click();
    await page.getByRole("button", { name: /Try the demo/ }).waitFor();
    const settings = (await api("GET", "/api/settings")).json;
    expect(settings.onboarding_completed && settings.display_name === "E2E", "onboarding was not saved");
  });

  await step("2. command palette opens a new project", async () => {
    await page.keyboard.press("Control+K");
    await page.getByRole("combobox", { name: /Type a command/ }).fill("new project");
    await page.keyboard.press("Enter");
    await page.waitForURL(/\/projects\?new=1$/);
    const dialog = page.getByRole("dialog");
    await dialog.getByLabel("Name").fill("E2E project");
    await dialog.getByRole("button", { name: "Create project" }).click();
    await page.waitForURL(/\/projects\/proj_/);
    projectId = page.url().split("/").pop().split("?")[0];
    urls.project = `/projects/${projectId}`;
    const put = await api("PUT", `/api/projects/${projectId}/files/content?path=files/old-notes.txt`, { content: "Outdated notes.\n" });
    expect(put.status === 200, `could not write the test file (${put.status})`);
  });

  await step("3. an agent uses tools, and a risky action waits for approval", async () => {
    await page.goto(`${WEB}/agents`);
    const card = page.locator("li", { has: page.getByRole("heading", { name: "File Manager", exact: true }) });
    await card.getByRole("button", { name: "Run", exact: true }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByLabel("Project").selectOption({ label: "E2E project" });
    await dialog.getByLabel("What should it do?").fill("[tidy] Tidy up the outdated notes in files/");
    await dialog.getByRole("button", { name: "Start" }).click();
    await page.waitForURL(/\/runs\/run_/);
    urls.run = page.url().replace(WEB, "");
    await page.getByText("Waiting for your approval").waitFor({ timeout: 30_000 });
    const before = await api("GET", `/api/projects/${projectId}/files/content?path=files/old-notes.txt`);
    expect(before.status === 200, "the file was deleted before approval");
    await shot("03-approval");
    await page.getByRole("button", { name: /Approve once/ }).click();
    await page.getByText("Removed files/old-notes.txt (it is in the project trash).").first().waitFor({ timeout: 30_000 });
    const after = await fetch(`${API}/api/projects/${projectId}/files/content?path=files/old-notes.txt`, { headers: H });
    expect(after.status === 404, "the file still exists after approval");
    const detail = (await api("GET", `/api/runs/${urls.run.split("/").pop()}`)).json;
    const tools = detail.tool_calls.map((c) => `${c.tool_name}:${c.status}`);
    expect(tools.includes("list_directory:SUCCEEDED") && tools.includes("delete_file:SUCCEEDED"), `unexpected tool calls ${tools}`);
    expect(detail.run.status === "COMPLETED", `run ended ${detail.run.status}`);
    // The person can review what happened: the project's tool activity lists both calls.
    await page.goto(`${WEB}${urls.project}?tab=tools`);
    const activity = page.getByRole("list", { name: "Tool calls" });
    await activity.getByText("delete_file", { exact: true }).waitFor();
    await activity.getByText("list_directory", { exact: true }).waitFor();
  });

  await step("4. the demo objective: plan, agents, review, verification, deliverable", async () => {
    await page.goto(`${WEB}/`);
    await page.getByRole("button", { name: /Try the demo/ }).click();
    await page.waitForURL(/\/objectives\/obj_/);
    urls.objective = page.url().replace(WEB, "");
    await page.getByText(/^Plan · \d+ tasks$/).waitFor({ timeout: 30_000 });
    await page.getByRole("button", { name: /^Run plan$/ }).click();
    await page.getByText("Verified", { exact: true }).first().waitFor({ timeout: 120_000 });
    expect((await page.getByLabel("Met").count()) >= 4, "not every completion criterion was met");
    expect((await page.locator(".react-flow__node").count()) >= 6, "the task graph is missing tasks");
    const objective = (await api("GET", `/api/objectives/${urls.objective.split("/").pop()}`)).json;
    const agents = new Set(objective.tasks.map((t) => t.assigned_agent));
    expect(agents.size >= 3, `only ${agents.size} agents worked`);
    await shot("04-objective-verified");
    await page.getByText("Remember this for next time?").waitFor({ timeout: 15_000 });
    await page.getByRole("button", { name: /^Remember$/ }).click();
    await page.getByText("Remember this for next time?").waitFor({ state: "detached" });
    const report = page.getByRole("link", { name: /ai-coding-assistants-comparison\.md/ }).first();
    await report.click();
    await page.getByText("DEMO DATA", { exact: false }).first().waitFor();
    urls.deliverable = page.url().replace(WEB, "");
  });

  await step("5. search finds the deliverable and the remembered outcome", async () => {
    await page.goto(`${WEB}/projects`);
    await page.getByRole("button", { name: /New project/ }).first().waitFor(); // shortcuts attach once the app is up
    await page.keyboard.press("/");
    await page.keyboard.type("coding assistants");
    await page.keyboard.press("Enter");
    await page.waitForURL(/\/search\?q=/);
    await page.getByText(/^Deliverables \(\d+\)$/).waitFor();
    await page.getByText(/^Memory \(\d+\)$/).waitFor();
    urls.search = page.url().replace(WEB, "");
  });

  await step("6. a workflow built in the editor, run twice", async () => {
    await page.keyboard.press("Control+K");
    await page.getByRole("combobox", { name: /Type a command/ }).fill("new workflow");
    await page.keyboard.press("Enter");
    const dialog = page.getByRole("dialog");
    await dialog.getByLabel("Name").fill("Topic note");
    await dialog.getByLabel("Project").selectOption({ label: "E2E project" });
    await dialog.getByRole("button", { name: "Create" }).click();
    await page.waitForURL(/\/workflows\/wf_/);
    urls.workflow = page.url().replace(WEB, "");
    const node = (id) => page.locator(`.react-flow__node[data-id="${id}"]`);
    await node("draft").click();
    await page.getByRole("button", { name: /Remove this step/ }).click();
    await node("result").click();
    await page.getByRole("button", { name: /Remove this step/ }).click();
    await node("start").click();
    await page.getByRole("toolbar", { name: "Add a step" }).getByRole("button", { name: /Output/ }).click();
    await page.getByRole("button", { name: /Add a value/ }).click();
    await page.getByLabel(/Expression for value_1/).fill('"Notes about " + inputs.topic');
    await page.getByText("Ready to run.").waitFor();
    await page.getByRole("button", { name: /^Save$/ }).click();
    await page.getByText("v2").first().waitFor();
    for (const topic of ["tea", "coffee"]) {
      await page.getByRole("button", { name: /^Run$/ }).click();
      await page.getByRole("dialog").getByLabel("topic").fill(topic);
      await page.getByRole("dialog").getByRole("button", { name: "Run" }).click();
      await page.waitForURL(/\/workflow-runs\/wfr_/);
      await page.getByText("Completed", { exact: true }).first().waitFor({ timeout: 30_000 });
      const run = (await api("GET", `/api/workflow-runs/${page.url().split("/").pop()}`)).json.run;
      expect(run.outputs.value_1 === `Notes about ${topic}`, `unexpected outputs ${JSON.stringify(run.outputs)}`);
      urls.workflowRun = page.url().replace(WEB, "");
      await page.getByRole("link", { name: "Topic note" }).click();
      await page.waitForURL(/\/workflows\/wf_/);
    }
    await page.getByRole("tab", { name: "Runs" }).click();
    const runs = page.getByRole("list", { name: "Workflow runs" }).locator("li");
    await runs.nth(1).waitFor();
    expect((await runs.count()) === 2, `expected 2 runs, saw ${await runs.count()}`);
  });

  await step("7. the activity log is intact", async () => {
    await page.goto(`${WEB}/settings/health`);
    await page.getByRole("button", { name: "Verify now" }).click();
    const ok = page.getByRole("status").filter({ hasText: /Verified \d+ events/ });
    await ok.waitFor();
    const events = (await api("GET", "/api/events?limit=1000")).json;
    const types = new Set(events.map((e) => e.type));
    for (const t of ["PROVIDER_CONFIGURED", "PROJECT_CREATED", "APPROVAL_REQUIRED", "TOOL_COMPLETED", "OBJECTIVE_COMPLETED", "WORKFLOW_COMPLETED"]) {
      expect(types.has(t), `no ${t} event recorded`);
    }
  });

  await step("8. keyboard shortcuts", async () => {
    await page.goto(`${WEB}/`);
    await page.getByRole("button", { name: /Try the demo/ }).waitFor();
    await page.locator("body").click({ position: { x: 5, y: 400 } });
    await page.keyboard.press("?");
    await page.getByRole("dialog", { name: "Keyboard shortcuts" }).waitFor();
    await page.keyboard.press("Escape");
    await page.keyboard.press("g");
    await page.keyboard.press("w");
    await page.waitForURL(/\/workflows$/);
  });

  const pages = [
    "/",
    "/projects",
    urls.project,
    `${urls.project}?tab=files`,
    `${urls.project}?tab=tools`,
    "/agents",
    urls.run,
    urls.objective,
    urls.deliverable,
    "/workflows",
    urls.workflow,
    urls.workflowRun,
    "/approvals",
    "/memory",
    urls.search,
    "/settings",
    "/settings/providers",
    "/settings/tools",
    "/settings/integrations",
    "/settings/usage",
    "/settings/health",
  ].filter(Boolean);

  await step(`9. ${pages.length} pages at 1440 and 390 px: layout and accessibility`, async () => {
    const issues = [];
    for (const width of [1440, 390]) {
      await page.setViewportSize({ width, height: width === 390 ? 844 : 900 });
      for (const path of pages) {
        await page.goto(`${WEB}${path}`);
        await page.locator("main").first().waitFor();
        await page.waitForTimeout(700);
        const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
        if (overflow > 1) issues.push(`${width}px ${path}: scrolls sideways by ${overflow}px`);
        for (const p of await page.evaluate(auditPage)) issues.push(`${width}px ${path}: ${p}`);
      }
      await shot(`09-${width}-last-page`);
    }
    expect(issues.length === 0, `\n    ${[...new Set(issues)].join("\n    ")}`);
  });
} catch {
  // the failing step has already been reported
}

const unexpected = [...new Set(problems)];
if (unexpected.length) {
  failed = true;
  console.log(`  ✗ console errors or failed requests:\n    ${unexpected.join("\n    ")}`);
}
await browser.close();
console.log(`${failed ? "E2E FAILED" : "E2E passed"} in ${((Date.now() - t0) / 1000).toFixed(0)}s.`);
process.exit(failed ? 1 : 0);

// ---- a basic accessibility audit, run inside the page ----------------------------------------------
function auditPage() {
  const out = [];
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== "hidden" && s.display !== "none";
  };
  const text = (el) => (el.innerText ?? el.textContent ?? "").trim();
  const describe = (el) => el.outerHTML.replace(/\s+/g, " ").slice(0, 140);
  function labelOf(el, useText) {
    const aria = el.getAttribute("aria-label");
    if (aria && aria.trim()) return aria;
    const by = el.getAttribute("aria-labelledby");
    if (by) {
      const t = by
        .split(/\s+/)
        .map((id) => document.getElementById(id))
        .filter(Boolean)
        .map(text)
        .join(" ");
      if (t) return t;
    }
    if (el.id) {
      const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (l && text(l)) return text(l);
    }
    const wrap = el.closest("label");
    if (wrap && text(wrap)) return text(wrap);
    if (useText && text(el)) return text(el);
    const img = el.querySelector?.("img[alt]");
    if (img?.alt) return img.alt;
    return el.getAttribute("title") ?? "";
  }
  const interactive = 'button, a[href], [role="button"], [role="link"], [role="tab"], [role="switch"], [role="checkbox"], [role="radio"], [role="option"], [role="menuitem"]';
  for (const el of document.querySelectorAll(interactive)) {
    if (visible(el) && !labelOf(el, true)) out.push(`control without a name: ${describe(el)}`);
  }
  for (const el of document.querySelectorAll("input, select, textarea")) {
    if (el.type === "hidden" || !visible(el)) continue;
    if (!labelOf(el, false)) out.push(`field without a label: ${describe(el)}`);
  }
  for (const img of document.querySelectorAll("img")) if (!img.hasAttribute("alt")) out.push(`image without alt text: ${describe(img)}`);
  const ids = new Map();
  for (const el of document.querySelectorAll("[id]")) ids.set(el.id, (ids.get(el.id) ?? 0) + 1);
  for (const [id, n] of ids) if (n > 1) out.push(`id "${id}" is used ${n} times`);
  if (document.querySelectorAll("main").length !== 1) out.push(`${document.querySelectorAll("main").length} main landmarks`);
  if (!document.querySelector("h1")) out.push("no h1 heading");
  if (!document.documentElement.lang) out.push("no page language");
  return out;
}
