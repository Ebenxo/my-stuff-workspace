// The browser preview, in a real browser: the built page inside the same document skeleton claude.ai
// gives it, with a stand-in for the claude.ai runtime (private storage, a user id, and Claude as
// `sample`, answering from a script). Run it with `python scripts/build_preview.py --check`.
//
// banner → the demo objective (plan, run, review, verification, deliverable, memory suggestion) →
// an agent run with a question and an answer → memory → a workflow from the starter, run →
// reload: everything is still there → a page without the runtime says no model is available →
// phone width. Fails on any console error.

import { chromium } from "@playwright/test";
import { existsSync, mkdirSync, readFileSync } from "node:fs";
import { createServer } from "node:http";

const PAGE = process.argv[2];
const SHOTS = process.env.PREVIEW_SHOTS ?? "preview-screenshots";
const SKIPPED = 3;
if (!PAGE || !existsSync(PAGE)) {
  console.error("Usage: node scripts/e2e/preview.mjs <nexus-os-preview.html> (or `python scripts/build_preview.py --check`)");
  process.exit(1);
}
mkdirSync(SHOTS, { recursive: true });

// The skeleton the Artifact host wraps page content in (see the Artifact tool's publish contract).
const SKELETON =
  '<!doctype html><html><head><meta charset=utf8><meta name=viewport content="width=device-width,initial-scale=1,viewport-fit=cover">' +
  "<style>:root{color-scheme:light;padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}" +
  "body{margin:0;font:14px system-ui,sans-serif;background:#fafaf7}img{max-width:100%}[hidden]{display:none!important}</style></head><body>";
const html = SKELETON + readFileSync(PAGE, "utf8") + "</body></html>";
const server = createServer((req, res) => {
  res.writeHead(200, { "content-type": "text/html; charset=utf-8" });
  res.end(req.url === "/favicon.ico" ? "" : html);
});
await new Promise((r) => server.listen(0, "127.0.0.1", r));
const ORIGIN = `http://127.0.0.1:${server.address().port}`;

// The stand-in runtime. Storage lives in localStorage under its own key, so a reload finds it again.
function runtime() {
  const KEY = "__standin_db__";
  const read = () => JSON.parse(localStorage.getItem(KEY) ?? "{}");
  const write = (all) => localStorage.setItem(KEY, JSON.stringify(all));
  const collection = (path) => ({
    doc: (id) => ({
      set: async (data) => {
        const all = read();
        all[`${path}/${id}`] = data;
        write(all);
      },
      delete: async () => {
        const all = read();
        delete all[`${path}/${id}`];
        write(all);
      },
    }),
    get: async () => ({
      docs: Object.entries(read())
        .filter(([k]) => k.startsWith(`${path}/`))
        .map(([k, v]) => ({ id: k.slice(path.length + 1), exists: true, data: () => v })),
    }),
  });
  const role = (p) =>
    p.startsWith("You are the Planner")
      ? "planner"
      : p.startsWith("You are the Critic")
        ? "critic"
        : p.startsWith("You are the Verifier")
          ? "verifier"
          : "agent";
  let asked = false;
  const answer = (p) => {
    window.__prompts = [...(window.__prompts ?? []), p];
    switch (role(p)) {
      case "planner":
        return {
          objective: "Compare three fictional AI coding assistants and save a sourced report.",
          assumptions: ["The three notes in files/notes/ are the sources."],
          risks: ["The notes may be incomplete."],
          completion_criteria: ["A comparison report is saved", "It covers all three assistants"],
          tasks: [
            { key: "t1", title: "Extract the facts", description: "Price, features and limits per note.", agent: "researcher" },
            {
              key: "t2",
              title: "Write the comparison report",
              description: "Tables and a recommendation.",
              agent: "writer",
              depends_on: ["t1"],
              review: true,
            },
          ],
        };
      case "critic":
        return { verdict: "approve", summary: "Accurate and sourced.", issues: [] };
      case "verifier":
        return {
          verdict: "PASS",
          summary: "The report covers all three assistants with sources.",
          criteria: [
            { criterion: "A comparison report is saved", met: true, evidence: "artifacts/comparison.md" },
            { criterion: "It covers all three assistants", met: true, evidence: "Both tables" },
          ],
          missing_requirements: [],
        };
      default:
        if (p.includes("This task: Extract the facts"))
          return "SUMMARY: Listed price, features and limits for all three.\nFILE: NONE\n\nAlpha Code $10, Beta Pair $19, Gamma Dev $15.";
        if (p.includes("This task: Write the comparison report"))
          return "SUMMARY: Wrote the comparison.\nFILE: comparison.md\n\n# Comparison (demo data)\n\n| Assistant | Price |\n|---|---|\n| Alpha Code | $10 |";
        if (p.includes("haiku") && !asked) {
          asked = true;
          return "SUMMARY: Need one detail.\nQUESTION: Green tea or black tea?\nOPTIONS: Green | Black";
        }
        if (p.includes("haiku")) return "SUMMARY: Wrote a haiku about green tea.\nFILE: tea-haiku.md\n\n# Tea\n\nSteam over the cup";
        return "SUMMARY: Wrote a short brief.\nFILE: NONE\n\nA short brief about the topic.";
    }
  };
  const later = (v) => new Promise((r) => setTimeout(() => r(v), 30));
  const sample = async (input) => {
    const a = answer(input);
    return later({ text: typeof a === "string" ? a : JSON.stringify(a), truncated: false });
  };
  sample.json = async (input) => later(answer(input));
  const caps = { db: { collection }, user: { id: async () => "user_standin" }, sample };
  window.claude = { use: async (name) => caps[name] ?? null };
}

async function launch() {
  const args = typeof process.getuid === "function" && process.getuid() === 0 ? ["--no-sandbox"] : [];
  const candidates = [undefined, process.env.NEXUS_E2E_CHROMIUM, "/opt/pw-browsers/chromium"].filter(
    (c, i) => i === 0 || (c && existsSync(c)),
  );
  for (const executablePath of candidates) {
    try {
      return await chromium.launch({ executablePath, args });
    } catch {
      // try the next one
    }
  }
  console.log("No browser could be started.");
  process.exit(SKIPPED);
}

const browser = await launch();
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
await context.addInitScript(runtime);
const page = await context.newPage();
page.setDefaultTimeout(20_000);
const problems = [];
const watch = (p) => {
  p.on("console", (m) => m.type() === "error" && problems.push(`console error: ${m.text()}`));
  p.on("pageerror", (e) => problems.push(`page error: ${e.message}`));
};
watch(page);

let failed = false;
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
const expect = (ok, message) => {
  if (!ok) throw new Error(message);
};
const shot = (name) => page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: true });
const go = (hash) => page.goto(`${ORIGIN}/#${hash}`);

try {
  await step("1. the page opens and says Claude is the model", async () => {
    await go("/");
    await page
      .getByRole("note")
      .filter({ hasText: "Browser preview." })
      .getByText(/Claude, on your own claude\.ai account, is the model/)
      .waitFor();
    await page.getByRole("note").getByText("Saved to your Claude account; only you can see it.").waitFor();
    await shot("01-home");
  });

  await step("2. the demo objective: plan, run, review, verification, deliverable", async () => {
    await page.getByRole("button", { name: /Try the demo/ }).click();
    await page.waitForURL(/#\/objectives\/obj_/);
    await page.getByText(/^Plan · 2 tasks$/).waitFor({ timeout: 30_000 });
    await shot("02-plan");
    await page.getByRole("button", { name: /^Run plan$/ }).click();
    await page.getByText("Verified", { exact: true }).first().waitFor({ timeout: 60_000 });
    expect((await page.getByLabel("Met").count()) === 2, "not every completion criterion was met");
    expect((await page.locator(".react-flow__node").count()) >= 4, "the task graph is missing the review or verification");
    const prompts = await page.evaluate(() => window.__prompts);
    expect(
      prompts.some((p) => p.includes("DEMO DATA") && p.includes("files/notes/alpha-code.md")),
      "the agents did not see the demo notes",
    );
    await page.getByText("Remember this for next time?").waitFor();
    await shot("03-objective-verified");
    await page.getByRole("button", { name: /^Remember$/ }).click();
    await page.getByText("Remember this for next time?").waitFor({ state: "detached" });
    await page
      .getByRole("link", { name: /comparison\.md/ })
      .first()
      .click();
    await page.getByText("Comparison (demo data)").first().waitFor();
  });

  await step("3. an agent asks a question, gets an answer and saves its work", async () => {
    await go("/agents");
    const card = page.locator("li", { has: page.getByRole("heading", { name: "Writer", exact: true }) });
    await card.getByRole("button", { name: "Run", exact: true }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByLabel("What should it do?").fill("Write a haiku about tea");
    await dialog.getByRole("button", { name: "Start" }).click();
    await page.waitForURL(/#\/runs\/run_/);
    await page.getByText("Green tea or black tea?").first().waitFor({ timeout: 30_000 });
    await page.getByRole("button", { name: "Green", exact: true }).click();
    await page.getByText("Completed", { exact: true }).first().waitFor({ timeout: 30_000 });
    await page.getByText("Wrote a haiku about green tea.").first().waitFor();
    await shot("04-agent-run");
  });

  await step("4. memory: remember something and find it", async () => {
    await go("/memory");
    await page.getByRole("button", { name: /Add a memory/ }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByLabel("What should be remembered?").fill("Prefer British spelling in reports.");
    await dialog.getByRole("button", { name: "Remember", exact: true }).click();
    await page.getByText("Prefer British spelling in reports.").first().waitFor();
    await shot("05-memory");
  });

  await step("5. a workflow from the starter, run with Claude", async () => {
    await page.keyboard.press("Control+K");
    await page.getByRole("combobox", { name: /Type a command/ }).fill("new workflow");
    await page.keyboard.press("Enter");
    const dialog = page.getByRole("dialog");
    await dialog.getByLabel("Name").fill("Brief");
    await dialog.getByRole("button", { name: "Create" }).click();
    await page.waitForURL(/#\/workflows\/wf_/);
    await page.getByText("Ready to run.").waitFor();
    await page.getByRole("button", { name: /^Run$/ }).click();
    await page.getByRole("dialog").getByLabel("topic").fill("herb gardens");
    await page.getByRole("dialog").getByRole("button", { name: "Run" }).click();
    await page.waitForURL(/#\/workflow-runs\/wfr_/);
    await page.getByText("Completed", { exact: true }).first().waitFor({ timeout: 30_000 });
    await shot("06-workflow-run");
  });

  await step("6. after a reload everything is still there", async () => {
    await go("/timeline");
    await page.reload();
    await page.getByRole("heading", { name: "Timeline" }).first().waitFor();
    await go("/projects");
    await page.getByText("Demo: AI coding assistants").first().waitFor();
    await go("/memory");
    await page.getByText("Prefer British spelling in reports.").first().waitFor();
    await go("/workflows");
    await page.getByText("Brief", { exact: true }).first().waitFor();
    await shot("07-timeline-after-reload");
  });

  await step("7. without the claude.ai runtime the page says no model is available", async () => {
    const bare = await browser.newContext({ viewport: { width: 1280, height: 800 } });
    const p = await bare.newPage();
    watch(p);
    await p.goto(`${ORIGIN}/#/`);
    await p
      .getByRole("note")
      .getByText(/No model is available in this view/)
      .waitFor();
    await p.getByRole("note").getByText("Saved in this browser.").waitFor();
    await bare.close();
  });

  await step("8. phone width: no sideways scrolling", async () => {
    await page.setViewportSize({ width: 390, height: 844 });
    for (const hash of ["/", "/timeline", "/agents", "/memory", "/workflows"]) {
      await go(hash);
      await page.waitForTimeout(300);
      const wide = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(wide <= 1, `${hash} scrolls sideways by ${wide}px at 390 px`);
    }
    await shot("08-phone");
  });

  await step("9. no console errors", async () => {
    expect(problems.length === 0, problems.slice(0, 5).join("; "));
  });
} catch {
  // reported by step()
} finally {
  await browser.close();
  server.close();
}
console.log(failed ? "\nPreview check FAILED" : `\nPreview check passed. Screenshots in ${SHOTS}/`);
process.exit(failed ? 1 : 0);
