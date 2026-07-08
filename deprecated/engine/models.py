from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ProjectManifest:
    root: str
    languages: list[str] = field(default_factory=list)
    frameworks: list[str] = field(default_factory=list)
    package_managers: list[str] = field(default_factory=list)
    entrypoints: list[str] = field(default_factory=list)
    config_files: list[str] = field(default_factory=list)
    build_commands: list[list[str]] = field(default_factory=list)
    test_commands: list[list[str]] = field(default_factory=list)
    files: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SymbolRecord:
    name: str
    kind: str
    file: str
    line: int
    column: int = 0
    parent: str | None = None
    parameters: list[str] = field(default_factory=list)
    returns: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DependencyGraph:
    imports: dict[str, list[str]] = field(default_factory=dict)
    exports: dict[str, list[str]] = field(default_factory=dict)
    inheritance: dict[str, list[str]] = field(default_factory=dict)
    calls: dict[str, list[str]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BuildResult:
    command: list[str]
    cwd: str
    stdout: str
    stderr: str
    exit_code: int
    duration_ms: int

    @property
    def ok(self) -> bool:
        return self.exit_code == 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ParsedError:
    category: str
    message: str
    file: str | None = None
    line: int | None = None
    column: int | None = None
    raw: str = ""

    def key(self) -> tuple[str, str | None, int | None, str]:
        return (self.category, self.file, self.line, self.message)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RootCause:
    primary: list[ParsedError]
    secondary: list[ParsedError] = field(default_factory=list)
    dependency_chain: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "primary": [e.to_dict() for e in self.primary],
            "secondary": [e.to_dict() for e in self.secondary],
            "dependency_chain": self.dependency_chain,
        }


@dataclass
class StageLog:
    stage: str
    duration_ms: int
    files_modified: list[str] = field(default_factory=list)
    tokens: int = 0
    llm_cost: float = 0.0
    result: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
