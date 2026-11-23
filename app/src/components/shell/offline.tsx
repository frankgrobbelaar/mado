import { WifiOff } from "lucide-react";
import { useSyncExternalStore } from "react";

/**
 * While Windows says the PC has no network: downloads and the check for a new version wait, and
 * the rest of Mado works as ever.
 */
export function Offline() {
  const online = useOnline();
  if (online) return null;
  return (
    <div
      role="status"
      className="flex animate-pop items-center gap-3 rounded-8 border border-tint/10 bg-raised px-4 py-3.5 text-14 shadow-toast"
    >
      <WifiOff size={20} aria-hidden="true" className="shrink-0 text-fg-soft" />
      <span>
        You're offline. Downloads and the check for a new version wait till you're back; everything
        else keeps working.
      </span>
    </div>
  );
}

/** Whether Windows says the PC has a network. */
export function useOnline(): boolean {
  return useSyncExternalStore(
    changes,
    () => navigator.onLine,
    () => true,
  );
}

function changes(changed: () => void): () => void {
  window.addEventListener("online", changed);
  window.addEventListener("offline", changed);
  return () => {
    window.removeEventListener("online", changed);
    window.removeEventListener("offline", changed);
  };
}
