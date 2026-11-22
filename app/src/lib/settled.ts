import { useEffect, useState } from "react";

/** A value that's stopped changing for `wait` milliseconds: a search asked as typing pauses, a
 * preview as the picture stops moving. */
export function useSettled<T>(value: T, wait: number): T {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setSettled(value), wait);
    return () => clearTimeout(timer);
  }, [value, wait]);
  return settled;
}
