import { Download, Monitor, Plus, Scissors } from "lucide-react";
import { DropdownMenu } from "radix-ui";
import type { ReactNode } from "react";
import { Link } from "react-router";
import { Arrow } from "@/components/arrow";
import { Button } from "@/components/ui/button";
import type { BatchStep, KeptRecipe, StepWords } from "@/lib/engine";
import { cn } from "@/lib/utils";

/** The three circles of a look, as the Batch board draws its step. */
export function LookIcon({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      aria-hidden="true"
      className={cn("size-5", className)}
    >
      <circle cx="9" cy="10" r="5" />
      <circle cx="15" cy="10" r="5" />
      <circle cx="12" cy="15" r="5" />
    </svg>
  );
}

const ICONS: Record<string, ReactNode> = {
  cutout: <Scissors size={20} strokeWidth={1.6} aria-hidden="true" />,
  size: <Monitor size={20} strokeWidth={1.6} aria-hidden="true" />,
  look: <LookIcon />,
  save: <Download size={20} strokeWidth={1.6} aria-hidden="true" />,
};

/**
 * A batch's steps, in the order they're made, as the Batch board draws them: each with what it
 * does and Change, then Save; "Add a step" for one it hasn't yet; and, when `recipes` are given,
 * "or start from" each recipe, the one it's from pressed, with the Recipes page beside them.
 */
export function StepsPanel(props: {
  steps: BatchStep[];
  /** The steps, then the save, in words. */
  words: StepWords[];
  onChange: (kind: string) => void;
  onAdd: (kind: BatchStep["step"]) => void;
  /** What its header says on its right: "From the recipe Holiday prints". */
  aside?: ReactNode;
  recipes?: KeptRecipe[];
  recipe?: number | null;
  onRecipe?: (recipe: KeptRecipe) => void;
}) {
  const { steps, words } = props;
  const missing = (["cutout", "size", "look"] as const).filter(
    (kind) => !steps.some((step) => step.step === kind),
  );
  return (
    <section
      aria-labelledby="steps"
      className="flex animate-fade-up flex-col rounded-8 border border-edge bg-glass"
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 px-4.5 pt-3.5 pb-2.5">
        <h2 id="steps" className="type-eyebrow">
          Steps, in order
        </h2>
        {props.aside && <span className="ml-auto text-12 text-fg-muted">{props.aside}</span>}
      </div>
      {steps.length === 0 && (
        <p className="border-edge border-t px-4.5 py-3.5 text-13 text-fg-muted leading-normal">
          Pick what to do: cut out their subject, make them right for a screen or a print, give them
          a look, or start from a recipe.
        </p>
      )}
      <ol>
        {words.map((said, at) => (
          <li
            key={said.kind}
            className="flex items-center gap-3.5 border-edge border-t px-4.5 py-3"
          >
            <span className="w-5.5 font-mono text-13 text-fg-faint">{at + 1}</span>
            <span className="text-fg-muted">{ICONS[said.kind] ?? ICONS.save}</span>
            <span className="flex min-w-0 flex-1 flex-col gap-0.5">
              <span className="font-semibold text-15">{said.title}</span>
              <span className="text-13 text-fg-muted">{said.detail}</span>
            </span>
            <Button
              size="sm"
              className="bg-transparent font-medium"
              aria-label={`Change ${said.title.toLowerCase()}`}
              onClick={() => props.onChange(said.kind)}
            >
              Change
            </Button>
          </li>
        ))}
      </ol>
      <div className="flex flex-wrap items-center gap-2 border-edge border-t px-4.5 py-3">
        {missing.length === 0 ? (
          <Button
            size="sm"
            disabled
            title="It has every step Mado makes so far"
            className="border-dash border-dashed bg-transparent font-medium"
          >
            <Plus size={15} aria-hidden="true" />
            Add a step
          </Button>
        ) : (
          <DropdownMenu.Root>
            <DropdownMenu.Trigger asChild>
              <Button size="sm" className="border-dash border-dashed bg-transparent font-medium">
                <Plus size={15} aria-hidden="true" />
                Add a step
              </Button>
            </DropdownMenu.Trigger>
            <DropdownMenu.Portal>
              <DropdownMenu.Content
                align="start"
                sideOffset={4}
                className="z-60 flex min-w-52 flex-col rounded-8 border border-edge bg-dialog p-1.5 text-13 shadow-float"
              >
                {missing.map((kind) => (
                  <DropdownMenu.Item
                    key={kind}
                    onSelect={() => props.onAdd(kind)}
                    className="flex cursor-pointer items-center gap-2 rounded-6 px-3 py-2 font-semibold text-fg-soft outline-none data-highlighted:bg-tint/6 data-highlighted:text-fg"
                  >
                    {kind === "size"
                      ? "Make it for a screen"
                      : kind === "look"
                        ? "A look"
                        : "Cut out the subject"}
                  </DropdownMenu.Item>
                ))}
              </DropdownMenu.Content>
            </DropdownMenu.Portal>
          </DropdownMenu.Root>
        )}
        {props.recipes && props.recipes.length > 0 && (
          <>
            <span className="text-13 text-fg-muted">or start from</span>
            {props.recipes.map((recipe) => (
              <button
                key={recipe.id}
                type="button"
                aria-pressed={recipe.id === props.recipe}
                onClick={() => props.onRecipe?.(recipe)}
                className={cn(
                  "press inline-flex h-8 cursor-pointer items-center rounded-full border px-2.75 font-medium text-12",
                  recipe.id === props.recipe
                    ? "border-accent bg-accent/10 text-fg"
                    : "border-field-edge text-fg-muted hover:bg-tint/6 hover:text-fg",
                )}
              >
                {recipe.name}
              </button>
            ))}
          </>
        )}
        {props.recipes && (
          <Link
            to="/recipes"
            className="ml-auto text-13 text-accent-fg underline underline-offset-3 hover:text-accent-fg-hover"
          >
            Recipes
          </Link>
        )}
      </div>
    </section>
  );
}

/** A recipe's line, as the Recipes and Queue boards draw it: its steps then its save, each a
 * chip, a look's strength in the accent. */
export function RecipeLine({ words, strong }: { words: StepWords[]; strong?: boolean }) {
  return (
    <span className="flex flex-wrap items-center gap-1.5 text-12">
      {words.map((said, at) => (
        <span key={said.kind} className="contents">
          {at > 0 && (
            <span className="text-fg-faint">
              <Arrow said="then" />
            </span>
          )}
          <span className={cn("rounded-4 bg-raised px-2 py-1", strong && "font-semibold text-13")}>
            {said.chip}
            {said.amount && (
              <>
                {" "}
                <span className="font-mono text-accent-fg">{said.amount}</span>
              </>
            )}
          </span>
        </span>
      ))}
    </span>
  );
}
