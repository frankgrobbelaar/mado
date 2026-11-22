import { type RefObject, useEffect, useState } from "react";

/**
 * Whether an element is near the part of the page in view: within `margin` of the page's
 * scrolling area (the window's main part). The grid holds thousands of pictures, so each fetches
 * its thumbnail only when it comes near, and lets it go once it's far away. Where the window
 * can't tell (tests), everything counts as near.
 */
export function useNear(element: RefObject<HTMLElement | null>, margin = "1200px 0px"): boolean {
  const [near, setNear] = useState(typeof IntersectionObserver === "undefined");
  useEffect(() => {
    const target = element.current;
    if (!target || typeof IntersectionObserver === "undefined") return;
    const watcher = new IntersectionObserver(
      ([seen]) => {
        if (seen) setNear(seen.isIntersecting);
      },
      { root: target.closest("#main"), rootMargin: margin },
    );
    watcher.observe(target);
    return () => watcher.disconnect();
  }, [element, margin]);
  return near;
}
