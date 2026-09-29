import type { Approval } from "@nexus/schemas";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { jsonResponse, renderWithProviders } from "../../test/render";
import { ApprovalCard } from "./ApprovalCard";

const GET = vi.fn();
const POST = vi.fn();
vi.mock("../../lib/api", () => ({
  api: { GET: (...a: unknown[]) => GET(...a), POST: (...a: unknown[]) => POST(...a) },
  runtimeConfig: { baseUrl: "", token: undefined },
}));

const approval = (over: Partial<Approval> = {}): Approval => ({
  id: "appr_1",
  project_id: "proj_1",
  run_id: "run_1",
  task_id: null,
  agent_id: "agent_1",
  tool_name: "delete_file",
  arguments: { path: "files/old.txt" },
  edited_arguments: null,
  reason: "Remove the old file",
  risk_level: "HIGH",
  impact: "Moves files/old.txt to the project's trash (recoverable).",
  session_grantable: false,
  tainted: false,
  taint_sources: [],
  status: "PENDING",
  decided_by: null,
  decision_note: null,
  created_at: "2026-09-29T10:00:00Z",
  decided_at: null,
  ...over,
});

const decision = (call = 0) => (POST.mock.calls[call]![1] as { params: { path: { approval_id: string } }; body: Record<string, unknown> });

describe("ApprovalCard", () => {
  beforeEach(() => {
    GET.mockReset().mockResolvedValue(jsonResponse([]));
    POST.mockReset().mockResolvedValue(jsonResponse(approval({ status: "APPROVED_ONCE" })));
  });

  it("explains what will happen before anything does", () => {
    renderWithProviders(<ApprovalCard approval={approval()} agentName="File Manager" />);
    expect(screen.getByText("High risk")).toBeInTheDocument();
    expect(screen.getByText("delete_file")).toBeInTheDocument();
    expect(screen.getByText("File Manager")).toBeInTheDocument();
    expect(screen.getByText(/Remove the old file/)).toBeInTheDocument();
    expect(screen.getByText(/Moves files\/old.txt to the project's trash/)).toBeInTheDocument();
    expect(screen.getByText("files/old.txt")).toBeInTheDocument();
    expect(POST).not.toHaveBeenCalled();
  });

  it("approves once", async () => {
    renderWithProviders(<ApprovalCard approval={approval()} />);
    await userEvent.click(screen.getByRole("button", { name: /Approve once/ }));
    await waitFor(() => expect(POST).toHaveBeenCalledTimes(1));
    expect(POST.mock.calls[0]![0]).toBe("/api/approvals/{approval_id}/decision");
    expect(decision().params.path.approval_id).toBe("appr_1");
    expect(decision().body).toEqual({ decision: "approve_once" });
  });

  it("does not offer a session approval for actions that must always ask", () => {
    renderWithProviders(<ApprovalCard approval={approval({ session_grantable: false })} />);
    expect(screen.queryByRole("button", { name: /For this session/ })).not.toBeInTheDocument();
    expect(screen.getByText(/always asks/)).toBeInTheDocument();
  });

  it("can approve a safe-enough action for the session", async () => {
    renderWithProviders(<ApprovalCard approval={approval({ tool_name: "write_file", risk_level: "MODERATE", session_grantable: true })} />);
    await userEvent.click(screen.getByRole("button", { name: /For this session/ }));
    await waitFor(() => expect(POST).toHaveBeenCalled());
    expect(decision().body).toEqual({ decision: "approve_session" });
  });

  it("denies", async () => {
    renderWithProviders(<ApprovalCard approval={approval()} />);
    await userEvent.click(screen.getByRole("button", { name: /Deny/ }));
    await waitFor(() => expect(POST).toHaveBeenCalled());
    expect(decision().body).toEqual({ decision: "deny" });
  });

  it("warns when the request may have been influenced by outside content", () => {
    renderWithProviders(<ApprovalCard approval={approval({ tainted: true, taint_sources: ["web:evil.example", "file:notes.txt"] })} />);
    const note = screen.getByRole("note");
    expect(note).toHaveTextContent("web:evil.example, file:notes.txt");
    expect(note).toHaveTextContent(/influenced/);
  });

  it("checks edited arguments before sending them", async () => {
    renderWithProviders(<ApprovalCard approval={approval()} />);
    await userEvent.click(screen.getByRole("button", { name: /Edit/ }));
    const box = screen.getByLabelText(/Edit the arguments/);
    expect(box).toHaveValue(JSON.stringify({ path: "files/old.txt" }, null, 2));

    fireEvent.change(box, { target: { value: "{not json" } });
    await userEvent.click(screen.getByRole("button", { name: /Approve with changes/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/not valid JSON/);
    expect(POST).not.toHaveBeenCalled();

    fireEvent.change(box, { target: { value: '["a"]' } });
    await userEvent.click(screen.getByRole("button", { name: /Approve with changes/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/JSON object/);
    expect(POST).not.toHaveBeenCalled();

    fireEvent.change(box, { target: { value: '{"path": "files/other.txt"}' } });
    await userEvent.click(screen.getByRole("button", { name: /Approve with changes/ }));
    await waitFor(() => expect(POST).toHaveBeenCalled());
    expect(decision().body).toEqual({ decision: "approve_once", edited_arguments: { path: "files/other.txt" } });
  });

  it("can back out of an edit", async () => {
    renderWithProviders(<ApprovalCard approval={approval()} />);
    await userEvent.click(screen.getByRole("button", { name: /Edit/ }));
    await userEvent.click(screen.getByRole("button", { name: /Cancel edit/ }));
    expect(screen.getByRole("button", { name: /Approve once/ })).toBeInTheDocument();
    expect(screen.queryByLabelText(/Edit the arguments/)).not.toBeInTheDocument();
  });

  it("shows a past decision without offering any buttons", () => {
    renderWithProviders(
      <ApprovalCard approval={approval({ status: "APPROVED_ONCE", edited_arguments: { path: "files/other.txt" }, decision_note: "ok" })} readOnly />,
    );
    expect(screen.getByText("Approved once")).toBeInTheDocument();
    expect(screen.getByText("Edited")).toBeInTheDocument();
    expect(screen.getByText("files/other.txt")).toBeInTheDocument(); // what actually ran
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("shows the highest-risk requests as such", () => {
    renderWithProviders(<ApprovalCard approval={approval({ tool_name: "run_command", risk_level: "VERY_HIGH" })} />);
    expect(screen.getByText("Very high risk")).toBeInTheDocument();
  });

  it("keeps the buttons usable when the server refuses (already decided elsewhere)", async () => {
    POST.mockResolvedValue(jsonResponse({ error: { code: "conflict", message: "This approval was already approved once.", details: {} } }, 409));
    renderWithProviders(<ApprovalCard approval={approval()} />);
    await userEvent.click(screen.getByRole("button", { name: /Approve once/ }));
    await waitFor(() => expect(POST).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByRole("button", { name: /Approve once/ })).toBeEnabled());
  });
});
