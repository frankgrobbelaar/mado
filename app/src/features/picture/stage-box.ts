import { useEffect, useState } from "react";

/** The space a stage has, kept as the window changes; `measured` once it's known, not guessed
 * (where nothing can measure it, the guess is all there is). */
export function useBox(area: { current: HTMLElement | null }) {
  const unmeasurable = typeof ResizeObserver === "undefined";
  const [box, setBox] = useState({ width: 1000, height: 560, measured: unmeasurable });
  useEffect(() => {
    const here = area.current;
    if (!here || typeof ResizeObserver === "undefined") return;
    const watch = new ResizeObserver(([entry]) => {
      if (entry && entry.contentRect.width > 0 && entry.contentRect.height > 0)
        setBox({
          width: entry.contentRect.width,
          height: entry.contentRect.height,
          measured: true,
        });
    });
    watch.observe(here);
    return () => watch.disconnect();
  }, [area]);
  return box;
}

/** Something of `ratio` fitted in `box`, in its middle. */
export function fitted(box: { width: number; height: number }, ratio: number) {
  const width = Math.min(box.width, box.height * ratio);
  const height = width / ratio;
  return { width, height, left: (box.width - width) / 2, top: (box.height - height) / 2 };
}
