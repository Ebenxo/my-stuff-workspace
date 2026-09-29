/** Path helpers for the project file browser. Pure: the server's WorkspaceFS is the real guard. */

export const ROOT = ".";
export const WRITABLE_AREAS = new Set(["files", "temp"]);

export interface Crumb {
  label: string;
  path: string;
}

export function breadcrumbs(path: string): Crumb[] {
  const crumbs: Crumb[] = [{ label: "Project", path: ROOT }];
  if (path === ROOT || path === "") return crumbs;
  const parts = path.split("/").filter(Boolean);
  parts.forEach((part, i) => crumbs.push({ label: part, path: parts.slice(0, i + 1).join("/") }));
  return crumbs;
}

export function parentPath(path: string): string {
  const parts = path.split("/").filter(Boolean);
  return parts.length <= 1 ? ROOT : parts.slice(0, -1).join("/");
}

export function areaOf(path: string): string {
  return path.split("/").filter(Boolean)[0] ?? "";
}

export function isWritable(path: string): boolean {
  return WRITABLE_AREAS.has(areaOf(path));
}

export function baseName(path: string): string {
  return path.split("/").filter(Boolean).pop() ?? path;
}

/** Client-side check for a new file name so obvious mistakes never reach the server. */
export function validateNewName(name: string): string | undefined {
  const n = name.trim();
  if (!n) return "Enter a file name.";
  if (n.length > 200) return "That name is too long.";
  if (/[\\/]/.test(n)) return "Use a name only; pick the folder by opening it first.";
  if (n === "." || n === "..") return "That is not a valid file name.";
  // eslint-disable-next-line no-control-regex
  if (/[\x00-\x1f<>:"|?*]/.test(n)) return "That name has characters files cannot contain.";
  if (n.endsWith(".") || n.endsWith(" ")) return "A file name cannot end with a dot or space.";
  return undefined;
}

export function joinPath(dir: string, name: string): string {
  return dir === ROOT || dir === "" ? name.trim() : `${dir}/${name.trim()}`;
}
