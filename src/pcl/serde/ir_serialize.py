from ..datamodel import CompiledTemplate, VarRef, Conditional
from ..errors import PCLError

def serialize(template: CompiledTemplate) -> dict:
    """Convert a CompiledTemplate to a plain dict suitable for CBOR encoding."""
    return {
        "pcl_version": 1,
        "metadata": template.metadata,
        "segments": _serialize_segments(template.segments),
    }

def _serialize_segments(segments: list) -> list:
    return [_serialize_segment(s) for s in segments]


def _serialize_segment(seg) -> dict | str:
    if isinstance(seg, str):
        return {"type": "text", "value": seg}
    if isinstance(seg, VarRef):
        return {"type": "var", "name": seg.name, "default": seg.default, "line": seg.line}
    if isinstance(seg, Conditional):
        return {
            "type": "if",
            "variable": seg.variable,
            "negated": seg.negated,
            "line": seg.line,
            "body": _serialize_segments(seg.body),
        }
    raise PCLError(f"Unknown segment type: {type(seg)!r}")  # pragma: no cover