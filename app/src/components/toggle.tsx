import { useId } from "react";
import { Switch } from "@/components/ui/switch";

/** A choice that's on or off: its name and what it does, the switch at the row's end. */
export function Toggle(props: {
  label: string;
  text: string;
  checked: boolean;
  onChange: (on: boolean) => void;
}) {
  const id = useId();
  return (
    <div className="flex items-center justify-between gap-4 rounded-8 border border-edge bg-glass px-4 py-3">
      <span className="flex min-w-0 flex-col gap-0.5">
        <label htmlFor={id} className="cursor-pointer font-semibold">
          {props.label}
        </label>
        <span id={`${id}-text`} className="text-13 text-fg-muted">
          {props.text}
        </span>
      </span>
      <Switch
        id={id}
        checked={props.checked}
        onCheckedChange={props.onChange}
        aria-describedby={`${id}-text`}
      />
    </div>
  );
}
