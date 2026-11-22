# What Mado ships beside its code

Making a picture bigger needs AI models, which aren't code. The small ones ship inside Mado (the
engine bundle), so nothing is downloaded for them, and each keeps its licence, which goes into
`THIRD-PARTY-NOTICES.txt` (`engine/tools/third_party_notices.py`). The bigger ones are downloads,
fetched the first time they're asked for (`engine/src/mado/downloads.json`): RealESRGAN x4plus
(Best for photos, 67 MB) and LaMa (extending edges, 209 MB), from Mado's own release `models-1`,
each with its licence beside it.

| File | What it is | Licence | SHA-256 |
| --- | --- | --- | --- |
| `realesr-general-x4v3.onnx` | Real-ESRGAN's general model (v0.2.5.0), four times bigger: Fast, for photos and drawings; it takes noise and JPEG blocks out | BSD-3-Clause, Xintao Wang (`LICENSE-Real-ESRGAN.txt`) | `22955412e704d0c7da459ba118a0aad0ce9e545b8004cec0588cce822cc61c8e` |
| `realesr-general-wdn-x4v3.onnx` | Its weak-denoise twin: Fast with cleaning turned off, keeping grain | BSD-3-Clause, Xintao Wang (`LICENSE-Real-ESRGAN.txt`) | `568c87f30c75d4a18de830b69f97805acc194436642cd97180591a58d44c5605` |
| `realesrgan-x4plus-anime-6b.onnx` | RealESRGAN x4plus's anime model (v0.2.2.4): Best for drawings, comics and flat-colour art | BSD-3-Clause, Xintao Wang, and Apache-2.0 for BasicSR's network (`LICENSE-Real-ESRGAN.txt`, `LICENSE-BasicSR.txt`) | `c489130a7221324ca4473ce22bdd1b7dc91426a7aeac96393425b675dfd6276d` |

How they were made: exported to ONNX (opset 17, full precision, `dynamo=False`) from the official
weights of Real-ESRGAN's releases with PyTorch 2.15 and onnx 1.23.2, then checked against
PyTorch on the processor and on DirectML (a mean difference under a millionth). Each takes
`input`, float32 `[batch, 3, height, width]` RGB from 0 to 1, and gives `output`, four times as
wide and high, clamped to 0 to 1. Mado pins batch, height and width to its tile size as each
session is made (`mado/directml.py`).

Why these: measured on the owner's GTX 1660 Super on 2026-11-22 against the rest of the
shortlist, see [docs/stack/upscaling.md](../../../../docs/stack/upscaling.md).
