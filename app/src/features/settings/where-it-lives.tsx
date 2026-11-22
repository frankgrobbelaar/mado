import { Button } from "@/components/ui/button";
import type { DataSizes } from "@/lib/engine";
import { openFolder, useExplorer } from "@/lib/explorer";
import { Panel } from "./panel";

/** Settings > Your data > Where your data lives: the folder, and opening it. */
export function WhereItLives(props: { found: DataSizes | null; children: React.ReactNode }) {
  const explorer = useExplorer();
  const { found } = props;
  if (!found) return null;
  return (
    <Panel
      title="Where your data lives"
      note={<span className="font-mono text-12 text-fg-soft">{found.folder}</span>}
      action={
        <Button onClick={() => explorer.run(() => openFolder(found.folder))}>Open folder</Button>
      }
    >
      {explorer.problem && (
        <p role="alert" className="text-13 text-broken-fg">
          {explorer.problem}
        </p>
      )}
      {props.children}
    </Panel>
  );
}
