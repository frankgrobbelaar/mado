import { EngineProblem } from "@/components/engine-problem";
import { TitleBar } from "@/components/shell/title-bar";
import { useHealth, useSettings, useTools } from "@/lib/engine";
import { ToolsStep } from "./tools-step";

/** First run: the tools Mado needs, fetched once, and then Home. More steps join as Mado is
 * built. */
export function SetupPage() {
  // Everything the step shows, so one place can say when the engine couldn't give it.
  const queries = [useHealth(), useSettings(), useTools()];

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      <TitleBar title="Mado setup" />
      <div className="flex-1 overflow-y-auto">
        <main className="mx-auto flex w-full max-w-250 flex-col gap-7 px-6 pt-6 pb-16">
          <header className="flex animate-fade-up flex-col gap-2">
            <span className="type-eyebrow">First run</span>
            <h1 className="font-extrabold text-44 leading-[1.05] tracking-[-0.03em]">
              Welcome to Mado
            </h1>
            <p className="max-w-170 text-17 text-fg-muted">
              One quick step. Nothing on this PC changes until you review it.
            </p>
          </header>

          <EngineProblem queries={queries} />
          <ToolsStep />

          <p className="text-13 text-fg-faint">
            Mado never uploads your pictures. It only goes online to fetch its tools and to check
            for updates.
          </p>
        </main>
      </div>
    </div>
  );
}
