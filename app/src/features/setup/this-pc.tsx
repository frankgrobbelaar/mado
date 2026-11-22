import { usePc } from "@/lib/engine";

const GIB = 1024 ** 3;

/** This PC, on Setup's welcome, as Setup-Welcome draws it: its graphics card and memory, and
 * where Mado's AI tools will run. Settings › About says more. */
export function ThisPc() {
  const pc = usePc().data;
  if (!pc) return null;
  const memory = pc.card?.memory ? `${Math.round(pc.card.memory / GIB)} GB` : null;
  const onCard = pc.onCard !== false && pc.card !== null;
  return (
    <section
      aria-labelledby="this-pc"
      className="flex animate-fade-up flex-wrap items-center gap-x-7 gap-y-3 rounded-8 border border-edge bg-glass px-5 py-4"
    >
      <h2 id="this-pc" className="type-eyebrow">
        This PC
      </h2>
      {pc.card && (
        <span className="text-14">
          <span className="text-fg-muted">Graphics card</span>{" "}
          <span className="font-mono">
            {memory ?? pc.card.name}
            {pc.onCard ? " · DirectX 12" : ""}
          </span>
        </span>
      )}
      {pc.memory && (
        <span className="text-14">
          <span className="text-fg-muted">Memory</span>{" "}
          <span className="font-mono">{Math.round(pc.memory / GIB)} GB</span>
        </span>
      )}
      <span className="text-14 text-fg-muted">
        {pc.testing
          ? "Mado is testing what this PC's AI tools can do…"
          : onCard
            ? "Mado's AI tools will run on the card. A picture takes seconds; Settings › About says what each tool needs."
            : "Mado's AI tools will run on the processor: slower, so Fast goes first. Settings › About says more."}
      </span>
    </section>
  );
}
