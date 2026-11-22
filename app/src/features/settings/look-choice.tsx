import { RadioGroup } from "radix-ui";
import { useId } from "react";
import type { Look } from "@/lib/look";
import { LOOKS } from "@/lib/look";

const CAPTIONS: Record<Look, string> = {
  windows: "Changes when Windows does",
  light: "Aluminium, always",
  dark: "Graphite, always",
};

/** The two schemes as the window wears them, for the little pictures on the choices. */
const SCHEMES = {
  dark: { window: "#2a2b2e", rail: "#232427", panel: "#333438", accent: "#c9f24d" },
  light: { window: "#d3d4d7", rail: "#c9cace", panel: "#e4e5e8", accent: "#4c7500" },
} as const;

/** Light or dark, three choices side by side, each with a little picture of the window in it:
 * Same as Windows, Light (Aluminium) and Dark (Graphite). Built on Radix's RadioGroup, so arrow
 * keys move between them. */
export function LookChoice(props: { value: Look; onChange: (look: Look) => void }) {
  const id = useId();
  return (
    <div className="flex flex-col gap-3">
      <span className="flex flex-col gap-0.5">
        <span id={id} className="font-semibold">
          Light or dark
        </span>
        <span className="text-13 text-fg-muted">
          Graphite is the dark, Aluminium the light. Your pictures look the same in both.
        </span>
      </span>
      <RadioGroup.Root
        aria-labelledby={id}
        value={props.value}
        onValueChange={(next) => props.onChange(next as Look)}
        className="grid grid-cols-[repeat(auto-fit,minmax(10rem,1fr))] gap-3"
      >
        {LOOKS.map((look) => (
          <RadioGroup.Item
            key={look.value}
            value={look.value}
            aria-label={look.label}
            className="group press flex cursor-pointer flex-col gap-2.5 rounded-8 border border-edge bg-glass p-2.5 text-left data-[state=checked]:border-accent data-[state=checked]:bg-accent/8"
          >
            <Preview look={look.value} />
            <span className="flex items-center gap-2 px-0.5">
              <span
                aria-hidden="true"
                className="flex size-4 items-center justify-center rounded-full border-[1.5px] border-control group-data-[state=checked]:border-accent"
              >
                <span className="size-2 rounded-full group-data-[state=checked]:bg-accent" />
              </span>
              <span className="font-semibold text-14">{look.label}</span>
            </span>
            <span className="px-0.5 text-12 text-fg-muted">{CAPTIONS[look.value]}</span>
          </RadioGroup.Item>
        ))}
      </RadioGroup.Root>
    </div>
  );
}

/** A little window in a scheme: its rail, two panels and the accent; both halves for Same as
 * Windows. */
function Preview({ look }: { look: Look }) {
  const halves = look === "windows" ? [SCHEMES.dark, SCHEMES.light] : [SCHEMES[look]];
  return (
    <span aria-hidden="true" className="flex h-16 overflow-hidden rounded-6 border border-edge">
      {halves.map((scheme) => (
        <span
          key={scheme.window}
          className="flex flex-1 gap-1.5 p-1.5"
          style={{ background: scheme.window }}
        >
          <span className="w-2.5 rounded-2" style={{ background: scheme.rail }} />
          <span className="flex flex-1 flex-col gap-1.5">
            <span className="h-2 rounded-2" style={{ background: scheme.panel }} />
            <span className="h-1.5 w-1/3 rounded-full" style={{ background: scheme.accent }} />
            <span className="flex-1 rounded-2" style={{ background: scheme.panel }} />
          </span>
        </span>
      ))}
    </span>
  );
}
