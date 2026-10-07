import type { McpServer } from "@nexus/schemas";
import { describe, expect, it } from "vitest";
import { EMPTY_FORM, argsFromText, countLine, launchLine, toCreate, toForm, toUpdate, validateForm, type ServerForm } from "./model";

const server: McpServer = {
  id: "mcp_1",
  name: "github",
  description: "",
  transport: "stdio",
  command: "npx",
  args: ["-y", "@modelcontextprotocol/server-github"],
  cwd: null,
  env: { LOG_LEVEL: "info" },
  url: "",
  headers: {},
  secret_env: ["GITHUB_TOKEN"],
  secret_headers: [],
  risk_level: "HIGH",
  timeout_s: 60,
  enabled: true,
  status: "running",
  tools: 12,
  resources: 1,
  prompts: 0,
  created_at: "2026-09-29T10:00:00Z",
  updated_at: "2026-09-29T10:00:00Z",
};

describe("MCP server form", () => {
  it("builds a create request for a program, secrets kept apart", () => {
    const form: ServerForm = {
      ...EMPTY_FORM,
      name: "files",
      command: " uvx ",
      args: "mcp-server-files\n\n  --root /tmp  \n",
      env: [{ key: "MODE", value: "safe" }, { key: " ", value: "ignored" }],
      secretEnv: [{ key: "API_TOKEN", value: "abc", saved: false }],
    };
    expect(validateForm(form, true)).toEqual({});
    expect(toCreate(form)).toEqual({
      name: "files",
      description: "",
      transport: "stdio",
      risk_level: "HIGH",
      timeout_s: 60,
      enabled: true,
      command: "uvx",
      args: ["mcp-server-files", "--root /tmp"],
      cwd: null,
      env: { MODE: "safe" },
      secret_env: { API_TOKEN: "abc" },
    });
    expect(argsFromText(" a \n\nb")).toEqual(["a", "b"]);
  });

  it("builds a create request for a web address", () => {
    const form: ServerForm = {
      ...EMPTY_FORM,
      name: "remote",
      transport: "http",
      command: "left over",
      url: "https://mcp.example.com/mcp",
      secretHeaders: [{ key: "Authorization", value: "Bearer x", saved: false }],
    };
    const body = toCreate(form);
    expect(body).toMatchObject({ transport: "http", url: "https://mcp.example.com/mcp", headers: {}, secret_headers: { Authorization: "Bearer x" } });
    expect(body).not.toHaveProperty("command");
  });

  it("explains what is wrong", () => {
    const errors = validateForm(
      {
        ...EMPTY_FORM,
        name: "My Server",
        timeout: "0",
        env: [{ key: "BAD-NAME", value: "1" }],
      },
      true,
    );
    expect(errors.name).toMatch(/lowercase/);
    expect(errors.command).toMatch(/command/);
    expect(errors.timeout).toMatch(/600/);
    expect(errors.env).toBe("“BAD-NAME” is not a valid variable name.");
    expect(validateForm({ ...EMPTY_FORM, name: "x", command: "c", secretEnv: [{ key: "T", value: "", saved: false }] }, true).env).toBe(
      "Enter the secret value for T.",
    );
    expect(validateForm({ ...EMPTY_FORM, name: "x", command: "c", env: [{ key: "A", value: "" }], secretEnv: [{ key: "a", value: "1", saved: false }] }, true).env).toBe(
      "a is listed twice.",
    );
    expect(validateForm({ ...EMPTY_FORM, name: "x", transport: "http", url: "example.com" }, true).url).toMatch(/https/);
    expect(validateForm({ ...toForm(server), name: "ignored when editing" }, false)).toEqual({});
  });

  it("sends only what changed, and never a saved secret's value", () => {
    const form = toForm(server);
    expect(form.secretEnv).toEqual([{ key: "GITHUB_TOKEN", value: "", saved: true }]);
    expect(toUpdate(server, form)).toEqual({});
    expect(toUpdate(server, { ...form, riskLevel: "VERY_HIGH", args: "-y\n@modelcontextprotocol/server-github\n--read-only" })).toEqual({
      risk_level: "VERY_HIGH",
      args: ["-y", "@modelcontextprotocol/server-github", "--read-only"],
    });
    // replace the saved token, add another, then remove the saved one
    const replaced = { ...form, secretEnv: [{ key: "GITHUB_TOKEN", value: "new", saved: true }, { key: "OTHER_KEY", value: "k", saved: false }] };
    expect(toUpdate(server, replaced)).toEqual({ secret_env: { GITHUB_TOKEN: "new", OTHER_KEY: "k" } });
    expect(toUpdate(server, { ...form, secretEnv: [] })).toEqual({ secret_env: { GITHUB_TOKEN: null } });
    expect(toUpdate(server, { ...form, cwd: "/srv/mcp" })).toEqual({ cwd: "/srv/mcp" });
  });

  it("summarises a server in a line", () => {
    expect(launchLine({ ...server, args: ["-y", "a b"] })).toBe('npx -y "a b"');
    expect(launchLine({ ...server, transport: "http", url: "https://x/mcp" })).toBe("https://x/mcp");
    expect(countLine(server)).toBe("12 tools · 1 resource · 0 prompts");
    expect(countLine({ tools: undefined, resources: undefined, prompts: undefined })).toBe("0 tools · 0 resources · 0 prompts");
  });
});
