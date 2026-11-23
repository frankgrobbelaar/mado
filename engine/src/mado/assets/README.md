# What Mado ships beside its code

Making a picture bigger and cutting out its subject need AI models, which aren't code. The small
ones ship inside Mado (the engine bundle), so nothing is downloaded for them, and each keeps its
licence, which goes into `THIRD-PARTY-NOTICES.txt` (`engine/tools/third_party_notices.py`). The
bigger ones are downloads, fetched the first time they're asked for
(`engine/src/mado/downloads.json`), each with its licence beside it: RealESRGAN x4plus (Best for
photos, 67 MB) and LaMa (extending edges and erasing at Best, 209 MB) from Mado's own release
`models-1`; SAM 2.1 (picking a part, 156 MB), MI-GAN (erasing at Fast, 28 MB) and BiRefNet lite
(cutting out at Best, 224 MB) from `models-2`.

| File | What it is | Licence | SHA-256 |
| --- | --- | --- | --- |
| `realesr-general-x4v3.onnx` | Real-ESRGAN's general model (v0.2.5.0), four times bigger: Fast, for photos and drawings; it takes noise and JPEG blocks out | BSD-3-Clause, Xintao Wang (`LICENSE-Real-ESRGAN.txt`) | `22955412e704d0c7da459ba118a0aad0ce9e545b8004cec0588cce822cc61c8e` |
| `realesr-general-wdn-x4v3.onnx` | Its weak-denoise twin: Fast with cleaning turned off, keeping grain | BSD-3-Clause, Xintao Wang (`LICENSE-Real-ESRGAN.txt`) | `568c87f30c75d4a18de830b69f97805acc194436642cd97180591a58d44c5605` |
| `realesrgan-x4plus-anime-6b.onnx` | RealESRGAN x4plus's anime model (v0.2.2.4): Best for drawings, comics and flat-colour art | BSD-3-Clause, Xintao Wang, and Apache-2.0 for BasicSR's network (`LICENSE-Real-ESRGAN.txt`, `LICENSE-BasicSR.txt`) | `c489130a7221324ca4473ce22bdd1b7dc91426a7aeac96393425b675dfd6276d` |
| `u2netp.onnx` | U²-Net's small model (U2NETP), 320 × 320: finds a picture's subject, to cut it out at Fast. 4.6 MB, so it ships: Fast cut-outs work offline and in a recipe from the first run | Apache-2.0, the U-2-Net authors (`LICENSE-U-2-Net.txt`); its ONNX conversion is rembg's, MIT, Daniel Gatis (`LICENSE-rembg.txt`) | `309c8469258dda742793dce0ebea8e6dd393174f89934733ecc8b14c76f4ddd8` |

How the Real-ESRGAN models were made: exported to ONNX (opset 17, full precision, `dynamo=False`) from the official
weights of Real-ESRGAN's releases with PyTorch 2.15 and onnx 1.23.2, then checked against
PyTorch on the processor and on DirectML (a mean difference under a millionth). Each takes
`input`, float32 `[batch, 3, height, width]` RGB from 0 to 1, and gives `output`, four times as
wide and high, clamped to 0 to 1. Mado pins batch, height and width to its tile size as each
session is made (`mado/directml.py`).

u2netp is rembg's published ONNX file of U²-Net's own weights (its v0.0.0 release), byte for byte:
`input.1`, float32 `[1, 3, 320, 320]` with ImageNet's mean and spread, giving the subject at
320 × 320 from 0 to 1 as its first output.

Why these: measured on the owner's GTX 1660 Super on 2026-11-22 against the rest of the
shortlist, see [docs/stack/upscaling.md](../../../../docs/stack/upscaling.md) and
[docs/stack/editing.md](../../../../docs/stack/editing.md).
