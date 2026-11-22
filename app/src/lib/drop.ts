import { getCurrentWebview } from "@tauri-apps/api/webview";
import { useEffect, useRef, useState } from "react";

/**
 * Files and folders dragged over Mado's window from File Explorer, anywhere on it: whether some
 * are over it now, and their paths once they're dropped (`onDrop`). The window's own drag and
 * drop is Tauri's (it gives paths, which a web page can't), so the page never sees the files.
 */
export function useDroppedFiles(onDrop: (paths: string[]) => void): { over: boolean } {
  const [over, setOver] = useState(false);
  const dropped = useRef(onDrop);
  useEffect(() => {
    dropped.current = onDrop;
  });
  useEffect(() => {
    let stop: (() => void) | null = null;
    let gone = false;
    let listening: Promise<() => void>;
    try {
      listening = getCurrentWebview().onDragDropEvent((event) => {
        const what = event.payload;
        if (what.type === "enter" || what.type === "over") setOver(true);
        else if (what.type === "leave") setOver(false);
        else if (what.type === "drop") {
          setOver(false);
          if (what.paths.length) dropped.current(what.paths);
        }
      });
    } catch {
      return; // outside Mado's window (a test, a browser): nothing is dropped on it
    }
    listening
      .then((unlisten) => {
        if (gone) unlisten();
        else stop = unlisten;
      })
      .catch(() => {
        // the window went before it listened: nothing to stop
      });
    return () => {
      gone = true;
      stop?.();
    };
  }, []);
  return { over };
}
