import { describe, expect, it } from "vitest";
import { dayAndTime, madeAt, size, split } from "./format";

describe("size", () => {
  it("writes sizes the way the boards do", () => {
    expect(size(0)).toBe("0 KB");
    expect(size(200)).toBe("1 KB");
    expect(size(320_400)).toBe("320 KB");
    expect(size(233_000_000)).toBe("233 MB");
    expect(size(1_100_000_000)).toBe("1.1 GB");
    expect(size(8_200_000_000)).toBe("8.2 GB");
    expect(size(16_400_000_000)).toBe("16 GB");
    expect(size(931_000_000_000)).toBe("931 GB");
    expect(size(1_240_000_000_000)).toBe("1.2 TB");
  });
});

describe("dayAndTime", () => {
  it("says today and yesterday, and the date before that", () => {
    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 3, 0);
    const yesterday = new Date(today);
    yesterday.setDate(today.getDate() - 1);

    expect(dayAndTime(today)).toBe("today 03:00");
    expect(dayAndTime(yesterday)).toBe("yesterday 03:00");
    expect(dayAndTime(new Date(2020, 9, 11, 3, 0))).toBe("11 October 03:00");
  });
});

describe("madeAt", () => {
  it("says so when a backup's time can't be read", () => {
    expect(madeAt("not a time")).toBe("a backup Mado no longer has");
  });
});

describe("split", () => {
  it("parts a path into its file name and its folder", () => {
    expect(split("D:\\Backups\\Mado export.zip")).toEqual(["Mado export.zip", "D:\\Backups"]);
  });
});
