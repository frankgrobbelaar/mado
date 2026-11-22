// Adapted from shadcn/ui's slider (MIT, see LICENSE-shadcn.txt), restyled to Graphite as the
// Picture-Looks board draws it: a thin track, the part up to the thumb in the accent, a round
// thumb in the text colour. Built on Radix's slider, so the arrow keys, Page Up and Down, Home and
// End move it.
import { Slider as Primitive } from "radix-ui";
import { cn } from "@/lib/utils";

export function Slider(props: {
  label: string;
  value: number;
  onChange: (value: number) => void;
  min?: number;
  max?: number;
  step?: number;
  disabled?: boolean;
  /** What a screen reader says of the value: "60%". */
  valueText?: string;
  className?: string;
}) {
  return (
    <Primitive.Root
      value={[props.value]}
      min={props.min ?? 0}
      max={props.max ?? 100}
      step={props.step ?? 1}
      disabled={props.disabled}
      onValueChange={([next]) => next !== undefined && props.onChange(next)}
      className={cn(
        "relative flex h-5 flex-1 cursor-pointer touch-none select-none items-center data-disabled:cursor-default data-disabled:opacity-50",
        props.className,
      )}
    >
      <Primitive.Track className="relative h-1 grow overflow-hidden rounded-2 bg-track">
        <Primitive.Range className="absolute h-full bg-accent" />
      </Primitive.Track>
      <Primitive.Thumb
        aria-label={props.label}
        aria-valuetext={props.valueText}
        className="block size-4 rounded-full bg-fg transition-transform duration-120 ease-mado hover:scale-110"
      />
    </Primitive.Root>
  );
}
