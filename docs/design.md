# Design

How Mado looks and behaves. The look is **Graphite**, the owner's pick of three on the
[Mado Looks canvas](https://claude.ai/artifact/3te6hjNWp42cxk5EXcsDXv): a mid-grey bench, dense
panels, the slim rail down the side, one volt accent, and IBM Plex Sans and Mono. Its light is
**Aluminium**. Every screen is drawn in it on the
[Mado Screens canvas](https://claude.ai/artifact/TJcDDQ5XmVTNPMvRdE3Jfb), the source of truth to
build to, with snapshots you can open locally in [design/](design/README.md). Build to those
boards, and never change the look unasked.

The mark is a round window lit in volt with a hill seen through it, on a graphite tile
([app/src-tauri/icons/mado.svg](../app/src-tauri/icons/mado.svg)). It keeps its colours in light
and dark, as an app's icon does.

## The bar

Simple to use and beautiful, like Revolut or Linear: fewer, clearer elements and one strong
primary action per view. Smooth motion that explains what changed. Honest progress. And no
struggling with small things: every error, empty state and recovery is designed.

## Eight rules every screen follows

1. **Pictures come first.** The interface around a picture stays neutral grey, so it never changes
   how the picture's colours look; colour in the interface is one small accent.
2. **Status reads without colour.** Shape and label carry the meaning; colour reinforces it. Done
   is solid in the text colour, working is the accent pulsing, waiting is hollow, a problem is
   hatched.
3. **Motion explains, never decorates.** Hover and press 120 ms, toggles 200 ms, panels and pages
   320 ms, charts on first view 600 to 900 ms, one curve, `cubic-bezier(.2,.8,.2,1)`: a quick
   start and a soft landing. With Windows' animation effects off, nothing moves.
4. **Progress says what, how far and how long.** Every long job, a batch above all, shows its
   stage, a percentage and the time left, and can be paused. Nothing spins silently.
5. **Nothing changes until you review it.** A tool's result is a new picture beside the original
   unless you choose to replace it; then the original goes to quarantine for 30 days, and History
   puts it back. Renames, moves and deletions are proposed first, logged and undoable.
6. **Fits every window size.** Layouts reflow on their own, and only the page scrolls: the rail,
   the title bar and the status bar stay where they are.
7. **Light and dark, designed together.** Mado is light or dark as Windows is, unless the owner
   picks one in Settings › General. Body text keeps 4.5:1 contrast in both.
8. **Keyboard first, mouse friendly.** Everything can be reached and done from the keyboard, the
   focus ring (the accent, 2 px, 2 px off the edge) is always visible, and click targets are at
   least 36 px.

## Graphite in code

The tokens live in [app/src/styles/tokens.css](../app/src/styles/tokens.css), value for value from
the Tokens board; Tailwind turns them into classes ([stack/tailwind.md](stack/tailwind.md)), and
Tailwind's own palette is switched off so nothing off-system creeps in. A colour that differs in
light mode is written `light-dark(aluminium, graphite)`, so one class serves both.

| For | Use | Graphite (dark) | Aluminium (light) |
| --- | --- | --- | --- |
| The window, the bench | `bg-window` | #2A2B2E | #D3D4D7 |
| The rail and the title bar | `bg-chrome`, `border-chrome-edge` | #232427, #3A3B40 | #C9CACE, #B5B6BB |
| The status bar | `bg-statusbar` | #262729 | #CBCCD0 |
| A panel | `bg-glass border border-edge rounded-8` | #333438, #46474D | #E4E5E8, #BDBEC3 |
| A tools column, a placeholder | `bg-surface` | #2F3033 | #DCDDE0 |
| A picked row, a card over a panel, a dialog | `bg-raised`, `bg-dialog rounded-10` | #3A3B40, #333438 | #EDEEF0 |
| Behind a picture | `bg-behind` | #1E1F21 | #BFC0C4 |
| Under segmented choices, logs | `bg-well`, `bg-inset` | #232427 | #C6C7CB |
| A field or a secondary button | `bg-field border border-field-edge` | #2F3033, #55565C | #F4F4F6, #A6A7AD |
| Lines between rows | `border-rule` (and `edge`, `line`) | #46474D | #BDBEC3 |
| A stronger line, a step not reached | `border-line-strong` | #55565C | #A6A7AD |
| A drop zone's dashes | `border-dash border-dashed` | #6A6B71 | #8D8E94 |
| Main text, quiet, faint | `text-fg`, `text-fg-muted`, `text-fg-faint` | #F0F0F1, #B4B5BA, #9A9BA1 | #1A1B1E, #45464C, #57585E |
| Labels and inactive controls | `text-fg-soft` | #D6D7DA | #2E2F33 |
| The primary action | `bg-accent text-on-accent` | #C9F24D on #172000 | #4C7500 on #FFFFFF |
| Accent text, links, picked | `text-accent-fg`, `bg-accent/8` | #D6F57A | #3D5F00 |
| A problem, its words | `status-problem`, `text-broken-fg` | #FF8B7B | #B3261E |
| A destructive button | `bg-danger text-on-danger` | #FF8B7B on #2B0D09 | #B3261E on #FFFFFF |
| A hover, a chip | `bg-tint/6` (and /3 to /12) | white at that share | ink at that share |
| Sizes, paths, times, numbers | `font-mono` | IBM Plex Mono |
| Headings | `type-display` (32), `type-title` (24), `type-heading` (16), `type-eyebrow` (11, capitals) | IBM Plex Sans 600 |
| Other text | `text-14` (body, 400), `text-13` (secondary), `text-12`, `text-11` | px-named sizes |
| Corners | `rounded-4` thumbnails, `rounded-6` controls, `rounded-8` panels, `rounded-10` dialogs, `rounded-full` dots and badges | |
| Motion | `ease-mado`, `duration-120`/`200`/`320`, `animate-fade-up`, `press`, `lift` | |

Rules of thumb:

- One `bg-accent` button per view; everything else is secondary or ghost.
- Text on the accent is always `text-on-accent`; accent text is `text-accent-fg`.
- No `white/…` or `black/…` on the interface: they don't turn with light mode. White and black are
  for what sits on a picture.
- Panels sit flat, drawn by their edges; only what floats over the page (a dialog, a toast, the
  update card) has a shadow.
- If a value you need isn't a token, ask before adding one, with its value in both lights.

## The window

- **The rail** (`components/shell/nav-rail.tsx`), 80 px wide down the left: the mark at the top
  (drag it to move the window), Mado's places under it with their icon over their name (Home, the
  Library, the Queue, History), the lit one raised, and Settings at its foot. The Queue's badge,
  a volt pill in the mono at its corner, says how far the batch being made has got ("37%"), or
  how many pictures wait. Many at once lights the Library; Recipes lights the Queue.
- **The title bar** (`title-bar.tsx`), a slim strip over the page with the window's buttons; a
  page without the rail (Setup) gives it the mark and a name.
- **The status bar** (`status-bar.tsx`), 32 px at the foot in the mono: how the engine is, Mado's
  version, what it's making ("Graphics card working · Holiday prints 18 of 48"), what it's doing
  with the library ("Watching 3 folders", "Reading 212 of 4,812"), and "Your pictures stay on
  this PC".
- **Dropping pictures** (`shell/drop-zone.tsx`): anywhere on the window. While they're over it, a
  dashed card over the page says what dropping does; dropped, one picture from the library opens
  its page and anything else Many at once. What isn't a picture is said in a note at the foot.

## Components

Built so far, in `app/src/components/`:

| Component | Use it for |
| --- | --- |
| `ui/button.tsx` | Every button. Variants `primary`, `secondary`, `ghost`, `danger`; sizes `md` (40 px) and `sm` (36 px); `asChild` to style a link |
| `ui/segmented.tsx` | One choice from a few side by side, the chosen one raised in a well |
| `ui/slider.tsx` | An amount along a line (a look's strength, a touch's amount): a thin track, the part up to the thumb in the accent, a round thumb in the text colour; the arrow keys, Page Up and Down, Home and End move it |
| `ui/switch.tsx`, `toggle.tsx` | On or off: the switch (the accent when on), and a row with its name and what it does |
| `empty-state.tsx` | A place with nothing in it yet, with its one next step |
| `made-up-picture.tsx` | The made-up pictures an empty place shows (alps, dunes, aurora, meadow, lake, bloom), drawn by code as the Pic board draws them |
| `shell/` | The rail, title bar, status bar, update card and the notes at the window's foot |
| `mado-logo.tsx` | The mark, in its own colours |

Settings' light-or-dark choice (`features/settings/look-choice.tsx`) is three cards, each with a
little picture of the window in its scheme.

Many at once's own (`features/batch/`): `StepsPanel` (a batch's steps, numbered, each with its
icon, what it does and Change; "Add a step"; "or start from" a recipe's pill; the Recipes link),
`RecipeLine` (steps as chips joined by arrows, a look's strength in the accent mono), the step
cards (`step-dialogs.tsx`: the Size tab's devices, screens and prints; the Looks tab's looks and
touches; how they're saved) and `SeeFirst` (three pictures before and after with a white line
between them, opened at Fit, 100% or 400%). New primitives start from shadcn/ui (accessible, built
on Radix) and are restyled to the tokens; see [stack/tailwind.md](stack/tailwind.md).

## Patterns

- **Page header**: `type-title`, a one-line summary beside or under it in `text-fg-muted`, the
  page's primary action on the right.
- **A long job**: stage steps, a bar with the percentage, and "18 min left". Pause is always there.
- **Review before apply**: the change as before → after, grouped, with counts, one primary button,
  and Undo afterwards in a toast and in History.
- **Ticks**: a box on each picture of a grid, Shift for a run from the one ticked last, and a bar
  that says how many, from how many days, and offers only what works on them now.
- **A page with its own column** (the Library's folders, a picture's tools): the column runs the
  window's height beside the page, flush to the rail or the edge, and stays put while the page
  scrolls.
- **Before and after** (the Size tab): fitted, the picture shows the shape it takes (the part
  kept framed in dashes, the rest dimmed, the point it's cropped around to drag, or the new edges
  drawn in); zoomed to 100% or 400%, a part of the picture made at full detail beside the same
  part only stretched, a white line with a round handle between them (dragged, or moved with the
  arrow keys), the picture dragged (or moved with the arrow keys) to look elsewhere; a big, sharp
  screen gets no more than a preview may be (4 megapixels), shown a little bigger to fill the
  stage. After waits, saying so, while its model downloads. Labels sit on the picture in white on
  black.
- **Going through looks** (the Looks tab): every look a small copy of the picture, three to a
  row, the one picked outlined in the accent; the arrow keys go along them (up and down a row at
  a time), and the pointer resting on one shows it on the big picture till it moves away. The big
  picture keeps the last look while the next is made, says "Making the preview…" meanwhile, and
  "Hold to see the original" (or the \ key) shows it without its look. A label on the picture says
  what's on it: "Warm film · 60% · grain, vignette".
- **On or off, with an amount** (finishing touches): a pill each, its amount beside its name in
  the mono while it's on, and a line with a slider for each touch that's on.
- **A tool's foot**: the job making the picture and the primary action stay at the foot of the
  tools column however long it grows, what scrolls under them fading out above.
- **A job in its column**: the stage in words, a bar with the percentage, "about 25 s left" and
  Cancel till it saves; then what it saved with Show in folder and Open it (a new picture, or one
  that replaced its original in another format), or why it didn't work, hatched.
- **A model to download**: offered where it's needed, with its size and the lighter way beside it
  ("Download RealESRGAN x4plus" or "Use Fast"), its progress in its place.
- **The small things**: a drive unplugged, not enough space, a file in use, a crash, a failed job,
  a name already taken, offline. Each message names the problem, says what Mado already did, and
  offers the next step.
- **A batch's steps** (Many at once, a recipe): numbered in the order they're made, each with
  what it does in a line and Change, which opens the picture page's own choices in a card; Save
  last; "Add a step" dashed for one it hasn't yet. The right column holds When (radios), Saving
  (new pictures or the originals replaced, and where, in a line) and What it takes (time, space,
  what's free, how it was timed), then the one primary button, "Put 48 in the queue".
- **The queue's rows**: a table, its pictures by their shape (being made pulses, waiting is
  hollow, done is solid, didn't work is hatched with its reason in a sentence and Try again);
  "now", "next" and "+28 more" in the mono; ticks only on what waits, which a toolbar above moves
  next, to the end or out. A drive without room is a card in the queue's place: what it needs,
  "Make the 11 that fit now", emptying its quarantine (asked again), or waiting. With nothing
  waiting, a batch whose pictures didn't all work stays, "is done" in its line, with Try again
  on each and Clear where Pause and Cancel all were.

## Words

- Plain words, short sentences, second person: "Your library is empty".
- Say what happens: "Mado closes, updates and opens again", not "Applying update".
- Numbers carry their units and stay human: "18 min left", "about 40 MB", "today 14:20".
- No exclamation marks, no blame, no jargon (say "picture", not "image asset").
