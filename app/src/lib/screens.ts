import { invoke } from "@tauri-apps/api/core";

/** A screen of this PC, as the shell sees it: its pixels, and whether it's the main one. */
export interface SeenScreen {
  width: number;
  height: number;
  main: boolean;
}

/** This PC's screens, from the shell (src-tauri/src/screens.rs); none when it can't say. */
export async function thisPcsScreens(): Promise<SeenScreen[]> {
  try {
    const found = await invoke<SeenScreen[] | null>("screens");
    return Array.isArray(found) ? found.filter((each) => each.width > 0 && each.height > 0) : [];
  } catch {
    return [];
  }
}
