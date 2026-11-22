# watchdog (noticing changes in the library's folders)

[watchdog](https://github.com/gorakhargosh/watchdog) 7.1 (Apache-2.0) tells Mado when a file in a
library folder is added, removed, renamed or written, the moment Windows knows
(`ReadDirectoryChangesW`), without walking the folders on a timer. Walking every few minutes would
keep sleeping disks awake; being told costs nothing.

## How Mado uses it

[mado/watch.py](../../engine/src/mado/watch.py) runs inside `mado serve` (`create_app(...,
watch=True)`; tests leave it off):

- **As Mado starts** it watches the folders first, then catches up: a scan for whatever changed
  while Mado was closed, once setup is done and there are folders. Watching first means a picture
  that arrives as Windows starts (a phone syncing) is never between the two.
- **Watching**: one watchdog observer per library folder that's there (`recursive=True`). A folder
  added or taken out is followed at once (the API wakes the watcher), so a picture saved into a
  new folder straight away is noticed. Windows stops telling about a folder once it goes (deleted,
  or its drive unplugged), so its observer is dropped then and a new one starts when it's back,
  with a scan for what changed meanwhile.
- **What counts**: pictures (by extension, camera RAW too) when they come, go, change or are
  renamed; folders when they come or are renamed, or go while the library has pictures in them.
  Something written inside a folder doesn't count: the files tell for themselves.
- **When a scan starts**: once the folder has been quiet for 5 seconds, so a card's pictures still
  copying wait until they're done. A scan asked for while one runs follows it.

It looks around every 15 seconds, and every second while a change waits for its folder to go
quiet. Anything that goes wrong in one look is logged, and the next look carries on.

## Notes

- Windows takes a moment after an observer starts before it reports changes; the catch-up scan at
  start covers anything that happens in that moment.
- A file write raises "created" and then "modified": both count as the same change, and the quiet
  period runs from the last one.
- A folder moved out of a watched folder, or deleted, comes as a "deleted" event that says it's a
  file (the folder is gone, so Windows can't tell); Mado asks its database whether it held
  pictures there.
- watchdog 7 closes a folder's handle once, in the thread that reads the folder, whether the
  folder goes or the observer is stopped. watchdog 6 closed it twice, and by the second time
  Windows could have given that number to another file (the database's): in Kura, closing it
  crashed the engine. `tests/test_watch.py` checks the handle is closed once.
- PyInstaller bundles watchdog without help; `tests/test_cli.py` (with `MADO_ENGINE_EXE`) starts
  the bundled engine, which imports it.
