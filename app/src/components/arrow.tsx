import { ArrowRight } from "lucide-react";

/** "→", drawn at the size of the words round it, and read as `said` ("to", "then"): IBM Plex as
 * Mado bundles it has no arrow, so a typed one would come in another font. */
export function Arrow({ said }: { said: string }) {
  return (
    <>
      <ArrowRight
        aria-hidden="true"
        size="1em"
        strokeWidth={1.75}
        className="inline-block shrink-0 align-[-0.125em]"
      />
      <span className="sr-only"> {said} </span>
    </>
  );
}
