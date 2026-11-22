# Design

How Mado looks and behaves. Mado's own look is being chosen: three looks are drawn on a design
canvas for the owner to pick from, and its boards become the source of truth for every screen,
with snapshots you can open locally in [design/](design/README.md). Until then the app wears
Kura's Cinema tokens as a stand-in (the stack pages that say "Cinema" mean those tokens). Build to
the boards once they're chosen, and never change the look unasked.

## The bar

Simple to use and beautiful, like Revolut or Linear: fewer, clearer elements and one strong
primary action per view. Smooth motion that explains what changed. Honest progress. And no
struggling with small things: every error, empty state and recovery is designed.

## Eight rules every screen follows

1. **Pictures come first.** The interface around a picture stays neutral grey, so it never changes
   how the picture's colours look; colour in the interface is one small accent.
2. **Status reads without colour.** Shape and label carry the meaning; colour reinforces it.
3. **Motion explains, never decorates.** Hover and press 120 ms, toggles 200 ms, panels and pages
   320 ms, one curve, `cubic-bezier(.2,.8,.2,1)`: a quick start and a soft landing. With Windows'
   animation effects off, nothing moves.
4. **Progress says what, how far and how long.** Every long job, a batch above all, shows its
   stage, a percentage and the time left, and can be paused. Nothing spins silently.
5. **Nothing changes until you review it.** A tool's result is a new picture beside the original
   unless you choose to replace it; then the original goes to quarantine for 30 days, and History
   puts it back. Renames, moves and deletions are proposed first, logged and undoable.
6. **Fits every window size.** Layouts reflow on their own, and only the page scrolls: the nav
   rail and the page's top stay where they are.
7. **Light and dark, designed together.** Mado is light or dark as Windows is, unless the owner
   picks one in Settings › General. Body text keeps 4.5:1 contrast in both.
8. **Keyboard first, mouse friendly.** Everything can be reached and done from the keyboard, the
   focus ring is always visible, and click targets are at least 40 px.

## Tokens in code

The tokens live in [app/src/styles/tokens.css](../app/src/styles/tokens.css); Tailwind turns them
into classes ([stack/tailwind.md](stack/tailwind.md)), and Tailwind's own palette is switched off
so nothing off-system creeps in. A colour that differs in light mode is written
`light-dark(light, dark)`, so one class serves both. For now they're Kura's Cinema values, as
Kura's [design page](https://github.com/frankgrobbelaar/kura/blob/main/docs/design.md) lists them;
Mado's own replace them once its look is chosen.

Rules of thumb:

- One `bg-accent` button per view; everything else is secondary or ghost.
- No `white/…` or `black/…` on the interface: they don't turn with light mode. White and black are
  for what sits on a picture.
- If a value you need isn't a token, ask before adding one, with its value in both lights.

## Components

Built so far, in `app/src/components/`:

| Component | Use it for |
| --- | --- |
| `ui/button.tsx` | Every button. Variants `primary`, `secondary`, `ghost`, `danger`; sizes `md` (44 px) and `sm` (36 px); `asChild` to style a link |
| `empty-state.tsx` | A place with nothing in it yet, with its one next step |
| `shell/` | The title bar, nav rail, update card and the notes at the window's foot (offline, what the engine tells of) around every screen |
| `mado-logo.tsx` | The mark, a stand-in until the look is chosen |

New primitives start from shadcn/ui (accessible, built on Radix) and are restyled to the tokens;
see [stack/tailwind.md](stack/tailwind.md).

## Patterns

- **Page header**: `type-title`, a one-line summary under it in `text-fg-muted`, the page's primary
  action on the right.
- **A long job**: stage steps, a bar or ring with the percentage, and "18 min left". Pause is always
  there.
- **Review before apply**: the change as before → after, grouped, with counts, one primary button,
  and Undo afterwards in a toast and in History.
- **The small things**: a drive unplugged, not enough space, a file in use, a crash, a failed job,
  a name already taken, offline. Each message names the problem, says what Mado already did, and
  offers the next step.

## Words

- Plain words, short sentences, second person: "Your library is empty".
- Say what happens: "Mado closes, updates and opens again", not "Applying update".
- Numbers carry their units and stay human: "18 min left", "about 40 MB", "today 14:20".
- No exclamation marks, no blame, no jargon (say "picture", not "image asset").
