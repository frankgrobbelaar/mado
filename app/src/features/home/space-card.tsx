import { type DriveSpace, useSpace } from "@/lib/engine";
import { size } from "@/lib/format";

/**
 * Space on the drive most of the library is on, as the Home board draws it: what's free, a bar of
 * what the pictures take of it, what they use, what quarantine holds there and what the queue
 * needs; then a line for each other drive the library uses. A drive that isn't connected says so.
 */
export function SpaceCard() {
  const space = useSpace();
  const [main, ...others] = space.data ?? [];
  if (space.isError) {
    return (
      <section
        aria-labelledby="space"
        className="flex flex-col gap-2 rounded-8 border border-edge bg-glass px-4.5 py-4"
      >
        <h2 id="space" className="type-eyebrow">
          Space
        </h2>
        <p className="text-13 text-fg-muted">
          Mado couldn't tell the room on your drives: {space.error.message}
        </p>
      </section>
    );
  }
  if (!main) return null;
  return (
    <section
      aria-labelledby="space"
      className="flex animate-fade-up flex-col gap-3 rounded-8 border border-edge bg-glass px-4.5 py-4"
    >
      <h2 id="space" className="type-eyebrow">
        Space on {main.drive}
      </h2>
      {main.connected && main.free !== null ? (
        <>
          <div className="flex items-baseline justify-between">
            <span className="font-medium font-mono text-30">{size(main.free)}</span>
            <span className="text-13 text-fg-muted">free</span>
          </div>
          <div
            role="img"
            aria-label={`${size(main.pictures)} of pictures, ${size(main.free)} free`}
            className="h-2 overflow-hidden rounded-4 bg-track"
          >
            <div
              className="h-full origin-left animate-grow-x bg-fg"
              style={{ width: `${share(main)}%` }}
            />
          </div>
          <p className="text-13 text-fg-muted leading-normal">
            Your pictures use <Figure value={size(main.pictures)} />
            {main.quarantine > 0 ? (
              <>
                ; quarantine holds <Figure value={size(main.quarantine)} />.
              </>
            ) : (
              "."
            )}
            {main.queue > 0 && (
              <>
                {" "}
                The queue needs <Figure value={size(main.queue)} /> more
                {main.queue > main.free ? ", more than is free." : "."}
              </>
            )}
          </p>
        </>
      ) : (
        <p className="text-13 text-fg-muted leading-normal">
          {main.drive} isn't connected. Its pictures stay in your library; connect it to see its
          room.
        </p>
      )}
      {others.length > 0 && (
        <ul className="flex flex-col gap-1 border-edge border-t pt-2.5 text-13">
          {others.map((drive) => (
            <li key={drive.drive} className="flex items-baseline justify-between gap-3">
              <span className="font-mono">{drive.drive}</span>
              <span className="text-right text-fg-muted">
                {drive.connected && drive.free !== null ? (
                  <>
                    <Figure value={size(drive.free)} /> free ·{" "}
                    <Figure value={size(drive.pictures)} /> of pictures
                  </>
                ) : (
                  "not connected"
                )}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function Figure({ value }: { value: string }) {
  return <span className="font-mono text-fg">{value}</span>;
}

/** The pictures' share of what they and the free room add up to, as the board's bar draws it. */
function share(drive: DriveSpace): number {
  const whole = drive.pictures + (drive.free ?? 0);
  if (drive.pictures <= 0 || whole <= 0) return 0;
  return Math.max(1, Math.round((drive.pictures / whole) * 1000) / 10);
}
