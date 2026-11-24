import { describe, expect, it } from "vitest";
import {
  about,
  clock,
  count,
  dayAndTime,
  dayHeading,
  depthAs,
  editedAs,
  madeAt,
  madeWith,
  pictures,
  restoredAs,
  size,
  split,
  takenOn,
  versionOf,
} from "./format";

describe("madeWith and versionOf", () => {
  it("say what a picture was made for and with", () => {
    const sized = { madeFor: "TV 8K", look: null };
    const looked = { madeFor: null, look: "Warm film at 60%" };
    const both = { madeFor: "TV 8K", look: "Warm film at 60%" };

    expect(madeWith(sized)).toBe("for TV 8K");
    expect(madeWith(looked)).toBe("with Warm film at 60%");
    expect(madeWith(both)).toBe("for TV 8K, with Warm film at 60%");
    expect(versionOf(sized)).toBe("TV 8K");
    expect(versionOf(looked)).toBe("Warm film at 60%");
    expect(versionOf(both)).toBe("TV 8K, Warm film at 60%");
  });

  it("say the edits made first in brackets, and a picture only edited is its edited version", () => {
    const erased = { madeFor: null, look: null, edit: "erased a part" };
    const sizedToo = { madeFor: "TV 8K", look: null, edit: "cut out the subject" };

    expect(madeWith(erased)).toBe("(erased a part)");
    expect(madeWith(sizedToo)).toBe("for TV 8K (cut out the subject)");
    expect(versionOf(erased)).toBe("edited");
    expect(versionOf(sizedToo)).toBe("TV 8K");
  });
});

describe("the depth tools and a 3D photo", () => {
  it("say the depth tools with the look, and a 3D photo as what it was made into", () => {
    const blurred = { madeFor: null, look: null, depth: "portrait blur at f/2.8" };
    const all = {
      madeFor: "TV 8K",
      look: "Warm film at 60%",
      depth: "portrait blur at f/2.8 and fog",
    };
    const video = { madeFor: null, look: null, depth: "into a 3D photo, swaying for 5 s" };

    expect(madeWith(blurred)).toBe("with portrait blur at f/2.8");
    expect(madeWith(all)).toBe(
      "for TV 8K, with portrait blur at f/2.8 and fog and Warm film at 60%",
    );
    expect(madeWith(video)).toBe("into a 3D photo, swaying for 5 s");
    expect(versionOf(blurred)).toBe("portrait blur");
    expect(depthAs("portrait blur at f/1.4")).toBe("Portrait blur");
    expect(depthAs("fog")).toBe("Fog");
    expect(depthAs("tilt-shift")).toBe("Tilt-shift");
    expect(depthAs("portrait blur at f/2.8, fog and tilt-shift")).toBe("Depth");
    expect(depthAs(video.depth)).toBe("3D photo");
    expect(depthAs(null)).toBeNull();
  });
});

describe("restoring", () => {
  it("says restoring in the brackets, after the edits and before the fixes, as it's made", () => {
    const coloured = { madeFor: null, look: null, restore: "coloured it" };
    const all = {
      madeFor: "TV 8K",
      look: null,
      edit: "erased a part",
      restore: "filled its scratches and dust and coloured it",
      fix: "took out noise",
    };

    expect(madeWith(coloured)).toBe("(coloured it)");
    expect(madeWith(all)).toBe(
      "for TV 8K (erased a part; filled its scratches and dust and coloured it; took out noise)",
    );
    expect(versionOf(coloured)).toBe("restored");
    expect(versionOf({ ...coloured, fix: "took out noise" })).toBe("restored");
    expect(restoredAs("coloured it")).toBe("Coloured");
    expect(restoredAs("filled its scratches and dust")).toBe("Restored");
    expect(restoredAs("brought its faded colours back")).toBe("Restored");
    expect(restoredAs(null)).toBeNull();
  });
});

describe("editedAs", () => {
  it("says what the edits made a picture, as its new name does", () => {
    expect(editedAs("erased a part")).toBe("Erased");
    expect(editedAs("erased 2 parts, erased a part")).toBe("Erased");
    expect(editedAs("cut out the subject")).toBe("Cut out");
    expect(editedAs("cut out a part over the rest, blurred")).toBe("Cut out");
    expect(editedAs("blurred what's behind a part")).toBe("Blurred");
    expect(editedAs("erased a part, cut out the subject onto a colour")).toBe("Edited");
    expect(editedAs(null)).toBeNull();
  });
});

describe("size", () => {
  it("writes sizes the way the boards do", () => {
    expect(size(0)).toBe("0 KB");
    expect(size(200)).toBe("1 KB");
    expect(size(320_400)).toBe("320 KB");
    expect(size(3_100_000)).toBe("3.1 MB");
    expect(size(21_400_000)).toBe("21.4 MB");
    expect(size(76_972_461)).toBe("77 MB"); // a whole number keeps no ".0"
    expect(size(233_000_000)).toBe("233 MB");
    expect(size(1_100_000_000)).toBe("1.1 GB");
    expect(size(8_200_000_000)).toBe("8.2 GB");
    expect(size(38_200_000_000)).toBe("38.2 GB");
    expect(size(412_000_000_000)).toBe("412 GB");
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

describe("count and pictures", () => {
  it("write numbers with their thousands marked, and say picture or pictures", () => {
    expect(count(4812)).toBe("4,812");
    expect(pictures(1)).toBe("1 picture");
    expect(pictures(3104)).toBe("3,104 pictures");
  });
});

describe("dayHeading", () => {
  it("names a day of this year by its weekday, and adds the year for older ones", () => {
    const now = new Date(2026, 10, 22);

    expect(dayHeading("2026-11-14", now)).toBe("Saturday 14 November");
    expect(dayHeading("2025-06-01", now)).toBe("Sunday 1 June 2025");
  });
});

describe("taken", () => {
  it("says when on a day a picture was taken, and when in full", () => {
    expect(clock("2026-11-12T18:42:07")).toBe("18:42");
    expect(takenOn("2026-11-12T18:42:07")).toBe("12 Nov 2026, 18:42");
  });
});

describe("about", () => {
  it("rounds what's left the way a person says it", () => {
    expect(about(12)).toBe("about 10 s");
    expect(about(40)).toBe("about 40 s");
    expect(about(185)).toBe("about 3 min");
    expect(about(4800)).toBe("about 1 h 20 min");
    expect(about(7200)).toBe("about 2 h");
  });
});
