"""The little of ONNX Runtime that Mado uses, typed: the package ships no type information."""

from collections.abc import Mapping, Sequence
from enum import Enum
from typing import Any

import numpy.typing as npt

__version__: str

class ExecutionMode(Enum):
    ORT_SEQUENTIAL = 0
    ORT_PARALLEL = 1

class GraphOptimizationLevel(Enum):
    ORT_DISABLE_ALL = 0
    ORT_ENABLE_BASIC = 1
    ORT_ENABLE_EXTENDED = 2
    ORT_ENABLE_ALL = 99

class SessionOptions:
    enable_mem_pattern: bool
    execution_mode: ExecutionMode
    graph_optimization_level: GraphOptimizationLevel
    intra_op_num_threads: int
    def __init__(self) -> None: ...
    def add_free_dimension_override_by_name(self, dim_name: str, dim_value: int) -> None: ...
    def add_session_config_entry(self, config_key: str, config_value: str) -> None: ...

class NodeArg:
    name: str
    shape: list[int | str | None]

class ModelMetadata:
    custom_metadata_map: dict[str, str]

type Provider = str | tuple[str, Mapping[str, object]]

class InferenceSession:
    def __init__(
        self,
        path_or_bytes: str | bytes,
        sess_options: SessionOptions | None = None,
        providers: Sequence[Provider] | None = None,
    ) -> None: ...
    def run(
        self,
        output_names: Sequence[str] | None,
        input_feed: Mapping[str, npt.NDArray[Any]],
    ) -> list[npt.NDArray[Any]]: ...
    def get_providers(self) -> list[str]: ...
    def get_inputs(self) -> list[NodeArg]: ...
    def get_outputs(self) -> list[NodeArg]: ...
    def get_modelmeta(self) -> ModelMetadata: ...

def get_available_providers() -> list[str]: ...
def disable_telemetry_events() -> None: ...
