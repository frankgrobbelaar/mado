import type { UseQueryResult } from "@tanstack/react-query";
import type { PictureDetails, Plan, Recipe } from "@/lib/engine";
import { cn } from "@/lib/utils";
import { SizeTab } from "./size-tab";

const TOOLS = [
  { key: "size", label: "Size", ready: true },
  { key: "looks", label: "Looks", ready: false },
  { key: "edit", label: "Edit", ready: false },
] as const;

/**
 * The column beside the picture where its tools are, as the Picture boards draw it: Size, Looks
 * and Edit along its top. Size is built (making the picture right for a screen or a print, and
 * saving it); Looks and Edit come in Mado's next pieces, so they wait, quietly, in their place.
 */
export function ToolsColumn(props: {
  picture: PictureDetails;
  recipe: Recipe | null;
  onRecipe: (recipe: Recipe) => void;
  plan: UseQueryResult<Plan>;
}) {
  const ready = props.picture.state === "ready";
  return (
    <aside
      aria-label="Tools"
      className="sticky top-0 flex h-[calc(100vh-4.25rem)] w-100 shrink-0 flex-col gap-3.5 overflow-y-auto border-chrome-edge border-l bg-surface px-4.5 pt-3.5 pb-4"
    >
      <nav aria-label="Tool" className="flex rounded-6 bg-well p-0.75">
        {TOOLS.map((tool) => (
          <span
            key={tool.key}
            aria-current={tool.ready ? "page" : undefined}
            aria-disabled={tool.ready ? undefined : true}
            title={tool.ready ? undefined : `${tool.label} comes in Mado's next pieces`}
            className={cn(
              "flex h-8 flex-1 items-center justify-center rounded-4 text-13",
              tool.ready ? "bg-raised font-semibold text-fg" : "font-medium text-fg-faint",
            )}
          >
            {tool.label}
          </span>
        ))}
      </nav>
      {ready ? (
        <SizeTab
          picture={props.picture}
          recipe={props.recipe}
          onRecipe={props.onRecipe}
          plan={props.plan}
        />
      ) : (
        <p className="text-13 text-fg-muted leading-normal">
          {props.picture.state === "raw"
            ? "Mado can't read camera RAW yet, so it can't make this one for a screen."
            : "Mado can't open this picture, so it can't make it for a screen."}
        </p>
      )}
    </aside>
  );
}
