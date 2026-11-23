import { Info } from "lucide-react";
import { Navigate, NavLink, useParams } from "react-router";
import { EngineProblem } from "@/components/engine-problem";
import { Toggle } from "@/components/toggle";
import { Button } from "@/components/ui/button";
import { type DataSizes, useDataSizes, useHealth } from "@/lib/engine";
import { size } from "@/lib/format";
import { openDownloadsPage } from "@/lib/links";
import { useLook, useSetLook } from "@/lib/look";
import {
  useKeepInTray,
  useOpenInExplorer,
  useSetKeepInTray,
  useSetOpenInExplorer,
  useSetStartWithWindows,
  useStartWithWindows,
} from "@/lib/startup";
import { updateStatus, useInstallUpdate, useReadyUpdate } from "@/lib/updates";
import { cn } from "@/lib/utils";
import { AboutPanel } from "./about-panel";
import { BackupsPanel } from "./backups-panel";
import { ExportPanel } from "./export-panel";
import { LookChoice } from "./look-choice";
import { Panel } from "./panel";
import { ManyAtOncePanel, SavingPanel } from "./saving-panel";
import { SearchPanel } from "./search-panel";
import { SetAsidePanel } from "./set-aside-panel";
import { ThisPcPanel, ToolsPanel } from "./this-pc-panel";
import { WhereItLives } from "./where-it-lives";

const SECTIONS = [
  { key: "general", label: "General" },
  { key: "data", label: "Your data" },
  { key: "updates", label: "Updates" },
  { key: "about", label: "About" },
] as const;

type Section = (typeof SECTIONS)[number]["key"];

/** Settings: how Mado looks and starts, Mado's data, updates and what Mado is made of. */
export function SettingsPage() {
  const { section } = useParams();
  const known = SECTIONS.find((each) => each.key === section);
  if (!known) return <Navigate to="/settings/general" replace />;
  return (
    <>
      <h1 className="page-top type-title animate-fade-up">Settings</h1>
      <div className="@container flex flex-wrap items-start gap-5">
        {/* Beside the sections (not above them), it stays put while they scroll: under the
            page's title (6 px, the title's 35.2 px and the 32 px gap). */}
        <nav
          aria-label="Settings"
          className="flex flex-[0_1_220px] animate-fade-up flex-col gap-1 @min-[800px]:sticky @min-[800px]:top-[4.575rem]"
        >
          {SECTIONS.map(({ key, label }) => (
            <NavLink
              key={key}
              to={`/settings/${key}`}
              className={({ isActive }) =>
                cn(
                  "press flex min-h-11 items-center justify-between rounded-6 px-3.5 font-semibold text-14",
                  isActive ? "bg-raised text-fg" : "text-fg-muted hover:bg-tint/6",
                )
              }
            >
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="flex min-w-0 flex-[999_1_560px] flex-col gap-5">
          <Content section={known.key} />
        </div>
      </div>
    </>
  );
}

function Content({ section }: { section: Section }) {
  switch (section) {
    case "general":
      return <General />;
    case "data":
      return <YourData />;
    case "updates":
      return <Updates />;
    case "about":
      return (
        <>
          <AboutPanel />
          <ThisPcPanel />
          <ToolsPanel />
        </>
      );
  }
}

function General() {
  const start = useStartWithWindows();
  const change = useSetStartWithWindows();
  const keep = useKeepInTray();
  const changeKeep = useSetKeepInTray();
  const look = useLook();
  const changeLook = useSetLook();
  const explorer = useOpenInExplorer();
  const changeExplorer = useSetOpenInExplorer();
  const problem =
    change.error ??
    start.error ??
    changeKeep.error ??
    keep.error ??
    changeExplorer.error ??
    explorer.error ??
    changeLook.error ??
    look.error;
  return (
    <>
      <Panel title="General">
        <LookChoice
          value={look.data ?? "windows"}
          onChange={(chosen) => changeLook.mutate(chosen)}
        />
        <Toggle
          label="Start Mado when Windows starts"
          text="It waits in the tray from when you sign in, so the nightly backup carries on, and it tells you what it finished."
          checked={start.data ?? false}
          onChange={(on) => change.mutate(on)}
        />
        <Toggle
          label="Keep Mado running when you close the window"
          text="Closing the window leaves Mado in the tray, still at work; quit from there. Off, closing the window quits Mado."
          checked={keep.data ?? false}
          onChange={(on) => changeKeep.mutate(on)}
        />
        <Toggle
          label="Open in Mado in File Explorer"
          text="Right-click pictures or a folder to open them here (on Windows 11, under Show more options), and Mado is in Open with. Which app opens a picture stays yours to choose."
          checked={explorer.data ?? true}
          onChange={(on) => changeExplorer.mutate(on)}
        />
        {problem && (
          <p role="alert" className="text-13 text-broken-fg">
            {String(problem)}
          </p>
        )}
      </Panel>
      <SavingPanel />
      <ManyAtOncePanel />
      <SearchPanel />
    </>
  );
}

const PARTS: {
  key: Exclude<keyof DataSizes, "folder">;
  label: string;
  note: string;
  color: string;
  /** Shown only while it holds something. */
  some?: boolean;
}[] = [
  { key: "database", label: "Database", note: "mado.db, one SQLite file", color: "bg-accent" },
  { key: "backups", label: "Backups", note: "last 7 nights", color: "bg-line-strong" },
  { key: "cache", label: "Cache", note: "can be made again", color: "bg-waiting" },
  { key: "tools", label: "Tools", note: "ffmpeg, AI models", color: "bg-line-strong" },
  { key: "logs", label: "Logs", note: "kept 30 days", color: "bg-control" },
  {
    key: "pasted",
    label: "Pasted",
    note: "a month after last opened",
    color: "bg-fg-faint",
    some: true,
  },
  {
    key: "wallpapers",
    label: "Wallpapers",
    note: "showing now and the last 3 days'",
    color: "bg-dash",
    some: true,
  },
  {
    key: "search",
    label: "Search",
    note: "read again when it's lost",
    color: "bg-fg-soft",
    some: true,
  },
];

function YourData() {
  const sizes = useDataSizes();
  const found = sizes.data;
  return (
    <>
      <EngineProblem queries={[sizes]} />
      <WhereItLives found={found ?? null}>
        {found && <Breakdown sizes={found} />}
        <p className="text-13 text-fg-muted">
          What Mado knows lives in one database file. There's no server to install, nothing listens
          beyond this PC, and none of it is uploaded.
        </p>
      </WhereItLives>
      <div className="flex flex-wrap items-stretch gap-5">
        <BackupsPanel className="flex-[1_1_300px]" />
        <ExportPanel />
      </div>
      <SetAsidePanel />
      <p className="flex items-start gap-2.5 rounded-8 border border-tint/14 border-dashed px-5 py-4 text-13 text-fg-soft">
        <Info size={16} aria-hidden="true" className="mt-0.5 shrink-0 text-fg-muted" />
        Uninstalling asks you to export first, and keeps this folder unless you choose to delete it.
        Your pictures are never touched.
      </p>
    </>
  );
}

function Breakdown({ sizes }: { sizes: DataSizes }) {
  const parts = PARTS.filter((part) => !part.some || sizes[part.key] > 0);
  const total = parts.reduce((sum, part) => sum + sizes[part.key], 0) || 1;
  return (
    <>
      <div aria-hidden="true" className="flex h-3 gap-0.5 overflow-hidden rounded-6 bg-track">
        {parts.map((part) => (
          <span
            key={part.key}
            className={cn("h-full animate-grow-x origin-left", part.color)}
            style={{ width: `${(sizes[part.key] / total) * 100}%` }}
          />
        ))}
      </div>
      <dl className="grid grid-cols-[repeat(auto-fit,minmax(140px,1fr))] gap-3">
        {parts.map((part) => (
          <div key={part.key} className="flex flex-col gap-0.5">
            <dt className="inline-flex items-center gap-1.5 text-12 text-fg-muted">
              <span aria-hidden="true" className={cn("size-2 rounded-2", part.color)} />
              {part.label}
            </dt>
            <dd className="font-semibold text-14">{size(sizes[part.key])}</dd>
            <dd className="font-mono text-11 text-fg-faint">{part.note}</dd>
          </div>
        ))}
      </dl>
    </>
  );
}

/** This copy's version, where the update check stands, and checking now rather than waiting for
 * the daily check. A version found can be installed from here too, though its card was put off. */
function Updates() {
  const health = useHealth();
  const update = useReadyUpdate();
  const install = useInstallUpdate();
  return (
    <Panel
      title="Updates"
      note="Mado looks for a new version when it starts and once a day, and downloads it in the background. When one is ready, it shows what's new and asks before restarting."
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <span className="flex flex-col gap-0.5">
          <span className="text-14">
            This is Mado <span className="font-mono">{health.data?.version ?? "…"}</span>
          </span>
          <span role="status" className="text-13 text-fg-muted">
            {updateStatus(update)}
          </span>
        </span>
        <div className="flex flex-wrap gap-2.5">
          {update.data ? (
            <Button variant="primary" disabled={install.isPending} onClick={() => install.mutate()}>
              Restart and update
            </Button>
          ) : (
            import.meta.env.PROD && (
              <Button disabled={update.isFetching} onClick={() => void update.refetch()}>
                Check for a new version
              </Button>
            )
          )}
          <Button onClick={() => void openDownloadsPage()}>Every version</Button>
        </div>
      </div>
      {install.isError && (
        <p role="alert" className="text-13 text-broken-fg">
          The update didn't start: {String(install.error)}
        </p>
      )}
    </Panel>
  );
}
