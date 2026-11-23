import { createContext, type ReactNode, useContext, useEffect, useState } from "react";

const Note = createContext<{ note: string | null; set: (note: string | null) => void } | null>(
  null,
);

/** What the page in view says in the status bar, as the boards' status bars do: "1 part
 * picked". The shell holds it; a page sets it while it's open. */
export function StatusNoteProvider({ children }: { children: ReactNode }) {
  const [note, set] = useState<string | null>(null);
  return <Note.Provider value={{ note, set }}>{children}</Note.Provider>;
}

/** Says `note` in the status bar while this page is open (null: nothing). */
export function useStatusNote(note: string | null) {
  const held = useContext(Note);
  const set = held?.set;
  useEffect(() => {
    set?.(note);
    return () => set?.(null);
  }, [note, set]);
}

/** What the page in view says, for the status bar. */
export function useShownNote(): string | null {
  return useContext(Note)?.note ?? null;
}
