import type { UseQueryResult } from "@tanstack/react-query";
import { type KeyboardEvent, useRef } from "react";
import type { LookStep, PictureDetails, Plan, Recipe, SizeStep } from "@/lib/engine";
import { cn } from "@/lib/utils";
import { LooksTab } from "./looks-tab";
import { SizeTab } from "./size-tab";

export type Tool = "size" | "looks";

const TOOLS = [
  { key: "size", label: "Size", ready: true },
  { key: "looks", label: "Looks", ready: true },
  { key: "edit", label: "Edit", ready: false },
] as const;

/**
 * The column beside the picture where its tools are, as the Picture boards draw it: Size, Looks
 * and Edit along its top. Size makes the picture right for a screen or a print, Looks gives it a
 * look and finishing touches, and one Save on either makes both; Edit comes in Mado's next pieces,
 * so it waits, quietly, in its place.
 */
export function ToolsColumn(props: {
  picture: PictureDetails;
  tool: Tool;
  onTool: (tool: Tool) => void;
  size: SizeStep | null;
  onSize: (size: SizeStep) => void;
  look: LookStep;
  onLook: (look: LookStep) => void;
  onPoint: (step: LookStep | null) => void;
  /** The whole recipe Save makes; null while there's nothing to make. */
  recipe: Recipe | null;
  plan: UseQueryResult<Plan>;
  /** The look is still changing, so the plan for it isn't here yet. */
  settling: boolean;
}) {
  const ready = props.picture.state === "ready";
  const tabs = useRef<Partial<Record<Tool, HTMLButtonElement | null>>>({});
  // The plan Save opens with is the one for the recipe as it is now, never the last one's.
  const plan = props.plan.isPlaceholderData ? null : (props.plan.data ?? null);

  /** The arrow keys, Home and End go from tool to tool, as tabs do. */
  function move(event: KeyboardEvent<HTMLDivElement>) {
    const open = TOOLS.filter((tool) => tool.ready).map((tool) => tool.key) as Tool[];
    const at = open.indexOf(props.tool);
    const to =
      event.key === "ArrowRight"
        ? open[(at + 1) % open.length]
        : event.key === "ArrowLeft"
          ? open[(at - 1 + open.length) % open.length]
          : event.key === "Home"
            ? open[0]
            : event.key === "End"
              ? open.at(-1)
              : undefined;
    if (!to) return;
    event.preventDefault();
    props.onTool(to);
    tabs.current[to]?.focus();
  }

  return (
    <aside
      aria-label="Tools"
      className="sticky top-0 flex h-[calc(100vh-4.25rem)] w-100 shrink-0 flex-col gap-3.5 overflow-y-auto border-chrome-edge border-l bg-surface px-4.5 pt-3.5 pb-4"
    >
      <div
        role="tablist"
        aria-label="Tool"
        onKeyDown={move}
        className="flex rounded-6 bg-well p-0.75"
      >
        {TOOLS.map((tool) => {
          const chosen = tool.key === props.tool;
          return (
            <button
              key={tool.key}
              ref={(tab) => {
                if (tool.key !== "edit") tabs.current[tool.key] = tab;
              }}
              id={`tool-${tool.key}`}
              type="button"
              role="tab"
              aria-selected={chosen}
              aria-controls={chosen ? "tool-panel" : undefined}
              tabIndex={chosen ? 0 : -1}
              disabled={!tool.ready}
              title={tool.ready ? undefined : `${tool.label} comes in Mado's next pieces`}
              onClick={() => tool.key !== "edit" && props.onTool(tool.key)}
              className={cn(
                "press flex h-8 flex-1 items-center justify-center rounded-4 text-13",
                chosen
                  ? "bg-raised font-semibold text-fg"
                  : tool.ready
                    ? "cursor-pointer font-medium text-fg-muted hover:text-fg"
                    : "font-medium text-fg-faint",
              )}
            >
              {tool.label}
            </button>
          );
        })}
      </div>
      <div
        role="tabpanel"
        id="tool-panel"
        aria-labelledby={`tool-${props.tool}`}
        className="flex min-h-0 flex-1 flex-col"
      >
        {!ready ? (
          <p className="text-13 text-fg-muted leading-normal">
            {props.picture.state === "raw"
              ? "Mado can't read camera RAW yet, so it can't make this one for a screen or give it a look."
              : "Mado can't open this picture, so it can't make it for a screen or give it a look."}
          </p>
        ) : props.tool === "looks" ? (
          <LooksTab
            picture={props.picture}
            step={props.look}
            onStep={props.onLook}
            onPoint={props.onPoint}
            recipe={props.recipe}
            plan={plan}
            settling={props.settling}
          />
        ) : (
          <SizeTab
            picture={props.picture}
            chosen={props.size}
            onChosen={props.onSize}
            recipe={props.recipe}
            plan={props.plan}
            saving={plan}
            settling={props.settling}
          />
        )}
      </div>
    </aside>
  );
}
