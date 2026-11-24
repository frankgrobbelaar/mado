# Tauri (the shell)

[Tauri 2](https://v2.tauri.app) turns the web UI into a Windows app: a native window drawn by
WebView2, a small Rust program around it, and the installer and updater. Mado uses Tauri 2.12 with
Rust stable (edition 2024).

## Files

| File | What it holds |
| --- | --- |
| `app/src-tauri/src/main.rs` | The app: plugins, state, commands, start and exit |
| `app/src-tauri/src/engine.rs` | Starting, watching and stopping the engine |
| `app/src-tauri/src/updater.rs` | Updates from the GitHub releases |
| `app/src-tauri/src/tray.rs` | The tray icon, starting with Windows, and notifications |
| `app/src-tauri/src/process.rs` | Running console programs without a console window |
| `app/src-tauri/src/opened.rs` | The paths Mado is started with, a second start's too, gathered into one choice for the window |
| `app/src-tauri/src/clipboard.rs` | The files copied in File Explorer, for pasting |
| `app/src-tauri/src/open_in_mado.rs` | File Explorer's "Open in Mado" and Open with, under HKCU, and their switch in Settings |
| `app/src-tauri/tauri.conf.json` | Name, version source, window, security policy, bundle, updater address and key |
| `app/src-tauri/tauri.bundle.conf.json` | Extra settings for building the installer (see below) |
| `app/src-tauri/capabilities/default.json` | What the window may ask of the shell |
| `app/src-tauri/windows/hooks.nsh` | Mado's additions to the installer |
| `app/src-tauri/icons/` | App icons, generated from `mado.svg` |

## The window

One window, `main`, 1280 × 832 (at least 720 × 560), with `decorations: false`: Mado draws its own
title bar (`app/src/components/shell/title-bar.tsx`) as the design shows. Elements marked
`data-tauri-drag-region` move the window and maximise it on double-click; the buttons call
`getCurrentWindow().minimize()`, `.toggleMaximize()` and `.close()`. Windows' snap layouts menu
doesn't appear when hovering our maximise button; Win+Z and dragging to the screen's edges still
work.

Light or dark (`look.rs`): the shell makes the window itself at start (`"create": false` in the
config, then `WebviewWindowBuilder::from_config`), giving it the look the owner chose in Settings >
General: none of its own to follow Windows, or always light or always dark. WebView2 takes the
window's theme as the page's `prefers-color-scheme`, so the page is light or dark from its first
frame, and its colours change with it (`light-dark()` in `tokens.css`). The window's own colour
under the page, seen before it draws, follows the theme too (`ThemeChanged`). The UI reads and
sets the look with the `look` and `set_look` commands (`app/src/lib/look.ts`).

## Commands and events

The UI calls the shell through these commands and listens to two events:

| Name | Kind | Does |
| --- | --- | --- |
| `engine_status` | command | The engine's status now: `starting`, `ready` (with address and token) or `failed` |
| `restart_engine` | command | Start again after a failure |
| `prepare_update` | command | Check for an update and download it; returns its version or nothing |
| `install_update` | command | Stop the engine, run the installer, let it reopen Mado |
| `open_downloads_page` | command | Open the downloads page in the browser |
| `pick_folder`, `pick_export` | command | Windows' folder picker, or its file picker for an export; nothing when cancelled |
| `open_folder`, `show_in_folder` | command | Open a folder in Explorer, or show a file there, selected |
| `start_with_windows`, `set_start_with_windows` | command | Whether Mado starts with Windows, in the tray |
| `keep_in_tray`, `set_keep_in_tray` | command | Whether closing the window keeps Mado running in the tray |
| `look`, `set_look` | command | Light or dark: `windows` (as Windows is), `light` or `dark` |
| `take_opened` | command | The choices of paths Windows handed Mado since the window last asked, each a list |
| `clipboard_files` | command | The paths of the files copied in File Explorer; none when the clipboard holds anything else |
| `open_in_explorer`, `set_open_in_explorer` | command | Whether File Explorer has "Open in Mado" and Open with; writing or taking away their keys |
| `engine-status` | event | Sent whenever the engine's status changes |
| `notice` | event | What the engine tells of, while the window is open |
| `opened` | event | A choice of paths is ready to take |

A new command is a `#[tauri::command]` function, listed in `generate_handler!` in `main.rs`, with
its types mirrored in `app/src/lib/`. Commands return `Result<T, String>`; the string is shown to
the person, so write it as a sentence.

## Security

- **Capabilities** (`capabilities/default.json`): the window gets `core:default` plus the title bar
  permissions (minimise, maximise, close, dragging). Add a permission only for a feature that needs
  it, and say why in the description.
- **Content security policy** (`app.security.csp`): scripts and styles from the app only,
  connections to the app, Tauri's IPC and the engine on `http://127.0.0.1:*`, images also from the
  engine, and video from `blob:` (a 3D photo plays from what the page fetched; without
  `media-src` it falls back to `default-src` and the window refuses to play it, which jsdom and
  the README's shots never notice).
- The installed window's origin is `http://tauri.localhost`; in development it is
  `http://localhost:1420`. The engine allows exactly these two (see [fastapi.md](fastapi.md)).

## Plugins

- **single-instance**: opening Mado again focuses the open window, because two copies would share
  one database, and hands it the paths it was started with (`opened.rs`). The plugin has a gap:
  a second start that finds the first's lock (`<identifier>-sim`) before the first has made its
  message window (`<identifier>-sic`) carries on as a second Mado. So `main.rs` first waits for
  that window, two seconds at most, whenever the lock is taken (`opened::wait_for_first`).
- **updater**: downloads and verifies updates. Configured under `plugins.updater`: the address of
  the newest release's `latest.json`, the public key, and passive install mode. Mado drives it
  from Rust (`updater.rs`), so the window needs no updater permission and the downloaded
  installer waits in the shell until "Restart and update". See [../releasing.md](../releasing.md).
- **dialog**: Windows' folder picker, for "Add a folder". Mado opens it from Rust too
  (`dialogs.rs`, `pick_folder`), so the window needs no dialog permission.
- **opener**: opens web pages in the default browser. Mado drives it from Rust too (`links.rs`):
  the window asks for a page by name (`open_downloads_page`), so it needs no opener permission and
  can't be steered to any other address.
- **The tray** (Tauri's `tray-icon` feature, `tray.rs`): an icon in the notification area while
  Mado runs, with Open Mado and Quit Mado; a click opens the window.
- **autostart**: "Start with Windows" in Settings > General, which Windows keeps in its own list
  of startup apps (the shell asks it, so the switch is always true to it). Windows starts Mado
  with `--in-tray`: the window stays hidden (it's created hidden and shown at start otherwise).
  Don't turn it on from a development build: Windows would start that build at sign-in.
- **Closing the window** quits Mado, unless "Keep Mado running when you close the window" is on
  (Settings > General, `keep_in_tray` in `tray.rs`): then it hides the window and Mado carries on
  in the tray. The shell keeps that choice, and light or dark, in `window.json` in its own folder
  (`choices.rs`; `%LOCALAPPDATA%\io.github.frankgrobbelaar.mado`, which uninstalling removes with
  "Delete the application data"). Until the owner chooses, it's whatever "Start with Windows" is,
  as closing was before it had a setting of its own.
- **notification**: Windows notifications for what the engine tells of on its stdout after the
  ready line (`{"event":"notify",...}`: a finished batch, a queue that paused itself), and for an
  engine that can't run (it's then tried again by itself), shown only while the window is away
  (in the tray or minimized); a click on one opens the window. While the window is open, the
  engine's notifications go to it instead, as the `notice` event. All from Rust, so the window
  needs no permission for either.

## Open in Mado

`open_in_mado.rs` writes, for this user only, under `HKCU\Software\Classes`:

| Key | Values | For |
| --- | --- | --- |
| `SystemFileAssociations\<type>\shell\Mado.Open` | `Open in Mado`, `Icon`, `MultiSelectModel` `Player`; `command` `"…\mado.exe" "%1"` | The menu entry on every type Mado reads, by extension, whatever Windows thinks the type is (HEIC, AVIF and camera RAW included) |
| `Directory\shell\Mado.Open` | the same | The menu entry on folders |
| `<type>\OpenWithProgids` | the value `Mado.Picture`, empty | Open with lists Mado for the type |
| `Mado.Picture` | `DefaultIcon`, `shell\open\command` | The file type Open with goes by |
| `Applications\mado.exe` | `FriendlyAppName`, `DefaultIcon`, `shell\open\command`, `SupportedTypes\<type>` | Mado among the applications, and the types it was written for |

Never a type's own default value, never `UserChoice`: which app opens a picture stays the owner's.
Windows reads each value of a type from the user's keys first and the PC's after, so an `.ext` key
holding only Mado's `OpenWithProgids` value leaves the PC's default in force (checked on the
owner's PC: an HKCU `.bmp` key with no default of its own still opens with the PC's
`Paint.Picture`). Windows may ask, the next time such a picture is opened, which app to use; the
owner's choice stays. Tauri's own `bundle.fileAssociations` isn't used: its NSIS template's
`APP_ASSOCIATE` writes each type's default value (`Software\Classes\.<ext>` = its class), which
would make Mado the default.

Only an installed Mado writes them (`uninstall.exe` beside `mado.exe`), as it starts and when
Settings › General's "Open in Mado in File Explorer" (on till turned off, kept in `window.json`)
changes; it writes them only when something differs, and tells Explorer then
(`SHChangeNotify(SHCNE_ASSOCCHANGED)`). Taking them away goes by what's written: "Open in Mado"
under every type (an older Mado's too), Open with's value under each type `SupportedTypes` names,
then each key above them left empty. The uninstaller does the same (`MadoForgetExplorer` in
`hooks.nsh`), except while updating. The registry code is tested against a root of the test's own
(`cargo test`), the uninstaller's half with `windows/hooks-test.ps1`, both comparing everything
under their root before and after.

On Windows 11 the entry is under "Show more options": the first menu takes only apps in a signed
package with an identity (an MSIX), which an unsigned app can't have.

**Several at once.** For a verb with a command line, Explorer starts Mado once for each file
selected; each start hands its path to the Mado running and ends, and `opened.rs` gathers what
arrives within 600 ms of the last into one choice. Measured on the owner's PC with the shell's own
multi-select invoke (`FolderItems.InvokeVerbEx`, as Explorer's right-click) against a build with
an identifier of its own:

| Selected | Mado running: paths arrive over | longest gap | one choice after | Mado not running: over | longest gap | one choice after |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | | | 1.7 s | | | 1.3 s |
| 15 | 0.22 s | 22 ms | 0.95 s | 0.41 s | 146 ms | 1.15 s |
| 100 | 1.53 s | 20 ms | 2.26 s | 1.70 s | 114 ms | 2.46 s |
| 101, 150, 200, 300, 500 | nothing starts | | | nothing starts | | |

Every run made one choice, in one Mado. 600 ms is four of the longest gap, which came while a Mado
started cold found its feet; the last look at a gathering is made on the main thread, where the
paths arrive, so a main thread too busy to take them can't make them look quiet. A start's words
become paths back on the gathering's own thread, as looking at a path on a network share that isn't
there can take a while; the clipboard's read and the switch's registry writes are off the main
thread too. Windows starts nothing past 100 selected with `Player`, and nothing past 15 with its
default (`Document`), which is why the verb says `Player`. Past 100, the folder's own "Open in Mado"
opens every picture in it.

"Send to › Mado" (a shortcut in the SendTo folder) was measured too: it starts Mado once with
every path (15 and 100 files: one choice in 0.7 s), but Windows refuses once the command line
passes 32,767 letters ("The filename or extension is too long": 200 files 160 letters deep
already), and it's a second menu entry. The verb, and the folder's own entry, cover more, so Mado
has no Send to.

**Starting cold.** The first start takes its own paths as it starts; the others wait for its
window, then hand theirs over. The window takes each choice once the engine is ready
(`take_opened`, told by the `opened` event), so nothing that arrives while Mado starts is lost;
`--in-tray` keeps working, and a Mado in the tray comes forward with them. Paths are taken as
given, quoted or not: a path with spaces typed without quotes is put back together, the longest
run of words that's there; one typed in a terminal is found where it was typed.

## Paste

Ctrl+V anywhere in the window but a text field: the page's own `paste` event. The window can't
learn the paths of files copied in File Explorer (a web page is never given them), so the shell
reads the clipboard's file list itself (`CF_HDROP`, `clipboard_files`, through windows-sys, the
windows crate's own bindings, already in Mado's build through Tauri; the Tauri clipboard plugin
reads only words and pictures). That's asked first, as a page sees a copied picture file as a
picture too. Then a picture on the clipboard (a screenshot, or one copied from a browser or
another app), which the window's Chromium hands the page as PNG, goes to the engine (`/pasted`);
then words that are paths (File Explorer's Copy as path, `file:` addresses); anything else, a note.

The window's own clipboard hands a page a picture of at most 2^26 pixels (256 MiB of them, about
67 megapixels); past that it gives an empty PNG, so that's Mado's limit, said as "too big to paste"
on both sides. Measured on the owner's PC (Edge, as WebView2 is Chromium, a made-up picture put on
the clipboard and Ctrl+V sent over DevTools; headless Edge has a clipboard of its own, so it ran
with a window):

| Picture | The window has it as PNG | Mado keeps it | its view made |
| --- | --- | --- | --- |
| 4 MP | 71 ms | | |
| 12 MP | | 0.1 s | 0.7 s |
| 25 MP | 0.48 s | | |
| 50 MP | 0.91 s | 0.4 s | 1.3 s |
| 66 MP | 1.20 s | | |
| 68 MP and more | an empty picture | | |
| 100 MP | | 0.7 s | 1.6 s |

## The engine process

In development the shell runs `uv run --project engine mado serve --watch-stdin` and points
`MADO_DATA_DIR` at `engine/.dev-data`. Installed, it runs `engine\mado-engine.exe` from the
resource folder. Either way it hides the console window, reads the ready line (waiting on while
the engine says it's still working, giving up on one silent for a minute), keeps the last 40
error lines for the failure screen, notices if the engine stops on its own, and closes its
stdin on exit. See
[../architecture.md](../architecture.md#start-run-stop).

## Installer

`bundle.targets` is `nsis`: one `Mado_<version>_x64-setup.exe`, installed per user without admin
rights (`installMode: currentUser`). Publisher: Mado. WebView2 is downloaded by the installer if a
PC lacks it (Windows 11 always has it).

`tauri.bundle.conf.json` is merged in only by `pnpm build:installer`. It builds the engine, the UI
and the third-party notices first; adds `engine/dist/mado-engine/` as the `engine/` resource
folder, with `LICENSE.txt` and `THIRD-PARTY-NOTICES.txt` beside Mado; and turns on
`createUpdaterArtifacts` (the `.sig` file). Keeping these out of the main config means
`pnpm tauri dev` and `cargo clippy` work without a PyInstaller build or the signing key.

`windows/hooks.nsh` is included by Tauri's NSIS template:

- `MadoUseProgramsFolder` (run as the installer's window opens) changes the default folder from
  `%LOCALAPPDATA%\Mado`, which is the data folder, to `%LOCALAPPDATA%\Programs\Mado`.
- `NSIS_HOOK_PREUNINSTALL` offers the export and stops if it fails.
- `NSIS_HOOK_POSTUNINSTALL` deletes the data folder (`%LOCALAPPDATA%\Mado`) only if "Delete the
  application data" was ticked, and takes away File Explorer's "Open in Mado" and Open with
  (`MadoForgetExplorer`, see "Open in Mado"), except while updating.
- `NSIS_HOOK_PREINSTALL` and `NSIS_HOOK_POSTINSTALL` replace the engine whole. NSIS copies a new
  version's files over the old ones and leaves the ones it doesn't have, so Python found both
  versions of whatever changed (updated to 0.2.0, the engine still said 0.1.0, from the old
  version's `mado-0.1.0.dist-info` beside the new one's). Before copying, the old `engine` folder
  becomes `engine-old`; after, `engine-old` goes, with a few tries while an engine that's only
  just stopped lets go of its files. `.onInstFailed` puts it back if the install stops between.
  Windows lets a running program's folder be renamed, so a running engine is set aside too; the
  files it holds stay in `engine-old` until the next install or the uninstall.

Hooks can use the template's variables (`$UpdateMode`, `$PassiveMode`, `$DeleteAppDataCheckboxState`).
After a Tauri upgrade, build an installer and test an install, an update and an uninstall. The
pre-install hook runs before the template checks whether Mado is open, and nothing runs between
that check and the copying. `windows/hooks-test.ps1` checks the engine's replacement on a scratch
folder in `target/` (an update, a first install, a stopped install, a running engine), and the
uninstall hook's registry part against a root of its own (Mado's keys taken away and only them,
kept through an update, nothing changed when there were none), with the NSIS that
`pnpm build:installer` downloads: run it after changing `hooks.nsh` or upgrading Tauri.

## Commands you'll use

```powershell
cd app
pnpm tauri dev                      # run Mado
pnpm tauri icon src-tauri/icons/mado.svg   # regenerate icons (then delete the non-Windows ones)
pnpm build:installer                # build the installer (needs the signing key)
cd src-tauri; cargo clippy --all-targets -- -D warnings; cargo test
```

## Upgrading

Keep `@tauri-apps/cli` and `@tauri-apps/api` (npm) and `tauri`, `tauri-build` and the plugins
(Cargo) on the same minor version. Read the [release notes](https://v2.tauri.app/release/) for
config changes, rebuild the installer, and test install, update and uninstall.
