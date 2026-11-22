import { MadeUpPicture } from "@/components/made-up-picture";
import { Button } from "@/components/ui/button";

/** A library with no folders yet: what it's for, and adding the first, as Library-Empty draws
 * it. */
export function EmptyLibrary(props: {
  onAdd: () => void;
  adding: boolean;
  problem: string | null;
  className?: string;
}) {
  return (
    <section
      aria-labelledby="empty-library"
      className={`flex animate-fade-up items-center justify-center rounded-8 border border-dash border-dashed bg-surface px-6 py-10 ${props.className ?? ""}`}
    >
      <div className="flex max-w-130 flex-col items-center gap-3.5 text-center">
        <div aria-hidden="true" className="flex gap-2 opacity-90">
          <MadeUpPicture kind="alps" className="h-15.5 w-21 -rotate-4" />
          <MadeUpPicture kind="dunes" className="h-15.5 w-21 -translate-y-1.5" />
          <MadeUpPicture kind="aurora" className="h-15.5 w-21 rotate-4" />
        </div>
        <h2 id="empty-library" className="mt-1.5 font-semibold text-20">
          Your library is empty
        </h2>
        <p className="text-14 text-fg-muted leading-[1.55]">
          Add the folders your pictures live in. Mado reads them where they are, sorts them by the
          day they were taken, and changes nothing until you say.
        </p>
        <Button variant="primary" className="mt-1" disabled={props.adding} onClick={props.onAdd}>
          Add a folder
        </Button>
        {props.problem && (
          <p role="alert" className="text-13 text-broken-fg">
            {props.problem}
          </p>
        )}
        <p className="mt-1 text-13 text-fg-faint">
          Pictures from phones, cameras and scanners: JPEG, HEIC, RAW, PNG, TIFF and more.
        </p>
      </div>
    </section>
  );
}
