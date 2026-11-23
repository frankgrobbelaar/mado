import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { invoke } from "@tauri-apps/api/core";

const KEY = ["shell", "start-with-windows"];
const KEEP = ["shell", "keep-in-tray"];

/**
 * Whether Mado starts with Windows and waits in the tray. Windows keeps the answer (the shell
 * asks it, src-tauri/src/tray.rs), so it's true even when it was set before this launch.
 */
export function useStartWithWindows() {
  return useQuery({ queryKey: KEY, queryFn: () => invoke<boolean>("start_with_windows") });
}

/** Turns starting with Windows on or off. */
export function useSetStartWithWindows() {
  const queries = useQueryClient();
  return useMutation({
    mutationFn: (on: boolean) => invoke<boolean>("set_start_with_windows", { on }),
    onSuccess: (on) => queries.setQueryData(KEY, on),
  });
}

/** Whether closing the window keeps Mado running in the tray (the shell keeps the choice). */
export function useKeepInTray() {
  return useQuery({ queryKey: KEEP, queryFn: () => invoke<boolean>("keep_in_tray") });
}

/** Closing the window keeps Mado running in the tray, or quits it. */
export function useSetKeepInTray() {
  const queries = useQueryClient();
  return useMutation({
    mutationFn: (on: boolean) => invoke<boolean>("set_keep_in_tray", { on }),
    onSuccess: (on) => queries.setQueryData(KEEP, on),
  });
}

const EXPLORER = ["shell", "open-in-explorer"];

/**
 * Whether File Explorer offers "Open in Mado" on pictures and folders, and lists Mado in Open with
 * (the shell keeps the choice, and the keys under this user's own classes:
 * src-tauri/src/open_in_mado.rs). On till the owner turns it off.
 */
export function useOpenInExplorer() {
  return useQuery({ queryKey: EXPLORER, queryFn: () => invoke<boolean>("open_in_explorer") });
}

/** Puts "Open in Mado" in File Explorer, or takes it away. */
export function useSetOpenInExplorer() {
  const queries = useQueryClient();
  return useMutation({
    mutationFn: (on: boolean) => invoke<boolean>("set_open_in_explorer", { on }),
    onSuccess: (on) => queries.setQueryData(EXPLORER, on),
  });
}
