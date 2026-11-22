import { cva, type VariantProps } from "class-variance-authority";
import { Slot } from "radix-ui";
import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

// Adapted from shadcn/ui's button (MIT, see LICENSE-shadcn.txt).
// Graphite's buttons are rectangles with 6px corners. One primary (volt) action per view; the
// rest are secondary or ghost.
const buttonVariants = cva(
  "press inline-flex cursor-pointer items-center justify-center gap-2 whitespace-nowrap rounded-6 font-semibold disabled:pointer-events-none disabled:opacity-50 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        primary: "bg-accent text-on-accent",
        secondary: "border border-field-edge bg-field text-fg",
        ghost: "bg-transparent text-fg-muted hover:bg-tint/6 hover:text-fg",
        danger: "bg-danger text-on-danger",
      },
      size: {
        md: "min-h-10 px-4 text-14",
        sm: "min-h-9 px-3 text-13",
      },
    },
    defaultVariants: { variant: "secondary", size: "md" },
  },
);

type ButtonProps = ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & {
    /** Render the child element (a link, say) with the button's look. */
    asChild?: boolean;
  };

export function Button({ className, variant, size, asChild = false, ...props }: ButtonProps) {
  const Component = asChild ? Slot.Root : "button";
  return (
    <Component
      data-slot="button"
      className={cn(buttonVariants({ variant, size }), className)}
      {...props}
    />
  );
}
