import { useState } from "react";
import { pickFolder } from "@/lib/dialogs";
import { useAddFolder } from "@/lib/engine";

/** Adding a folder to the library: Windows' folder picker, then the engine, which reads it.
 * `problem` says why it couldn't, in the engine's words. */
export function useAddFolderPicker() {
  const add = useAddFolder();
  const [picking, setPicking] = useState(false);

  async function pick() {
    setPicking(true);
    try {
      const path = await pickFolder("Choose a folder with pictures in it");
      if (path) add.mutate({ path: "/folders", body: { path } });
    } finally {
      setPicking(false);
    }
  }

  return {
    pick: () => void pick(),
    busy: picking || add.isPending,
    problem: add.isError ? add.error.message : null,
  };
}
