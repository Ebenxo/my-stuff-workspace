import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ProjectForm } from "./ProjectForm";

function setup() {
  const onSubmit = vi.fn();
  const onCancel = vi.fn();
  render(<ProjectForm submitLabel="Create" pending={false} onSubmit={onSubmit} onCancel={onCancel} />);
  return { onSubmit, onCancel, user: userEvent.setup() };
}

describe("ProjectForm", () => {
  it("blocks submit and explains when the name is empty", async () => {
    const { onSubmit, user } = setup();
    await user.click(screen.getByRole("button", { name: "Create" }));
    expect(onSubmit).not.toHaveBeenCalled();
    expect(await screen.findByRole("alert")).toHaveTextContent("Give the project a name.");
    expect(screen.getByLabelText("Name")).toHaveAttribute("aria-invalid", "true");
  });

  it("treats whitespace-only as empty", async () => {
    const { onSubmit, user } = setup();
    await user.type(screen.getByLabelText("Name"), "   ");
    await user.click(screen.getByRole("button", { name: "Create" }));
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("submits trimmed values and the chosen permission level", async () => {
    const { onSubmit, user } = setup();
    await user.type(screen.getByLabelText("Name"), "  My Site  ");
    await user.type(screen.getByLabelText("Description"), " Landing page ");
    await user.selectOptions(screen.getByLabelText("Permissions"), "cautious");
    await user.click(screen.getByRole("button", { name: "Create" }));
    expect(onSubmit).toHaveBeenCalledWith({
      name: "My Site",
      description: "Landing page",
      permission_level: "cautious",
      monthly_budget_usd: null,
    });
  });

  it("sends the monthly budget as a number, and blocks negative values", async () => {
    const { onSubmit, user } = setup();
    await user.type(screen.getByLabelText("Name"), "Capped");
    await user.type(screen.getByLabelText(/Monthly budget/), "12.5");
    await user.click(screen.getByRole("button", { name: "Create" }));
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ monthly_budget_usd: 12.5 }));

    onSubmit.mockClear();
    await user.clear(screen.getByLabelText(/Monthly budget/));
    await user.type(screen.getByLabelText(/Monthly budget/), "-3");
    await user.click(screen.getByRole("button", { name: "Create" }));
    expect(onSubmit).not.toHaveBeenCalled();
    expect(await screen.findByText("Enter zero or more.")).toBeInTheDocument();
  });

  it("describes what the selected permission level means", async () => {
    const { user } = setup();
    expect(screen.getByText(/follows the default/i)).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Permissions"), "permissive");
    expect(screen.getByText(/except deletions/i)).toBeInTheDocument();
  });

  it("calls cancel", async () => {
    const { onCancel, user } = setup();
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onCancel).toHaveBeenCalled();
  });
});
