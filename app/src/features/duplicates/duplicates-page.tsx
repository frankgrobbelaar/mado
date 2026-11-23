import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { EmptyState, WindowIllustration } from "@/components/empty-state";
import { EngineProblem } from "@/components/engine-problem";
import { Loading, PanelSkeleton } from "@/components/skeleton";
import { Button } from "@/components/ui/button";
import { Segmented } from "@/components/ui/segmented";
import {
  type AsideDone,
  type DuplicateGroup,
  type DuplicateKind,
  type GroupPicture,
  type ShownGroup,
  useDuplicates,
  useKeep,
  useLibrary,
  useNotSame,
  useSetAside,
} from "@/lib/engine";
import { count, size } from "@/lib/format";
import { Compare } from "./compare";
import { GroupCard } from "./group-card";

/**
 * The review of duplicates and bursts, drawn from the Queue, History and Library pages: the
 * groups Mado found, each with the one it keeps marked (a click keeps another; ticks keep more
 * than one; "Not the same" lets a group go), and one primary action that sets aside the rest of
 * every group, saying how many and what it frees. A group can be set aside on its own too.
 * Nothing changes till the owner asks; what's set aside waits in quarantine for 30 days. Opened
 * from a tag in the Library (`?group=`), it opens at that group.
 */
export function DuplicatesPage() {
  const [kind, setKind] = useState<DuplicateKind>("all");
  const [query] = useSearchParams();
  const asked = Number(query.get("group"));
  const at = Number.isInteger(asked) && asked > 0 ? asked : null;
  const found = useDuplicates(kind, at);
  const library = useLibrary();
  const keep = useKeep();
  const notSame = useNotSame();
  const aside = useSetAside();
  const [done, setDone] = useState<AsideDone | null>(null);
  const [letGo, setLetGo] = useState(false);
  const [open, setOpen] = useState<{ group: DuplicateGroup; picture: GroupPicture } | null>(null);
  const first = found.data?.pages[0];
  // A group once only, though the list may shift between pages while Mado looks.
  const groups = [
    ...new Map(
      (found.data?.pages.flatMap((page) => page.groups) ?? []).map((group) => [group.key, group]),
    ).values(),
  ];
  const busy = keep.isPending || notSame.isPending || aside.isPending;
  const reached = at !== null && groups.some((group) => group.key === at);

  // Opened at a group: it comes into view once it's here.
  useEffect(() => {
    if (reached) document.getElementById(`group-${at}`)?.scrollIntoView({ block: "center" });
  }, [reached, at]);
  const total = first ? first.duplicates + first.bursts : 0;

  /** Sets aside the rest of these groups as shown, or of every group of the kind shown (as the
   * review last saw them: the engine sets nothing aside when they changed since). */
  function setAside(shown: ShownGroup[] | null) {
    setLetGo(false);
    aside.mutate(
      {
        path: "/duplicates/aside",
        body: shown ? { groups: shown } : { groups: null, kind, version: first?.version },
      },
      { onSuccess: setDone },
    );
  }

  function keepIn(group: DuplicateGroup, ids: number[]) {
    keep.mutate({
      path: `/duplicates/${group.key}/keep`,
      body: { keep: ids, members: group.pictures.map((each) => each.id) },
    });
  }

  return (
    <>
      <header className="page-top flex animate-fade-up flex-wrap items-center gap-x-4 gap-y-2.5">
        <h1 className="type-title">Duplicates and bursts</h1>
        {first && total > 0 && (
          <p className="text-14 text-fg-muted">
            <Figure value={count(total)} /> {total === 1 ? "group" : "groups"} ·{" "}
            <Figure value={count(first.pictures)} /> to set aside ·{" "}
            <Figure value={size(first.bytes)} />
          </p>
        )}
        {first && first.pictures > 0 && (
          <Button
            variant="primary"
            className="ml-auto"
            disabled={busy}
            onClick={() => setAside(null)}
          >
            Set aside {count(first.pictures)}, freeing {size(first.bytes)}
          </Button>
        )}
      </header>

      <EngineProblem queries={[found]} />
      {!first && (
        <Loading label="Loading duplicates and bursts" queries={[found]}>
          <PanelSkeleton rows={2} />
          <PanelSkeleton rows={2} />
        </Loading>
      )}

      {first && (
        <p className="-mt-3 max-w-180 text-13 text-fg-muted leading-normal">
          Mado keeps the sharpest of each, or the biggest copy; click another to keep it instead, or
          tick more than one. The rest wait in quarantine for 30 days, and History puts them back.
        </p>
      )}

      {first?.looking && <Looking looked={first.looking.looked} of={first.looking.of} />}
      {first?.putBack && !done && <PutBackNote at={first.putBack.at} />}
      {done && <Done done={done} />}
      {letGo && (
        <p role="status" className="text-13 text-fg-muted">
          Mado won't ask about those again, unless one of them changes.
        </p>
      )}
      {(keep.isError || notSame.isError || aside.isError) && (
        <p role="alert" className="text-13 text-broken-fg">
          {keep.error?.message ?? notSame.error?.message ?? aside.error?.message}
        </p>
      )}
      {first && first.away > 0 && (
        <p className="text-13 text-fg-muted">
          {count(first.away)} more {first.away === 1 ? "is" : "are"} on a drive that isn't
          connected: connect it to set {first.away === 1 ? "it" : "them"} aside too.
        </p>
      )}

      {first && total > 0 && (
        <Segmented
          label="Show"
          value={kind}
          onChange={setKind}
          className="self-start"
          options={[
            { value: "all", label: `All ${count(total)}` },
            { value: "duplicates", label: `Duplicates ${count(first.duplicates)}` },
            { value: "bursts", label: `Bursts ${count(first.bursts)}` },
          ]}
        />
      )}

      {first && total === 0 && !first.looking && (done || letGo) && (
        <EmptyState title="Nothing left to review" illustration={<WindowIllustration />}>
          What you set aside waits in quarantine for 30 days, and History puts it back. Mado looks
          at new pictures as they arrive.
        </EmptyState>
      )}
      {first && total === 0 && !first.looking && !done && !letGo && (
        <EmptyState title="No duplicates or bursts" illustration={<WindowIllustration />}>
          {library.data && library.data.pictures > 0
            ? `Mado looked at all ${count(library.data.pictures)} pictures and found none. It looks at new pictures as they arrive.`
            : "Mado looks for them once your pictures are read. Add a folder on Home to begin."}
        </EmptyState>
      )}
      {first && total === 0 && first.looking && (
        <p className="text-13 text-fg-muted">
          Nothing found yet. What Mado finds joins here as it looks.
        </p>
      )}
      {first && total > 0 && groups.length === 0 && (
        <p className="text-13 text-fg-muted">
          {kind === "bursts" ? "No bursts among them." : "No duplicates among them."}
        </p>
      )}

      {groups.map((group) => (
        <GroupCard
          key={group.key}
          group={group}
          marked={group.key === at}
          busy={busy}
          onKeep={(ids) => keepIn(group, ids)}
          onNotSame={() =>
            notSame.mutate(
              { path: `/duplicates/${group.key}/not-same` },
              {
                onSuccess: () => {
                  setDone(null);
                  setLetGo(true);
                },
              },
            )
          }
          onSetAside={() => setAside([shownOf(group)])}
          onOpen={(picture) => setOpen({ group, picture })}
        />
      ))}

      {found.hasNextPage && (
        <Button
          className="self-start"
          disabled={found.isFetchingNextPage}
          onClick={() => void found.fetchNextPage()}
        >
          {found.isFetchingNextPage ? "Loading more…" : "Show more"}
        </Button>
      )}

      {open && (
        <Compare
          group={groups.find((group) => group.key === open.group.key) ?? open.group}
          picture={open.picture}
          busy={busy}
          onKeep={(ids) =>
            keepIn(groups.find((group) => group.key === open.group.key) ?? open.group, ids)
          }
          onClose={() => setOpen(null)}
        />
      )}
    </>
  );
}

function Figure({ value }: { value: string }) {
  return <span className="font-mono text-fg">{value}</span>;
}

/** A group as the review shows it: its pictures, and the ones kept. */
function shownOf(group: DuplicateGroup): ShownGroup {
  return {
    key: group.key,
    members: group.pictures.map((each) => each.id),
    keep: group.pictures.filter((each) => each.keep).map((each) => each.id),
  };
}

/** Still looking: how far it's got, with what it's found so far below. */
function Looking({ looked, of }: { looked: number; of: number }) {
  const percent = of > 0 ? Math.round((looked / of) * 100) : 0;
  return (
    <section
      role="status"
      aria-label="Still looking"
      className="flex animate-fade-up flex-col gap-2.5 rounded-8 border border-edge bg-glass px-4.5 py-3.5"
    >
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="font-semibold text-14">Still looking</span>
        <span className="text-13 text-fg-muted">
          Looked at <span className="font-mono text-fg">{count(looked)}</span> of{" "}
          <span className="font-mono text-fg">{count(of)}</span>. What it finds joins here as it
          looks.
        </span>
      </div>
      <div
        role="progressbar"
        aria-label="Looking for duplicates and bursts"
        aria-valuenow={percent}
        aria-valuemin={0}
        aria-valuemax={100}
        className="h-1.5 overflow-hidden rounded-3 bg-track"
      >
        <div
          className="h-full bg-accent transition-[width] duration-320 ease-mado"
          style={{ width: `${percent}%` }}
        />
      </div>
    </section>
  );
}

/** Everything the latest review set aside was put back. */
function PutBackNote({ at }: { at: string }) {
  const day = new Date(at).toLocaleDateString("en-GB", { day: "numeric", month: "short" });
  return (
    <p role="status" className="text-13 text-fg-muted">
      Everything you set aside on {day} is back where it was, so its groups are here again. Not the
      same keeps a group out.
    </p>
  );
}

/** What setting aside did, and what it left as it was. */
function Done({ done }: { done: AsideDone }) {
  return (
    <>
      {done.pictures > 0 && (
        <p role="status" className="text-13 text-fg-muted">
          Set aside {count(done.pictures)} {done.pictures === 1 ? "picture" : "pictures"}, freeing{" "}
          {size(done.bytes)}. {done.pictures === 1 ? "It waits" : "They wait"} in quarantine for 30
          days;{" "}
          <Link to="/history" className="text-accent-fg underline underline-offset-3">
            History
          </Link>{" "}
          puts {done.pictures === 1 ? "it" : "them"} back.
        </p>
      )}
      {done.left.length > 0 && (
        <div role="alert" className="flex flex-col gap-1 text-13 text-broken-fg">
          <span>
            {done.left.length === 1
              ? "One was left as it is:"
              : `${count(done.left.length)} were left as they are:`}
          </span>
          {sentences(done.left.slice(0, 5)).map((each) => (
            <span key={each.key}>{each.why}</span>
          ))}
          {done.left.length > 5 && <span>And {count(done.left.length - 5)} more like them.</span>}
        </div>
      )}
    </>
  );
}

/** What was left as it was, each with a key of its own: two pictures of one name, in two
 * folders, can be left for the same reason. */
function sentences(left: AsideDone["left"]): { key: string; why: string }[] {
  const seen = new Map<string, number>();
  return left.map((each) => {
    const times = (seen.get(each.why) ?? 0) + 1;
    seen.set(each.why, times);
    return { key: `${each.why}#${times}`, why: each.why };
  });
}
