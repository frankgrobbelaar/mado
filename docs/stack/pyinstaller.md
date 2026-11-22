# PyInstaller (bundling the engine)

The installed Mado can't assume Python is on the PC, so [PyInstaller](https://pyinstaller.org)
bundles the engine with its own Python into a folder: `mado-engine.exe` plus `_internal/` (the
interpreter and the packages, about 50 MB, Pillow's decoders the largest part). The installer copies that folder next to
Mado's window as `engine\`.

A folder ("onedir") rather than a single exe because a single exe unpacks itself into a temporary
folder on every start: slower, and it upsets antivirus tools.

## Files

| File | What it holds |
| --- | --- |
| `engine/mado-engine.spec` | The recipe: entry point, package metadata, console program, no UPX |
| `engine/src/mado/__main__.py` | The entry point (also `python -m mado`) |
| `engine/dist/mado-engine/` | The output (ignored by git) |

## Building

```powershell
cd engine; uv run pyinstaller mado-engine.spec --noconfirm
dist\mado-engine\mado-engine.exe version
```

`pnpm build:installer` does this first, through `tauri.bundle.conf.json`.

## How the spec works

- `Analysis` starts at `__main__.py` and follows imports; `pathex=["src"]` finds the package.
- `copy_metadata("mado")` includes the package's metadata, which `mado.__version__` reads.
- Packages that load modules by name (Uvicorn, and Pillow's format plugins) are covered by the
  hooks in `pyinstaller-hooks-contrib`, which comes with PyInstaller. watchdog needs nothing. A
  library of every format Mado reads was scanned with the bundled engine to check it.
- `console=True`: the engine is a console program (the uninstaller and the CLI read its output);
  the shell starts it with no console window.
- UPX compression is off: it saves little and causes antivirus false alarms.
- `excludes` drops packages that only optional imports reach: setuptools (through `distutils`)
  and pytest (anyio's test runner). The filter after `Analysis` drops the Universal C Runtime
  DLLs, which Windows 10 and 11 have built in; otherwise PyInstaller copies whichever ones it
  finds on PATH (a JDK's, on the owner's PC), and builds would differ between PCs.
- Microsoft's Visual C++ runtime (`vcruntime140.dll` and its kin), which Python and ONNX Runtime
  need and not every PC has, ships with the engine from Windows' own copy in `System32`,
  which Microsoft's Visual C++ Redistributable installs. Left alone, PyInstaller takes the first copy on PATH (ImageMagick's
  on GitHub's runners, a JDK's on the owner's PC), which could be any version, and the notices
  couldn't say what it is. A PC that builds the engine needs the Redistributable; GitHub's runners
  have it.
- PyInstaller's records of what it bundled (`build/mado-engine/*.toc`) feed the third-party
  notices (see [../releasing.md](../releasing.md#third-party-notices)).

## When something is missing

If the bundled engine fails with `ModuleNotFoundError` while `uv run mado` works, PyInstaller
didn't see an import made by name. Add it to `hiddenimports=[...]` in `Analysis`, or collect a
whole package with `collect_submodules("name")`, then rebuild and run
`dist\mado-engine\mado-engine.exe serve` with `MADO_TOKEN` set to check. Data files a package
reads at run time go in `datas`.

ffmpeg won't go in this bundle: Mado downloads it on first setup (the "Tools" step in the setup
screen), which keeps the installer and every update smaller. ONNX Runtime with DirectML ships
inside it (PyInstaller's own hook collects its `capi` folder, `DirectML.dll` included), and so do
the small AI models (`src/mado/assets`, in `datas`, about 28 MB): the bundle is about 170 MB. The
bigger models are downloads (see [upscaling.md](upscaling.md)). The PC check runs the bundled
engine again as `mado-engine.exe check-model`, a process of its own.

## Upgrading

`uv lock --upgrade` updates PyInstaller and its hooks. Rebuild, then run the engine's handshake test
against the bundle, as the release workflow does before publishing:

```powershell
cd engine; $env:MADO_ENGINE_EXE = "dist\mado-engine\mado-engine.exe"; uv run pytest tests/test_cli.py -k announces
```
