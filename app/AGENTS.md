# App UI: guide for coding agents

The UI lives in `app/src`: React 19, TypeScript 7, Tailwind 4, built by Vite. The Rust shell in
`app/src-tauri` has [its own guide](src-tauri/AGENTS.md). Start with [../AGENTS.md](../AGENTS.md)
and [../CLAUDE.md](../CLAUDE.md).

## Where it stands

The window's frame (the title bar, the nav rail with Home, the Library, the Queue with its badge,
History and Settings, the status bar with what the page in view says of itself
(`components/shell/status-note.tsx`), and pictures from anywhere: dropped on it, pasted with
Ctrl+V, or handed over by Windows (`components/shell/opening.tsx`, `features/batch/open.ts`, with
its notes at the window's foot)), Setup (Tools, which can be left while ffmpeg downloads, with This PC; then Your
folders), Home (the library in numbers, Drop pictures here with Pick pictures and Pick a folder, Needs you
with duplicates and bursts to review, the pictures that won't open in a card, and a batch done,
Space on the drives, Made today, Add a folder), the review of duplicates and bursts
(`features/duplicates/`: the groups, keeping another or more than one, Not the same, setting the
rest aside, a picture big beside the one kept), the Library (the folders as a tree, the pictures by
the day they were taken, ticks, and Many at once from the ticks, a folder's menu or a search),
Many at once (`features/batch/`: the steps with Change, See it first, When, Saving, What it
takes), the Queue (`features/queue/`), Recipes and watch folders (`features/recipes/`), a
picture's page, in the library or from outside it (`/pictures/:id`: where it lives in place of
the breadcrumb, with "Add its folder to the library"; pasted; or in a quarantine, to look at only:
`features/picture/outside.tsx`), the picture large at Fit, 100% or
400%, its neighbours, and its tools column: the Size tab, with the shape over the picture, before
and after at full detail when zoomed; the Looks tab, every look as a small copy of the picture,
its strength, the finishing touches, "Only on a part", the owner's own looks, and "Hold to see the
original"; the Edit tab (`edit-tab.tsx`, `edit-stage.tsx`, `editing.ts`: Select, Erase and Cut out,
what's picked and what to do with it, the brush, undo and Start again, each model downloaded the
first time); one Save for all three, and the job making it),
History (a week at a time, a batch or a review as one line with Take them away or Put them
back, take away and put back, replace again), Settings (General with Saving, Your data with
Set aside, Updates, About with This PC and the downloads), the update card, the notes at the
window's foot (a picture open in another app among them, `components/shell/in-use.tsx`), and the
way back from damaged records. Mado's own screens come from its design
canvas.

## Build to the design

- Every screen has a board on Mado's design canvas, snapshotted in `docs/design/`. Match it:
  layout, spacing, copy, states. Its inline values map one to one to the tokens in
  `src/styles/tokens.css`.
- `src/styles/tokens.css` is Graphite, the owner's pick, value for value from the Tokens board
  of the Mado Screens canvas (docs/design/screens/), with Aluminium for light. Never change a
  value unasked; build every screen to its board.
- Light and dark come from the same classes: every colour token holds both (`light-dark()`), and
  the page follows the window's theme. So no `white/…` or `black/…` on the interface (`bg-tint/6`,
  `border-rule`, `bg-field`, `bg-well` instead); white and black only on pictures, and in a part
  that stays dark, which carries `scheme-dark`. Check a new screen in both: `color-scheme: light`
  on `<html>` shows it light.
- One primary action per view; the rest are secondary or ghost buttons.
- Every screen designs its loading, empty and error states: name the problem, say what Mado did,
  offer the next step.
- Motion: `ease-mado`, 120 / 200 / 320 ms, `animate-fade-up` for entrances. Reduced motion is
  handled globally; don't work around it.
- Accessible as built: real `<button>` and `<a>`, labels on icon-only buttons, visible focus, a
  keyboard path for everything, `role="alert"` or `role="status"` for messages that appear.
- Only the page scrolls. A page starts with its top, its header or a breadcrumb, carrying
  `page-top`, so it stays put while the rest scrolls under it.
- More about one thing opens in a card over the page (`components/ui/dialog.tsx`): below the
  title bar, the page dimming behind it, closed by Escape, its cross or a click beside it, with a
  header (`DialogHeader`). The card itself takes the focus as it opens, not its first button. A
  long card scrolls inside its body, its foot (`DialogFooter`) staying put. Panels with a heading
  are `components/panel.tsx` (`features/settings/panel.tsx` in Settings).
- While Mado's records are damaged, the way back (`features/records/`) stands in for every page
  (`components/shell/app-shell.tsx`): the engine answers nothing else.
- Until setup is done, Home leads to it (`features/setup/`); its Tools step fetches what the
  engine's downloads list marks `setup`, then saves `setUp`.
- The window can't open addresses itself: the shell opens the downloads page for it
  (`lib/links.ts`), and folders and files in Explorer (`lib/explorer.ts`).

## Where things go

| What | Where |
| --- | --- |
| A screen and its parts | `src/features/<area>/` (`home/`, `settings/`, `setup/`, …) |
| Shared primitives (buttons, switches, dialogs…) | `src/components/ui/` |
| The window frame (title bar, nav rail, update card, the notes at its foot) | `src/components/shell/` |
| Talking to the engine and the shell | `src/lib/engine.tsx`, `src/lib/updates.ts`, `src/lib/screens.ts` |
| Tokens and global styles | `src/styles/` |
| Routes | `src/app.tsx`; nav items, and the one a new page lights (`sectionOf`), in `src/components/shell/sections.ts` |

## Data

- Engine data comes only through `src/lib/engine.tsx`: add a typed hook per endpoint
  (`export const useTools = () => useEngineQuery<Tool[]>("/tools")`), with its type mirroring
  `engine/openapi.json`. Changes use `useEngineAction` and refresh the queries they affect.
- No `fetch` or `invoke` outside `src/lib/`.
- Pictures the engine serves (thumbnails, views, a picture at full size) come through
  `usePictureImage(pictureAddress(picture, "thumbnail"))`: fetched with the token and shown as an
  object URL, let go when the address goes null. A long grid fetches thumbnails only as they near
  the view (`features/library/near.ts`).
- A list's place (its folder, search and order) lives in its address (`shownFrom`,
  `shownQuery`), so a picture opened from it, its neighbours and Back keep it.
- Local state stays in components. Add a global store only when two distant screens truly share
  client-side state.

## Components

- Reuse what exists (`Button`, `Toggle`, `EmptyState`, and `EngineProblem` for a screen whose data
  didn't come) before adding anything.
- New primitives start from shadcn/ui (`pnpm dlx shadcn@latest add <name>`) and are restyled to
  the tokens. They live in `src/components/ui/` and open with a comment naming shadcn/ui and
  `LICENSE-shadcn.txt`.
- A new npm package needs a licence on the allowed list in
  `engine/tools/third_party_notices.py`; `pnpm build:installer` stops otherwise.
- Merge classes with `cn()`. New font sizes or radii also go in `fontSizes` and `radii` in
  `src/lib/utils.ts` (a test checks).
- Icons from `lucide-react`; decorative ones get `aria-hidden="true"`.
- No real pictures, titles or people in the UI, its tests or its examples: made-up names, and
  pictures drawn by code.

## Commands

```powershell
pnpm tauri dev      # run Mado (UI with hot reload, shell, engine)
pnpm check          # Biome, TypeScript, Vitest
pnpm fix            # format and apply safe lint fixes
pnpm test:watch     # tests while you work
```

## Done means

`pnpm check` and `pnpm build` are green; the screen matches its board and works in the running app
with its loading, empty and error states; tests cover what a person sees and does.
