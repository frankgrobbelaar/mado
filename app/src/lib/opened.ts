import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";

/**
 * Pictures Windows handed to Mado (src-tauri/src/opened.rs): from File Explorer's "Open in Mado",
 * Open with or the command line, each start's paths gathered with those arriving close together
 * into one choice. The shell keeps them till the window takes them.
 */
export function takeOpened() {
  return invoke<string[][]>("take_opened");
}

/** Calls `heard` whenever the shell has a choice ready to take; gives back a way to stop. */
export function onOpened(heard: () => void): Promise<() => void> {
  return listen("opened", heard);
}

/** The paths of the files copied in File Explorer, which a page is never given
 * (src-tauri/src/clipboard.rs); none when the clipboard holds anything else. */
export function clipboardFiles() {
  return invoke<string[]>("clipboard_files");
}
