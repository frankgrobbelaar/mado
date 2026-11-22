import { ToggleGroup } from "radix-ui";
import { cn } from "@/lib/utils";

interface SegmentedProps<T extends string> {
  label: string;
  value: T;
  options: readonly { value: T; label: string }[];
  onChange: (value: T) => void;
  className?: string;
}

/**
 * One choice from a few, shown side by side (A new picture, Replace the original). Built on
 * Radix's ToggleGroup, so arrow keys move between the choices. Graphite: a well with the chosen
 * one raised.
 */
export function Segmented<T extends string>({
  label,
  value,
  options,
  onChange,
  className,
}: SegmentedProps<T>) {
  return (
    <ToggleGroup.Root
      type="single"
      aria-label={label}
      value={value}
      onValueChange={(next) => {
        if (next) onChange(next as T); // clicking the chosen one again keeps it chosen
      }}
      className={cn("inline-flex gap-0.5 rounded-6 border border-edge bg-well p-0.5", className)}
    >
      {options.map((option) => (
        <ToggleGroup.Item
          key={option.value}
          value={option.value}
          className="press min-h-8 cursor-pointer rounded-4 px-3 text-13 text-fg-muted data-[state=on]:bg-raised data-[state=on]:font-semibold data-[state=on]:text-fg"
        >
          {option.label}
        </ToggleGroup.Item>
      ))}
    </ToggleGroup.Root>
  );
}
