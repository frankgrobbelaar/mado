import type { UseQueryResult } from "@tanstack/react-query";
import { type KeyboardEvent, type ReactNode, useRef } from "react";
import type {
  DepthStep,
  EditStep,
  FixStep,
  LookStep,
  PictureDetails,
  Plan,
  Recipe,
  RestoreStep,
  SizeStep,
} from "@/lib/engine";
import { cn } from "@/lib/utils";
import { LooksTab } from "./looks-tab";
import { SizeTab } from "./size-tab";

export type Tool = "size" | "looks" | "edit" | "fix" | "depth";

const TOOLS = [
  { key: "size", label: "Size" },
  { key: "looks", label: "Looks" },
  { key: "edit", label: "Edit" },
  { key: "fix", label: "Fix" },
  { key: "depth", label: "Depth" },
] as const;

/**
 * The column beside the picture where its tools are, as the Picture boards draw it: Size, Looks
 * and Edit along its top, and Fix after them. Size makes the picture right for a screen or a
 * print, Looks gives it a look and finishing touches (on the whole picture or a part), Edit
 * picks parts with a click to erase, cut out or blur behind, Fix takes noise, blur, JPEG blocks
 * and darkness out, Depth blurs it as a lens would, hazes it with distance, keeps a band in focus
 * or makes a 3D photo; one Save on any of them makes them all (a 3D photo has its own).
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
  /** The edits made, which the Looks tab's small copies show; null for none. */
  edited: EditStep | null;
  /** The fixes chosen, settled: the Looks tab's small copies show a dark photo brightened. */
  fixed?: FixStep | null;
  /** Restoring chosen, settled, once its models are here: the Looks tab's small copies show it. */
  restored?: RestoreStep | null;
  /** The Looks tab's "Only on a part". */
  part: ReactNode;
  /** The Looks tab's painting styles. */
  styles?: ReactNode;
  /** The Edit tab, as the page holds its edits. */
  edit: ReactNode;
  /** The Fix tab, as the page holds its fixes. */
  fix: ReactNode;
  /** The Depth tab, as the page holds its depth tools and 3D photo. */
  depth: ReactNode;
  /** The depth tools chosen, settled: the Looks tab's picture shows them. */
  depthed?: DepthStep | null;
}) {
  const ready = props.picture.state === "ready";
  const tabs = useRef<Partial<Record<Tool, HTMLButtonElement | null>>>({});
  // The plan Save opens with is the one for the recipe as it is now, never the last one's.
  const plan = props.plan.isPlaceholderData ? null : (props.plan.data ?? null);

  /** The arrow keys, Home and End go from tool to tool, as tabs do. */
  function move(event: KeyboardEvent<HTMLDivElement>) {
    const open = TOOLS.map((tool) => tool.key) as Tool[];
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
                tabs.current[tool.key] = tab;
              }}
              id={`tool-${tool.key}`}
              type="button"
              role="tab"
              aria-selected={chosen}
              aria-controls={chosen ? "tool-panel" : undefined}
              tabIndex={chosen ? 0 : -1}
              onClick={() => props.onTool(tool.key)}
              className={cn(
                "press flex h-8 flex-1 items-center justify-center rounded-4 text-13",
                chosen
                  ? "bg-raised font-semibold text-fg"
                  : "cursor-pointer font-medium text-fg-muted hover:text-fg",
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
            {props.picture.state === "waiting"
              ? "This camera RAW waits for Mado's RAW reader: once it's here, it can be saved as it is, made for a screen, given a look, edited, fixed or given depth."
              : "Mado can't open this picture, so it can't make it for a screen, give it a look, edit it, fix it or give it depth."}
          </p>
        ) : props.tool === "edit" ? (
          props.edit
        ) : props.tool === "fix" ? (
          props.fix
        ) : props.tool === "depth" ? (
          props.depth
        ) : props.tool === "looks" ? (
          <LooksTab
            picture={props.picture}
            step={props.look}
            onStep={props.onLook}
            onPoint={props.onPoint}
            recipe={props.recipe}
            plan={plan}
            settling={props.settling}
            edit={props.edited}
            fix={props.fixed ?? null}
            restore={props.restored ?? null}
            part={props.part}
            styles={props.styles}
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
