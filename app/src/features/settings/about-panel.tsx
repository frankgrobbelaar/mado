import { useEngine, useHealth } from "@/lib/engine";
import { openDownloadsPage } from "@/lib/links";
import { updateStatus, useReadyUpdate } from "@/lib/updates";
import { Panel } from "./panel";

const LINK =
  "cursor-pointer text-accent-fg underline-offset-3 hover:text-accent-fg-hover hover:underline";

/** About Mado: this copy at a glance (engine, data folder, database and updates), its licence,
 * and whose work it stands on. */
export function AboutPanel() {
  const engine = useEngine();
  const health = useHealth();
  const update = useReadyUpdate();

  const engineText = { starting: "Starting…", ready: "Running", failed: "Not running" }[
    engine.state
  ];

  return (
    <Panel title="About Mado" note="窓, a window: a personal tool for one person's pictures.">
      <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-2.5 text-13">
        <dt className="text-fg-muted">Version</dt>
        <dd className="font-mono">{health.data?.version ?? "…"}</dd>
        <dt className="text-fg-muted">Engine</dt>
        <dd className="flex items-center gap-2">
          {engine.state === "starting" && (
            <span className="size-2 animate-pulse rounded-full bg-accent" aria-hidden="true" />
          )}
          {engineText}
        </dd>
        <dt className="text-fg-muted">Data folder</dt>
        <dd className="font-mono text-12 text-fg-soft [overflow-wrap:anywhere]">
          {health.data?.dataDir ?? "…"}
        </dd>
        <dt className="text-fg-muted">Database</dt>
        <dd>{health.data ? `Ready · schema version ${health.data.schemaVersion}` : "…"}</dd>
        <dt className="text-fg-muted">Updates</dt>
        <dd>{updateStatus(update)}</dd>
        <dt className="text-fg-muted">Versions</dt>
        <dd>
          <button type="button" className={LINK} onClick={() => void openDownloadsPage()}>
            Every version and what changed
          </button>
        </dd>
        <dt className="text-fg-muted">Licence</dt>
        <dd>MIT. Anyone may fork it; the repo takes no contributions.</dd>
      </dl>
      <p className="text-13 text-fg-muted">
        Mado looks after pictures already on this PC. Everything it does happens here: nothing is
        uploaded, and it never searches for or downloads pictures.
      </p>
      <p className="text-13 text-fg-muted">
        Mado stands on others' work, ffmpeg first. THIRD-PARTY-NOTICES.txt, next to Mado, lists
        every part with its licence.
      </p>
    </Panel>
  );
}
