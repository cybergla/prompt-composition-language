from dataclasses import dataclass

@dataclass
class VarRef:
    """A variable placeholder to be resolved at render time."""

    name: str
    default: str | None
    line: int


@dataclass
class Conditional:
    """A conditional branch to be evaluated at render time."""

    variable: str
    negated: bool
    body: list  # list[str | VarRef | Conditional]
    line: int


# Segment = str | VarRef | Conditional
Segment = str | VarRef | Conditional