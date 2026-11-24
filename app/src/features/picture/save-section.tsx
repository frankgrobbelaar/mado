import { createContext, type ReactNode, useContext, useState } from "react";
import { Button } from "@/components/ui/button";
import { type PictureDetails, type Plan, type Recipe, usePictureJobs } from "@/lib/engine";
import { JobCard } from "./job-card";
import { SaveDialog } from "./save-dialog";

/** Why every tab's Save waits, as the picture's page says it (its scratches' mask not yet checked:
 * nothing is filled till the owner has seen it); null when it needn't. */
export const SaveHeld = createContext<string | null>(null);

/**
 * The foot of a tool's column, on every tab alike: the job making the picture, and Save…, which
 * saves the whole recipe (what the tabs set, made by one Save), or the picture as it is when
 * nothing's chosen. Save waits while its plan is on its way, a model is still to download, or a
 * job is making this picture already.
 */
export function SaveSection(props: {
  picture: PictureDetails;
  recipe: Recipe | null;
  /** The plan for `recipe`, once it's here. */
  plan: Plan | null;
  /** The tab has something to save. */
  ready: boolean;
  /** Save is quiet, not the tab's one primary action: the Edit tab before its first edit. */
  quiet?: boolean;
  caption?: ReactNode;
}) {
  const { picture, recipe, plan } = props;
  const held = useContext(SaveHeld);
  const jobs = usePictureJobs(picture.id);
  const [saving, setSaving] = useState(false);
  const job = jobs.data?.[0];
  const working = job?.state === "queued" || job?.state === "running";
  // Any picture can be saved as it is, with nothing chosen on the tab.
  const ready = props.ready || plan?.asIs === true;
  const can =
    ready && recipe !== null && plan !== null && !plan.needs.length && !working && held === null;
  const caption = held ?? props.caption;
  return (
    <>
      {/* It stays at the column's foot, so Save is in reach however long the column grows; what
          scrolls under it fades out above it. */}
      <div className="sticky -bottom-4 -mx-4.5 mt-auto -mb-4 flex flex-col gap-2 bg-surface px-4.5 pt-2 pb-4 before:pointer-events-none before:absolute before:inset-x-0 before:-top-4 before:h-4 before:bg-linear-to-t before:from-surface before:to-transparent">
        {job && <JobCard job={job} />}
        <Button
          variant={props.quiet || (plan?.asIs && !picture.pasted) ? "secondary" : "primary"}
          disabled={!can}
          onClick={() => setSaving(true)}
        >
          Save…
        </Button>
        {caption && <p className="text-center text-13 text-fg-faint">{caption}</p>}
      </div>
      {saving && plan && recipe && (
        <SaveDialog
          picture={picture}
          plan={plan}
          recipe={recipe}
          onClose={() => setSaving(false)}
        />
      )}
    </>
  );
}
