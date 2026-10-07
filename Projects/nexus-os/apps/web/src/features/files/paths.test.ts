import { describe, expect, it } from "vitest";
import { areaOf, baseName, breadcrumbs, isWritable, joinPath, parentPath, validateNewName } from "./paths";

describe("file paths", () => {
  it("builds breadcrumbs from the project root", () => {
    expect(breadcrumbs(".")).toEqual([{ label: "Project", path: "." }]);
    expect(breadcrumbs("files/docs/a")).toEqual([
      { label: "Project", path: "." },
      { label: "files", path: "files" },
      { label: "docs", path: "files/docs" },
      { label: "a", path: "files/docs/a" },
    ]);
  });

  it("finds parents, areas and names", () => {
    expect(parentPath("files/docs/a.md")).toBe("files/docs");
    expect(parentPath("files")).toBe(".");
    expect(parentPath(".")).toBe(".");
    expect(areaOf("files/x")).toBe("files");
    expect(baseName("files/docs/a.md")).toBe("a.md");
  });

  it("knows which areas a person may write to", () => {
    expect(isWritable("files/a.md")).toBe(true);
    expect(isWritable("temp/run-1/out.txt")).toBe(true);
    expect(isWritable("artifacts/report.md")).toBe(false);
    expect(isWritable(".")).toBe(false);
  });

  it("joins directory and name", () => {
    expect(joinPath(".", " a.md ")).toBe("a.md");
    expect(joinPath("files/docs", "a.md")).toBe("files/docs/a.md");
  });

  it("rejects bad new file names before the server sees them", () => {
    expect(validateNewName("")).toMatch(/Enter/);
    expect(validateNewName("a/b.md")).toMatch(/name only/);
    expect(validateNewName("..")).toMatch(/not a valid/);
    expect(validateNewName("a?.md")).toMatch(/characters/);
    expect(validateNewName("trailing.")).toMatch(/dot or space/);
    expect(validateNewName("x".repeat(201))).toMatch(/too long/);
    expect(validateNewName("notes.md")).toBeUndefined();
  });
});
