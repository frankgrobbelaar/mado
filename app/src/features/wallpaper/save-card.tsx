import { FolderOpen } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
} from "@/components/ui/dialog";
import { Segmented } from "@/components/ui/segmented";
import { pickFolder } from "@/lib/dialogs";
import { type SaveFormat, useSaveWallpaper } from "@/lib/engine";

type What = "parts" | "whole";

const WHAT = [
  { value: "parts", label: "Each monitor's part" },
  { value: "whole", label: "One picture of them all" },
] as const;

const FORMATS = [
  { value: "PNG", label: "PNG" },
  { value: "JPEG", label: "JPEG" },
  { value: "WebP", label: "WebP" },
  { value: "AVIF", label: "AVIF" },
] as const;

/**
 * Saving the wallpaper as pictures, as any Save: new pictures in a folder the owner picks, named
 * after the picture they're from ("Harbour at dusk (Studio 27 wallpaper).png"), each in History.
 * Each monitor's part at its own pixels, or one picture of the whole arrangement.
 */
export function SaveCard(props: { monitors: number; onClose: () => void }) {
  const [what, setWhat] = useState<What>("parts");
  const [format, setFormat] = useState<SaveFormat>("PNG");
  const [folder, setFolder] = useState<string | null>(null);
  const save = useSaveWallpaper();
  return (
    <Dialog open onOpenChange={(open) => !open && props.onClose()}>
      <DialogContent className="w-[min(32rem,calc(100vw-2rem))]">
        <DialogHeader
          title="Save as pictures"
          description="New pictures in a folder you pick. Your wallpaper and Mado's copies stay as they are."
        />
        <DialogBody className="gap-4">
          {props.monitors > 1 && (
            <div className="flex flex-col gap-1.5">
              <span className="type-eyebrow">What</span>
              <Segmented label="What to save" value={what} options={WHAT} onChange={setWhat} />
            </div>
          )}
          <div className="flex flex-col gap-1.5">
            <span className="type-eyebrow">Where</span>
            <div className="flex flex-wrap items-center gap-2.5">
              {folder && <span className="min-w-0 truncate font-mono text-13">{folder}</span>}
              <Button
                size="sm"
                onClick={async () => {
                  const chosen = await pickFolder("Save the wallpaper's pictures in");
                  if (chosen) setFolder(chosen);
                }}
              >
                <FolderOpen size={15} aria-hidden="true" />
                {folder ? "Change…" : "Pick a folder…"}
              </Button>
            </div>
          </div>
          <div className="flex flex-col gap-1.5">
            <span className="type-eyebrow">Format</span>
            <Segmented label="Format" value={format} options={FORMATS} onChange={setFormat} />
            <span className="text-12 text-fg-faint">
              PNG keeps every pixel as Mado made it; JPEG, WebP and AVIF are smaller.
            </span>
          </div>
          {save.isError && (
            <p role="alert" className="text-13 text-broken-fg">
              {save.error.message}
            </p>
          )}
        </DialogBody>
        <DialogFooter>
          <Button variant="ghost" size="sm" onClick={props.onClose}>
            Cancel
          </Button>
          <Button
            variant="primary"
            size="sm"
            disabled={!folder || save.isPending}
            onClick={() =>
              save.mutate(
                { path: "/wallpaper/save", body: { what, folder, format } },
                {
                  onSuccess: props.onClose,
                },
              )
            }
          >
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
