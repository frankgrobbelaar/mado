import { ChevronDown, ChevronRight, Plus } from "lucide-react";
import { type CSSProperties, type ReactNode, useState } from "react";
import { Link } from "react-router";
import { Button } from "@/components/ui/button";
import { type FolderNode, type LibraryFolder, type Shown, shownQuery } from "@/lib/engine";
import { count } from "@/lib/format";
import { cn } from "@/lib/utils";

const ROW =
  "press flex min-h-8 min-w-0 flex-1 items-center gap-2 rounded-6 py-1.5 pr-2 text-14 outline-offset-0";
// The lit row: raised, with a fine edge in the light (Aluminium) as the boards draw it.
const LIT = "bg-raised text-fg shadow-[0_0_0_1px_light-dark(var(--color-edge),transparent)]";
const UNLIT = "text-fg-muted hover:bg-tint/6 hover:text-fg";
const STEP = 16; // px each folder sits further in than the one holding it

/**
 * The Library's folders: All pictures and Favourites, then each library folder with the folders
 * inside it as a tree, and Add a folder. The folder showing stays lit, and the folders holding it
 * open.
 */
export function FolderTree(props: {
  folders: LibraryFolder[];
  /** The favourites there now, from outside the library too. */
  favourites: number;
  shown: Shown;
  onAdd: () => void;
  adding: boolean;
  problem: string | null;
}) {
  const { folders, shown } = props;
  // The owner's own opening and closing; otherwise the folders holding the one showing are open.
  const [toggled, setToggled] = useState<Map<string, boolean>>(new Map());
  const total = folders.reduce((sum, folder) => sum + folder.pictures, 0);
  const holdsShown = (folderId: number, dir: string) =>
    shown.folder === folderId &&
    (dir === "" || shown.dir === dir || shown.dir.startsWith(`${dir}/`));
  const isOpen = (folderId: number, dir: string) =>
    toggled.get(`${folderId}:${dir}`) ?? holdsShown(folderId, dir);
  const toggle = (folderId: number, dir: string) =>
    setToggled((before) => new Map(before).set(`${folderId}:${dir}`, !isOpen(folderId, dir)));
  // A folder opened afresh: no search, nor the pictures most like one.
  const to = (folder: number | null, dir = "") => {
    const query = shownQuery({ ...shown, favourites: false, folder, dir, q: "", like: null });
    return query ? `/library?${query}` : "/library";
  };
  const loved = `/library?${shownQuery({ ...shown, favourites: true, folder: null, dir: "", q: "", like: null })}`;
  const all = shown.folder === null && !shown.favourites;

  return (
    <nav aria-label="Folders" className="flex flex-col gap-0.5">
      <h2 className="type-eyebrow mx-2 mb-2">Folders</h2>
      <Link
        to={to(null)}
        aria-current={all ? "page" : undefined}
        className={cn(ROW, "pl-2", all ? LIT : UNLIT)}
      >
        All pictures
        <span className="ml-auto font-mono text-12">{count(total)}</span>
      </Link>
      <Link
        to={loved}
        aria-current={shown.favourites ? "page" : undefined}
        className={cn(ROW, "pl-2", shown.favourites ? LIT : UNLIT)}
      >
        Favourites
        <span className="ml-auto font-mono text-12">{count(props.favourites)}</span>
      </Link>
      {folders.map((folder) => (
        <Branch
          key={folder.id}
          name={folder.name}
          title={folder.available ? folder.path : `${folder.path}: its drive isn't connected`}
          pictures={folder.pictures}
          depth={0}
          dim={!folder.available}
          lit={shown.folder === folder.id && shown.dir === ""}
          open={isOpen(folder.id, "")}
          onToggle={() => toggle(folder.id, "")}
          to={to(folder.id)}
        >
          {folder.children.map((node) => (
            <Inside
              key={node.dir}
              node={node}
              depth={1}
              folderId={folder.id}
              shown={shown}
              isOpen={isOpen}
              toggle={toggle}
              to={to}
            />
          ))}
        </Branch>
      ))}
      <Button
        size="sm"
        className="mt-3 self-start bg-transparent px-2.5 font-medium"
        disabled={props.adding}
        onClick={props.onAdd}
      >
        <Plus size={15} aria-hidden="true" />
        Add a folder
      </Button>
      {props.problem && (
        <p role="alert" className="mx-2 mt-1 text-12 text-broken-fg">
          {props.problem}
        </p>
      )}
    </nav>
  );
}

function Inside(props: {
  node: FolderNode;
  depth: number;
  folderId: number;
  shown: Shown;
  isOpen: (folderId: number, dir: string) => boolean;
  toggle: (folderId: number, dir: string) => void;
  to: (folder: number | null, dir?: string) => string;
}) {
  const { node, depth, folderId } = props;
  return (
    <Branch
      name={node.name}
      pictures={node.pictures}
      depth={depth}
      lit={props.shown.folder === folderId && props.shown.dir === node.dir}
      open={props.isOpen(folderId, node.dir)}
      onToggle={() => props.toggle(folderId, node.dir)}
      to={props.to(folderId, node.dir)}
    >
      {node.children.map((inner) => (
        <Inside key={inner.dir} {...props} node={inner} depth={depth + 1} />
      ))}
    </Branch>
  );
}

/** One folder's row, with its chevron when it holds folders, and those folders when open. */
function Branch(props: {
  name: string;
  title?: string;
  pictures: number;
  depth: number;
  dim?: boolean;
  lit: boolean;
  open: boolean;
  onToggle: () => void;
  to: string;
  children: ReactNode[];
}) {
  const holds = props.children.length > 0;
  const Chevron = props.open ? ChevronDown : ChevronRight;
  const inset: CSSProperties = { paddingLeft: 30 + STEP * props.depth };
  return (
    <>
      <div className="relative flex">
        {holds && (
          <button
            type="button"
            aria-label={`${props.open ? "Hide" : "Show"} the folders in ${props.name}`}
            aria-expanded={props.open}
            onClick={props.onToggle}
            className="press absolute top-1/2 z-10 inline-flex size-5 -translate-y-1/2 cursor-pointer items-center justify-center rounded-4 text-fg-muted hover:text-fg"
            style={{ left: 6 + STEP * props.depth }}
          >
            <Chevron size={14} strokeWidth={2} aria-hidden="true" />
          </button>
        )}
        <Link
          to={props.to}
          title={props.title}
          aria-current={props.lit ? "page" : undefined}
          className={cn(ROW, props.lit ? LIT : UNLIT, props.dim && "opacity-60")}
          style={inset}
        >
          <span className="truncate">{props.name}</span>
          <span className="ml-auto font-mono text-12">{count(props.pictures)}</span>
        </Link>
      </div>
      {holds && props.open && props.children}
    </>
  );
}
