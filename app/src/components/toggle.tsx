import { useId } from "react";
import { Switch } from "@/components/ui/switch";

/** A choice that's on or off, with what it does under its name. */
export function Toggle(props: {
  label: string;
  text: string;
  checked: boolean;
  onChange: (on: boolean) => void;
}) {
  const id = useId();
  return (
    <div className="flex items-center gap-3.5 rounded-16 border border-edge bg-glass px-4 py-3.5">
      <Switch
        id={id}
        checked={props.checked}
        onCheckedChange={props.onChange}
        aria-describedby={`${id}-text`}
      />
      <span className="flex flex-col gap-0.5">
        <label htmlFor={id} className="cursor-pointer font-extrabold">
          {props.label}
        </label>
        <span id={`${id}-text`} className="text-13 text-fg-muted">
          {props.text}
        </span>
      </span>
    </div>
  );
}
