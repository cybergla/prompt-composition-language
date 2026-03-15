from dataclasses import dataclass, field

@dataclass
class FrontmatterNode:
    data: dict
    line: int = 0


@dataclass
class ImportNode:
    path: str
    namespace: str
    line: int


@dataclass
class BlockDefNode:
    name: str
    body: list  # list[BodyNode]
    line: int


@dataclass
class IncludeNode:
    ref: str
    line: int


@dataclass
class IfNode:
    variable: str
    negated: bool
    body: list  # list[BodyNode]
    line: int


@dataclass
class RawNode:
    lines: list[str]
    line: int


@dataclass
class TextNode:
    text: str
    line: int


@dataclass
class ParsedFile:
    frontmatter: FrontmatterNode | None
    imports: list[ImportNode]
    body: list  # list[BodyNode]
    filename: str = "<string>"