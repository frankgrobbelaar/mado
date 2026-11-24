import { CheckCircle2, Info, MonitorOff } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router";
import { EngineProblem } from "@/components/engine-problem";
import { type Taken, useClaim } from "@/components/shell/claim";
import { useStatusNote } from "@/components/shell/status-note";
import { Loading, Skeleton } from "@/components/skeleton";
import { Button } from "@/components/ui/button";
import { Segmented } from "@/components/ui/segmented";
import {
  type Layout,
  type PictureChoice,
  type Quality,
  type Shape,
  type StudioState,
  useArrange,
  useCancelWallpaper,
  useChooseWallpaper,
  useLetGoOfWallpaper,
  usePutBack,
  useSetWallpaper,
  useStudio,
} from "@/lib/engine";
import { useSettled } from "@/lib/settled";
import { EveryDay } from "./every-day";
import { choiceFor, Monitors, type Moving } from "./monitors";
import { PickCard } from "./pick-card";
import { SaveCard } from "./save-card";
import { ChoiceTools, Chosen, Foot, NeedsFor, NoMonitors, Note, type Tab, Tabs } from "./tools";

const LAYOUTS = [
  { value: "each", label: "One for each" },
  { value: "across", label: "One across all" },
] as const;

type Change = Partial<{
  shape: Shape;
  quality: Quality | null;
  x: number | null;
  y: number | null;
  zoom: number;
}>;

/**
 * The wallpaper studio, a place in the rail: the owner's monitors drawn as Windows arranges them,
 * a picture for each (or one laid across them all, a gap left for the bezels), each part made at
 * exactly its monitor's pixels as the Size tab makes a picture, then set as Windows' own wallpaper
 * or saved as pictures; and every day's change from the favourites, with the owner's own wallpaper
 * kept and put back. A picture dropped on the window or pasted goes to the monitor picked; one sent
 * from a picture's page ("Make it a wallpaper") too.
 */
export function WallpaperPage() {
  const studio = useStudio();
  const [tab, setTab] = useState<Tab>("now");
  const [selected, setSelected] = useState<string | null>(null);
  const [moving, setMoving] = useState<Moving | null>(null);
  const [picking, setPicking] = useState(false);
  const [saving, setSaving] = useState(false);
  const [told, setTold] = useState<string[] | null>(null);
  // The gap and the zoom as they're dragged; the engine's once they settle.
  const [gapAsked, setGapAsked] = useState<number | null>(null);
  const [zoomAsked, setZoomAsked] = useState<{ monitor: string | null; zoom: number } | null>(null);
  const choose = useChooseWallpaper();
  const arrange = useArrange();
  const letGo = useLetGoOfWallpaper();
  const setIt = useSetWallpaper();
  const stop = useCancelWallpaper();
  const putBack = usePutBack();
  const [query] = useSearchParams();
  const navigate = useNavigate();
  const data = studio.data;
  const across = data?.layout === "across";
  const main = data?.monitors.find((each) => each.main) ?? data?.monitors[0] ?? null;
  // The monitor picked: the one clicked while it's connected, else the main one.
  const picked = data?.monitors.find((each) => each.key === selected) ?? main;
  const forKey = across ? null : (picked?.key ?? null);
  const choice = !data
    ? null
    : across
      ? (data.choices.find((each) => each.monitor === null) ?? null)
      : picked
        ? choiceFor(data, picked)
        : null;
  useStatusNote(
    data?.monitors.length
      ? `${data.monitors.length} ${data.monitors.length === 1 ? "monitor" : "monitors"} · ${data.width} × ${data.height}`
      : null,
  );

  function send(owner: PictureChoice, next: Change) {
    choose.mutate({
      path: "/wallpaper/pictures",
      body: {
        monitor: owner.monitor,
        pictureId: owner.picture.id,
        shape: next.shape ?? owner.shape,
        x: next.x !== undefined ? next.x : owner.x,
        y: next.y !== undefined ? next.y : owner.y,
        zoom: next.zoom ?? owner.zoom,
        quality: next.quality !== undefined ? next.quality : owner.quality,
      },
    });
  }

  function pick(picture: Taken | { id: number }) {
    if (!data?.monitors.length) return;
    setMoving(null);
    setZoomAsked(null);
    choose.mutate({
      path: "/wallpaper/pictures",
      body: { monitor: forKey, pictureId: picture.id, shape: "crop" },
    });
  }

  // A picture dropped on the window or pasted is the studio's, for the monitor picked.
  useClaim({
    take: pick,
    title: across || !picked ? "Drop it on your monitors" : `Drop it on ${picked.name}`,
    body: across
      ? "One picture, laid across them all, each part made at exactly its pixels."
      : "One picture, made at exactly its monitor's pixels.",
  });

  // A picture sent from its page ("Make it a wallpaper"): chosen once there are monitors to make
  // it for, then the address forgets it.
  const sent = Number(query.get("picture"));
  const took = useRef<number | null>(null);
  useEffect(() => {
    if (!data?.monitors.length || !Number.isInteger(sent) || sent <= 0 || took.current === sent)
      return;
    took.current = sent;
    pick({ id: sent });
    void navigate("/wallpaper", { replace: true });
  });

  // The gap, once it stops moving; once only, whatever the engine answers.
  const gapSettled = useSettled(gapAsked, 250);
  const gapSent = useRef<number | null>(null);
  useEffect(() => {
    if (!data || gapSettled === null || gapSettled === gapSent.current) return;
    gapSent.current = gapSettled;
    arrange.mutate({ path: "/wallpaper", body: { layout: data.layout, gap: gapSettled } });
  });

  // The zoom, once it stops moving.
  const zoomSettled = useSettled(zoomAsked, 250);
  const zoomSent = useRef<typeof zoomAsked>(null);
  useEffect(() => {
    if (!data || zoomSettled === null || zoomSettled === zoomSent.current) return;
    zoomSent.current = zoomSettled;
    const owner = data.choices.find((each) => each.monitor === zoomSettled.monitor);
    if (owner && owner.zoom !== zoomSettled.zoom) send(owner, { zoom: zoomSettled.zoom });
  });

  if (!data) {
    return (
      <div className="flex flex-col gap-4 pt-4.5">
        <h1 className="type-title">Wallpaper</h1>
        <EngineProblem queries={[studio]} />
        <Loading label="Looking at your monitors" queries={[studio]}>
          <Skeleton className="h-80 rounded-8" />
        </Loading>
      </div>
    );
  }

  const parts = across ? data.parts : data.parts.filter((each) => each.monitor === forKey);
  const away = data.choices.filter((each) => !each.connected);
  const making = data.making;
  const busy = making?.state === "waiting" || making?.state === "making";
  const needs = [...new Set(data.parts.flatMap((each) => each.needs))];
  const forWhat = across
    ? `All monitors · ${data.width} × ${data.height}`
    : picked
      ? `${picked.name} · ${picked.width} × ${picked.height}`
      : "";
  const gap = gapAsked ?? data.gap;
  const zoom =
    zoomAsked && choice && zoomAsked.monitor === choice.monitor
      ? zoomAsked.zoom
      : (choice?.zoom ?? 1);
  const shown: StudioState =
    zoomAsked && choice && zoomAsked.monitor === choice.monitor
      ? {
          ...data,
          choices: data.choices.map((each) => (each === choice ? { ...each, zoom } : each)),
        }
      : data;

  function cut(next: Moving) {
    const owner = data?.choices.find((each) => each.monitor === next.monitor);
    if (!owner) return;
    setMoving(next);
    setZoomAsked(null);
    choose.mutate(
      {
        path: "/wallpaper/pictures",
        body: {
          monitor: next.monitor,
          pictureId: owner.picture.id,
          shape: owner.shape,
          x: next.cut.x,
          y: next.cut.y,
          zoom: next.cut.zoom,
          quality: owner.quality,
        },
      },
      { onSettled: () => setMoving((now) => (now === next ? null : now)) },
    );
  }

  return (
    <div className="-mx-7 -mb-12 flex h-[calc(100vh-4.25rem)]">
      <div className="flex min-w-0 flex-1 flex-col gap-3.5 overflow-y-auto px-5.5 pt-4 pb-4">
        <header className="flex flex-wrap items-center gap-x-3.5 gap-y-2.5">
          <div className="flex min-w-0 flex-col gap-0.5">
            <h1 className="type-title">Wallpaper</h1>
            {data.monitors.length > 0 && (
              <p className="font-mono text-12 text-fg-muted">
                {data.monitors.length} {data.monitors.length === 1 ? "monitor" : "monitors"} ·{" "}
                {data.width} × {data.height} · as Windows arranges them
              </p>
            )}
          </div>
          {data.monitors.length > 1 && (
            <Segmented
              label="Layout"
              value={data.layout}
              options={LAYOUTS}
              onChange={(layout: Layout) => {
                gapSent.current = gap; // sent with it, so a gap still settling isn't sent again
                arrange.mutate({ path: "/wallpaper", body: { layout, gap } });
              }}
              className="ml-auto"
            />
          )}
        </header>
        <p className="max-w-3xl text-13 text-fg-muted leading-normal">
          Each monitor's part is made at exactly its pixels, then set as Windows' own wallpaper;
          your pictures and folders stay as they are. An app that draws its own desktop hides it.
          {data.choices.some((choice) => choice.picture.hdr) &&
            " Windows shows a wallpaper as an ordinary picture, so an HDR photo's extra brightness isn't kept in it."}
        </p>
        <EngineProblem queries={[studio]} />
        {data.monitors.length === 0 ? (
          <NoMonitors studio={data} onAgain={() => void studio.refetch()} />
        ) : (
          <>
            {away.length > 0 && (
              <Note icon={<MonitorOff size={16} aria-hidden="true" />}>
                {away.length === 1
                  ? "A monitor isn't connected: its picture waits for it"
                  : `${away.length} monitors aren't connected: their pictures wait for them`}
                , and Mado sets only what's connected.
              </Note>
            )}
            <div className="flex flex-1 flex-col justify-center rounded-8 bg-behind p-6">
              <Monitors
                studio={shown}
                selected={forKey}
                onSelect={setSelected}
                moving={moving}
                onMove={setMoving}
                onCut={cut}
              />
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <p className="text-13 text-fg-faint">
                {across
                  ? "Drop a picture on the window or paste one: it's laid across them all."
                  : picked
                    ? `Drop a picture on the window or paste one: it goes on ${picked.name}.`
                    : null}
              </p>
              {data.yours.kept.length > 0 && (data.yours.showingMine || data.yours.slideshow) && (
                <Button
                  size="sm"
                  className="ml-auto"
                  disabled={putBack.isPending || busy}
                  onClick={() =>
                    putBack.mutate(
                      { path: "/wallpaper/put-back", body: {} },
                      { onSuccess: (back) => setTold(back.told) },
                    )
                  }
                >
                  Put back your own wallpaper
                </Button>
              )}
            </div>
            {told && (
              <Note
                icon={<CheckCircle2 size={16} aria-hidden="true" />}
                onClose={() => setTold(null)}
              >
                {told.length
                  ? `Your own wallpaper is back, as far as Windows allows. ${told.join(" ")}`
                  : "Your own wallpaper is back on each monitor, and the daily change is off."}
              </Note>
            )}
            {putBack.isError && (
              <p role="alert" className="text-13 text-broken-fg">
                {putBack.error.message}
              </p>
            )}
          </>
        )}
      </div>
      <aside
        aria-label="Studio"
        className="sticky top-0 flex h-[calc(100vh-4.25rem)] w-100 shrink-0 flex-col gap-3.5 overflow-y-auto border-chrome-edge border-l bg-surface px-4.5 pt-3.5 pb-4"
      >
        <Tabs tab={tab} onTab={setTab} />
        <div
          role="tabpanel"
          id="studio-panel"
          aria-labelledby={`studio-${tab}`}
          className="flex min-h-0 flex-1 flex-col gap-4"
        >
          {tab === "daily" ? (
            <EveryDay daily={data.daily} monitors={data.monitors.length} />
          ) : (
            <>
              {forWhat && <span className="type-eyebrow">{forWhat}</span>}
              {data.monitors.length > 0 && (
                <Chosen
                  choice={choice}
                  busy={choose.isPending}
                  onPick={() => setPicking(true)}
                  onLetGo={() =>
                    letGo.mutate({
                      path: forKey
                        ? `/wallpaper/pictures?monitor=${encodeURIComponent(forKey)}`
                        : "/wallpaper/pictures",
                    })
                  }
                />
              )}
              {choice && (
                <ChoiceTools
                  studio={data}
                  choice={choice}
                  parts={parts}
                  zoom={zoom}
                  onZoom={(next) => setZoomAsked({ monitor: choice.monitor, zoom: next })}
                  gap={gap}
                  onGap={setGapAsked}
                  onChange={(next) => send(choice, next)}
                />
              )}
              {needs.length > 0 && <NeedsFor ids={needs} />}
              {(data.slideshow || data.spotlight) && (
                <Note icon={<Info size={16} aria-hidden="true" />}>
                  {data.slideshow &&
                    "Windows' slideshow is on: setting Mado's wallpaper turns it off, and putting back your own starts it again. "}
                  {data.spotlight &&
                    "Windows spotlight is on: setting Mado's wallpaper turns it off; only Windows turns it on again, in Settings › Personalisation › Background."}
                </Note>
              )}
              {choose.isError && (
                <p role="alert" className="text-13 text-broken-fg">
                  {choose.error.message}
                </p>
              )}
              {data.monitors.length > 0 && (
                <Foot
                  studio={data}
                  ready={data.parts.length > 0 && needs.length === 0}
                  busy={busy || setIt.isPending}
                  onSet={() => setIt.mutate({ path: "/wallpaper/set" })}
                  onSave={() => setSaving(true)}
                  onStop={() => stop.mutate({ path: "/wallpaper/cancel" })}
                  stopping={stop.isPending}
                  problem={setIt.isError ? setIt.error.message : null}
                />
              )}
            </>
          )}
        </div>
      </aside>
      {picking && (
        <PickCard
          forWhat={forWhat}
          onPick={(picture) => {
            setPicking(false);
            pick(picture);
          }}
          onClose={() => setPicking(false)}
        />
      )}
      {saving && <SaveCard monitors={data.monitors.length} onClose={() => setSaving(false)} />}
    </div>
  );
}
