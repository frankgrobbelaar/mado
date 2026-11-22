"""The AI models Mado makes pictures bigger with, and which one suits a picture. Pure.

All four are Real-ESRGAN (BSD-3-Clause), each four times bigger: the general model for photos,
fast and small, with its weak-denoise twin for keeping grain; RealESRGAN_x4plus, the best for
photos, a download; and its anime model, the best for drawings. docs/stack/upscaling.md has how
they were chosen and timed.
"""

from dataclasses import dataclass
from typing import Literal

from mado.core.kind import Kind

type Quality = Literal["fast", "best"]
type ModelId = Literal[
    "realesr-general-x4v3",
    "realesr-general-wdn-x4v3",
    "realesrgan-x4plus",
    "realesrgan-x4plus-anime-6b",
]

SCALE = 4  # every model makes its picture four times bigger each way


@dataclass(frozen=True)
class Model:
    id: ModelId
    file: str  # its file: in Mado's assets, or the download's folder
    name: str  # as people read it
    download: str | None  # downloads.json's id when it's fetched the first time it's asked for
    heavy: bool  # wants smaller tiles on a card with little memory of its own
    cleans: bool  # takes noise and JPEG blocks out as it goes


FAST = Model(
    "realesr-general-x4v3",
    "realesr-general-x4v3.onnx",
    "Real-ESRGAN general",
    None,
    heavy=False,
    cleans=True,
)
FAST_GRAIN = Model(
    "realesr-general-wdn-x4v3",
    "realesr-general-wdn-x4v3.onnx",
    "Real-ESRGAN general, keeping grain",
    None,
    heavy=False,
    cleans=False,
)
BEST_PHOTO = Model(
    "realesrgan-x4plus",
    "realesrgan-x4plus.onnx",
    "RealESRGAN x4plus",
    "realesrgan-x4plus",
    heavy=True,
    cleans=True,
)
BEST_DRAWING = Model(
    "realesrgan-x4plus-anime-6b",
    "realesrgan-x4plus-anime-6b.onnx",
    "RealESRGAN x4plus for drawings",
    None,
    heavy=True,
    cleans=True,
)
MODELS: dict[ModelId, Model] = {
    model.id: model for model in (FAST, FAST_GRAIN, BEST_PHOTO, BEST_DRAWING)
}


def model_for(kind: Kind, quality: Quality, clean: bool) -> Model | None:
    """The model a picture is made bigger with: a photo's or a drawing's, Fast or Best; Fast
    keeping grain when the owner turned cleaning off. None for pixel art and screenshots, which
    no AI touches."""
    match kind:
        case "pixels" | "screenshot":
            return None
        case "photo" if quality == "best":
            return BEST_PHOTO
        case "drawing" if quality == "best":
            return BEST_DRAWING
        case _:
            return FAST if clean else FAST_GRAIN
