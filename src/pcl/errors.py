"""PCL error types with line number context."""


class PCLError(Exception):
    """Raised for any PCL parse or compile error."""

    def __init__(
        self,
        message: str,
        *,
        line: int | None = None,
        file: str | None = None,
    ) -> None:
        self.line = line
        self.file = file
        parts: list[str] = []
        if file:
            parts.append(file)
        if line is not None:
            parts.append(str(line))
        prefix = ":".join(parts)
        full = f"{prefix}: {message}" if prefix else message
        super().__init__(full)
