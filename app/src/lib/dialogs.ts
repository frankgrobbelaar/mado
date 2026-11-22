import { invoke } from "@tauri-apps/api/core";

/** Asks for a folder with Windows' folder picker. Null when it's cancelled. */
export function pickFolder(title: string) {
  return invoke<string | null>("pick_folder", { title });
}

/** Asks for a Mado export (its zip) with Windows' file picker. Null when it's cancelled. */
export function pickExport(title: string) {
  return invoke<string | null>("pick_export", { title });
}

/** Asks for a look, a .cube file, with Windows' file picker. Null when it's cancelled. */
export function pickCube(title: string) {
  return invoke<string | null>("pick_cube", { title });
}

/** Asks for pictures with Windows' file picker, as many as are wanted. Empty when it's
 * cancelled. */
export function pickPictures(title: string) {
  return invoke<string[]>("pick_pictures", { title });
}
