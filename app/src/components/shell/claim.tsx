import { createContext, type ReactNode, use, useEffect, useRef } from "react";

/** A picture, as what's dropped or pasted opens as. */
export interface Taken {
  id: number;
  name: string;
  outside: boolean;
}

/**
 * A page that takes a picture dropped on the window or pasted for itself (the wallpaper studio),
 * rather than the window opening it on its own page. The window's own Opening still does the
 * work (the shell's drop, Ctrl+V, files copied in File Explorer); it hands the one picture over.
 */
export interface Claim {
  take: (picture: Taken) => void;
  /** What the window says while pictures are dragged over it. */
  title: string;
  body: string;
}

type Claims = { current: Claim | null };

const ClaimContext = createContext<Claims>({ current: null });

/** Where pages say they take what's dropped or pasted: the window's frame holds it. */
export function ClaimProvider({ children }: { children: ReactNode }) {
  const claims = useRef<Claim | null>(null);
  return <ClaimContext value={claims}>{children}</ClaimContext>;
}

/** The page taking what's dropped or pasted, if one is: read when something comes. */
export function useClaims(): Claims {
  return use(ClaimContext);
}

/** While the page is open, a picture dropped on the window or pasted is its to take. */
export function useClaim(claim: Claim) {
  const claims = use(ClaimContext);
  const latest = useRef(claim);
  useEffect(() => {
    latest.current = claim;
  });
  useEffect(() => {
    const mine: Claim = {
      take: (picture) => latest.current.take(picture),
      get title() {
        return latest.current.title;
      },
      get body() {
        return latest.current.body;
      },
    };
    claims.current = mine;
    return () => {
      if (claims.current === mine) claims.current = null;
    };
  }, [claims]);
}
