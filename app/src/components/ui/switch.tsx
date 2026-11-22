import { Switch as Primitive } from "radix-ui";
import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

/**
 * An on/off switch, built on Radix's Switch so it works with the keyboard and screen readers.
 * Graphite: a 40 by 22 track, the accent when on.
 */
export function Switch({ className, ...props }: ComponentProps<typeof Primitive.Root>) {
  return (
    <Primitive.Root
      className={cn(
        "relative inline-flex h-5.5 w-10 shrink-0 cursor-pointer rounded-full bg-control transition-colors duration-200 ease-mado data-[state=checked]:bg-accent disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      {...props}
    >
      <Primitive.Thumb className="absolute top-0.75 left-0.75 size-4 rounded-full bg-white transition-transform duration-200 ease-mado data-[state=checked]:translate-x-4.5 data-[state=checked]:bg-on-accent" />
    </Primitive.Root>
  );
}
