import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

// Adapted from shadcn/ui's input (MIT, see LICENSE-shadcn.txt), restyled to Graphite: a field
// with 6px corners like the buttons beside it, the accent's edge while it has the focus.
export function Input({ className, type = "text", ...props }: ComponentProps<"input">) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(
        "h-10 w-full min-w-0 rounded-6 border border-field-edge bg-field px-3 text-14 text-fg transition-[border-color] duration-200 ease-mado placeholder:text-fg-faint hover:border-tint/30 focus-visible:border-accent disabled:opacity-50",
        className,
      )}
      {...props}
    />
  );
}
