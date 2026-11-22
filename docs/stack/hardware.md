# This PC (what a PC can do for Mado)

Mado was measured on the owner's GTX 1660 Super, and runs on other PCs too: it looks at each PC's
graphics card, tests whether the AI models run on it, times them there, and starts each kind of
picture on the model that suits the PC. Nothing is promised that the PC can't do, and no time
shown is another PC's once it's tested. Settings › About shows it ("This PC"), and Setup's
welcome says it in a line.

| Part | Where |
| --- | --- |
| What a PC has and can do, decided (pure) | `mado/core/hardware.py` |
| Looking at Windows, and what's kept about the PC | `mado/hardware.py` |
| Checking and timing it, in the background | `mado/pc_check.py` (`PcCheck`, the engine's `app.state.pc`) |
| The API | `GET /pc`, `POST /pc/test` (`mado/api/pc.py`) |
| The screens | `app/src/features/settings/this-pc-panel.tsx`, `app/src/features/setup/this-pc.tsx` |

## What Mado looks at

Windows lists the display adapters (`Win32_VideoController`, through one PowerShell call that
also counts the processor's cores). Only cards on the PC's bus count (`PCI\…`): not Windows'
basic or remote display. Each card's maker comes from its PCI vendor id, its own memory from the
registry (`HardwareInformation.qwMemorySize`: the listing's `AdapterRAM` stops just short of 4
GB), and NVIDIA's driver as NVIDIA writes it ("617.42"). Intel's and AMD's with less than 2 GB of
their own are the processor's graphics. Mado works on the card of its own with the most memory,
else the processor's graphics; DirectML is asked for the high-performance card, the same one. The
processor's name comes from the registry, the memory from `GetPhysicallyInstalledSystemMemory`.
This is Kura's look at a PC, unchanged.

## The check

The general model runs one 512 tile through ONNX Runtime with DirectML, in a process of its own
(`mado check-model`, one line of JSON), so a graphics driver that fails on it takes only that
process with it, never the engine. A card that can't run it (no DirectX 12, a driver that fails)
sends the models to the processor, and Settings › About says why in the card's words.

Testing the PC (as Mado first starts, and "Test again" in Settings › About) also times each model,
about ten seconds in all: a tile to warm each up (DirectML compiles for the size on the first),
then up to eight more or six seconds: the general model at 512, the drawing model and the Best
photo model (once downloaded) at the tile this card gives them. On a PC whose card can't run
them, the general model on the processor at 256. A model that couldn't be timed keeps the time it
had. While a picture is being made, a test only checks, as its times would be off.

As the engine starts it checks again when this PC hasn't been checked, its last check found the
card didn't run the models (a driver mid-update, say), or its cards changed: new cards forget the
old ones' times and are timed anew; a new driver only checks.

## What's kept, and learned

The settings hold `pc` (what Windows said, and what the check found) and `pc_speeds` (each
model's seconds for a megapixel of tiles, by "model@place", and since when). Every picture made
times its model again (`mado/ai.py`'s `Timer`), moved 30% of the way into the speed kept
(`hardware.learn`), so the estimates become this PC's own; before anything is measured they're
the owner's PC's, and the Size tab says they're a guess. A tile is timed once it has the card,
not while it waits its turn behind a preview, and LaMa's squares aren't counted in the
upscaler's pace.

## Fast and Best

Each kind of picture starts on Best where a phone's 12-megapixel photo made for a 4K screen takes
Best at most two minutes on the card here (`core/hardware.py`'s `SLOW`), else on Fast; on the
processor, Fast always (Best there takes about 25 minutes a photo). On the owner's PC both start on
Best: about a minute for a photo with x4plus, 23 s for a drawing. The owner can always choose the
other on the Size tab, and About lists each kind at each quality with its time here.
