# Mado's screens

Snapshots of Mado's design canvases, as plain pages, made by
[scripts/design-snapshot.mjs](../../scripts/design-snapshot.mjs). The canvases are the source of
truth (they are the owner's, and private; these snapshots are the shared copy).

- [Mado Screens](https://claude.ai/artifact/TJcDDQ5XmVTNPMvRdE3Jfb): every screen in Graphite, the
  look the owner picked, and four in Aluminium, its light: Setup, Home, the Library, a picture's
  size, looks and editing, saving, many at once, the queue, recipes, History, Settings and the
  small things, with the Tokens board the app takes its values from ([screens.html](screens.html)
  and the pages in [screens/](screens/)). The rail on every screen is one board, Rail.
- [Mado Looks](https://claude.ai/artifact/3te6hjNWp42cxk5EXcsDXv): three looks for the owner to
  choose from, A Darkroom, B Gallery and C Graphite, each showing Home, the Library, a picture
  with its tools and many pictures at once ([looks.html](looks.html) and the pages in
  [looks/](looks/)). Every picture on it is drawn by code (the Pic board).

To refresh a canvas's pages, read it with Claude's Artifact tool (which saves it as a folder
holding `project/canvas.json`), then run `node scripts/design-snapshot.mjs --<canvas> <folder>`.
Never edit the pages by hand.
