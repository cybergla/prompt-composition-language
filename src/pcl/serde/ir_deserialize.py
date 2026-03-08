from ..datamodel import CompiledTemplate, VarRef, Conditional, Segment
from ..errors import PCLError

def deserialize(data: dict) -> CompiledTemplate:
    """Reconstruct a CompiledTemplate from a plain dict (decoded from CBOR)."""
    if data.get("pcl_version") != 1:
        raise PCLError(f"Unsupported .pclc version: {data.get('pcl_version')!r}")
    return CompiledTemplate(
        metadata=data.get("metadata", {}),
        segments=_deserialize_segments(data["segments"]),
    )

def _deserialize_segments(raw: list) -> list:
    return [_deserialize_segment(s) for s in raw]


def _deserialize_segment(s: dict) -> Segment:
    t = s.get("type")
    if t == "text":
        return s["value"]
    if t == "var":
        return VarRef(name=s["name"], default=s.get("default"), line=s["line"])
    if t == "if":
        return Conditional(
            variable=s["variable"],
            negated=s["negated"],
            body=_deserialize_segments(s["body"]),
            line=s["line"],
        )
    raise PCLError(f"Unknown segment type in .pclc: {t!r}")