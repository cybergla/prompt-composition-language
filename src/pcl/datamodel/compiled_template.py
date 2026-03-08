from dataclasses import dataclass

from .ir_segment_types import Segment

@dataclass
class CompiledTemplate:
    """Result of compile(). All structural resolution is done; only variable
    substitution and conditional evaluation remain."""

    metadata: dict
    segments: list[Segment]