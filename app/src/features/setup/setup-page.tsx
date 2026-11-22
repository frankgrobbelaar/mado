import { useState } from "react";
import { EngineProblem } from "@/components/engine-problem";
import { TitleBar } from "@/components/shell/title-bar";
import { useHealth, useScan, useSettings, useTools } from "@/lib/engine";
import { FoldersStep } from "./folders-step";
import { Steps } from "./parts";
import { ToolsStep } from "./tools-step";

/** First run: the tool Mado needs, fetched once; then the folders pictures live in (or not yet);
 * then Home. */
export function SetupPage() {
  const [step, setStep] = useState<"tools" | "folders">("tools");
  // Everything the steps show, so one place can say when the engine couldn't give it.
  const queries = [useHealth(), useSettings(), useTools()];
  useScan(); // what's found in the folders shows as it's found

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      <TitleBar title="Mado setup" />
      <div className="flex-1 overflow-y-auto">
        <main className="mx-auto flex w-full max-w-250 flex-col gap-7 px-6 pt-6 pb-16">
          <header className="flex animate-fade-up flex-col gap-2">
            <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
              <span className="type-eyebrow">First run</span>
              <span className="ml-auto">
                <Steps now={step} />
              </span>
            </div>
            {step === "tools" ? (
              <>
                <h1 className="type-display">Welcome to Mado</h1>
                <p className="max-w-170 text-16 text-fg-muted">
                  Two quick steps. Nothing on this PC changes until you review it.
                </p>
              </>
            ) : (
              <>
                <h1 className="type-display">Where do your pictures live?</h1>
                <p className="max-w-185 text-16 text-fg-muted">
                  Add the folders, in any layout. Each becomes part of your library. Mado reads the
                  pictures where they are and changes nothing until you say.
                </p>
              </>
            )}
          </header>

          <EngineProblem queries={queries} />
          {step === "tools" ? (
            <ToolsStep onNext={() => setStep("folders")} />
          ) : (
            <FoldersStep onBack={() => setStep("tools")} />
          )}

          <p className="text-13 text-fg-faint">
            Mado never uploads your pictures. It only goes online to fetch its tools and to check
            for updates.
          </p>
        </main>
      </div>
    </div>
  );
}
