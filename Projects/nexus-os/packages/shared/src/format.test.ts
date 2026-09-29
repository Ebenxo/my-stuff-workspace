import { describe, expect, it } from "vitest";
import { formatBytes, formatDuration, formatRelativeTime, greeting, truncate } from "./format";

describe("format", () => {
  const now = new Date("2026-09-29T12:00:00Z");
  it("formats relative time", () => {
    expect(formatRelativeTime("2026-09-29T11:59:58Z", now)).toBe("just now");
    expect(formatRelativeTime("2026-09-29T11:55:00Z", now)).toBe("5 minutes ago");
    expect(formatRelativeTime("2026-09-27T12:00:00Z", now)).toBe("2 days ago");
    expect(formatRelativeTime("2026-09-29T13:00:00Z", now)).toBe("in 1 hour");
  });
  it("formats bytes and durations", () => {
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(1536)).toBe("1.5 KB");
    expect(formatBytes(-1)).toBe("—");
    expect(formatDuration(45)).toBe("45s");
    expect(formatDuration(125)).toBe("2m 5s");
    expect(formatDuration(3700)).toBe("1h 1m");
  });
  it("greets by hour and truncates", () => {
    expect(greeting(new Date(2026, 0, 1, 9))).toBe("Good morning");
    expect(greeting(new Date(2026, 0, 1, 14))).toBe("Good afternoon");
    expect(greeting(new Date(2026, 0, 1, 20))).toBe("Good evening");
    expect(truncate("abcdef", 4)).toBe("abc…");
    expect(truncate("abc", 4)).toBe("abc");
  });
});
