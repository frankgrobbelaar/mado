# Mado's screens

Snapshots of Mado's design canvases, as plain pages, made by
[scripts/design-snapshot.mjs](../../scripts/design-snapshot.mjs). The canvases are the source of
truth (they are the owner's, and private; these snapshots are the shared copy).

The first canvas, three looks for Mado for the owner to choose from, is being drawn; its pages
arrive here with it.

To refresh a canvas's pages, read it with Claude's Artifact tool (which saves it as a folder
holding `project/canvas.json`), then run `node scripts/design-snapshot.mjs --<canvas> <folder>`.
Never edit the pages by hand.
