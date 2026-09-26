from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from .models import ScadParameter


SECTION_RE = re.compile(r"^\s*/\*\s*\[([^]]+)]\s*\*/\s*$")
ASSIGNMENT_RE = re.compile(
    r'^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(true|false|[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?|"(?:\\.|[^"\\])*")\s*;\s*(?://\s*(.*))?$'
)
CUSTOMIZER_RE = re.compile(r"\[\s*([^]]+)\s*]")
TAG_RE = re.compile(r"@(label|description|unit|group|order)\s*:\s*(\"(?:\\.|[^\"])*\"|'(?:\\.|[^'])*'|[^@\s]+)|@(hidden|advanced)\b")
INCLUDE_RE = re.compile(r"\b(?:include|use)\s*<([^>]+)>")
FILE_CALL_RE = re.compile(r"\b(?:import|surface)\s*\([^)]*?(?:file\s*=\s*)?[\"']([^\"']+)[\"']", re.DOTALL)
FILE_CALL_ANY_RE = re.compile(r"\b(?:import|surface)\s*\(", re.IGNORECASE)


@dataclass
class ParseResult:
    parameters: list[ScadParameter]
    includes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _humanize(name: str) -> str:
    return name.replace("_", " ").strip().capitalize()


def _literal(raw: str):
    if raw == "true":
        return True
    if raw == "false":
        return False
    if raw.startswith('"'):
        return ast.literal_eval(raw)
    number = float(raw)
    return int(number) if number.is_integer() and not any(c in raw.lower() for c in (".", "e")) else number


def _tag_value(raw: str) -> str:
    raw = raw.strip()
    if raw[:1] in {'"', "'"}:
        try:
            return str(ast.literal_eval(raw))
        except (ValueError, SyntaxError):
            return raw[1:-1]
    return raw


def _parse_customizer(raw: str, default) -> tuple[dict, list[str]]:
    matches = CUSTOMIZER_RE.findall(raw)
    if not matches:
        return {}, []
    value = matches[0].strip()
    if ":" in value:
        parts = [part.strip() for part in value.split(":")]
        if len(parts) == 3:
            try:
                low, step, high = (float(part) for part in parts)
                numeric = {"min": low, "step": step, "max": high}
                if isinstance(default, int) and all(item.is_integer() for item in (low, step, high)):
                    numeric = {key: int(item) for key, item in numeric.items()}
                return numeric, []
            except ValueError:
                return {}, [f"Nieprawidłowy zakres Customizera: [{value}]"]
        return {}, [f"Nieprawidłowy zakres Customizera: [{value}]"]
    options = [part.strip().strip('"\'') for part in value.split(",") if part.strip()]
    return ({"options": options} if options else {}), []


class ScadParser:
    """Parser declarative OpenSCAD Customizer metadata, not a SCAD interpreter."""

    def parse(self, source: str) -> ParseResult:
        parameters: list[ScadParameter] = []
        warnings: list[str] = []
        section = "General"
        lines = source.splitlines()
        preceding_comments: list[str] = []

        for index, line in enumerate(lines):
            section_match = SECTION_RE.match(line)
            if section_match:
                section = section_match.group(1).strip() or "General"
                preceding_comments.clear()
                continue
            stripped = line.strip()
            if stripped.startswith("//"):
                preceding_comments.append(stripped[2:].strip())
                continue
            match = ASSIGNMENT_RE.match(line)
            if not match:
                if stripped and not stripped.startswith(("/*", "*", "*/")):
                    preceding_comments.clear()
                continue

            name, raw_default, inline = match.groups()
            try:
                default = _literal(raw_default)
            except (ValueError, SyntaxError):
                warnings.append(f"Pominięto parametr {name}: nieprawidłowa wartość domyślna")
                continue

            metadata_text = inline or ""
            if index + 1 < len(lines) and lines[index + 1].strip().startswith("//"):
                next_comment = lines[index + 1].strip()[2:].strip()
                if next_comment.startswith(("[", "@")):
                    metadata_text += " " + next_comment

            custom, custom_warnings = _parse_customizer(metadata_text, default)
            warnings.extend(custom_warnings)
            tags: dict[str, str | bool] = {}
            for tag in TAG_RE.finditer(metadata_text):
                if tag.group(3):
                    tags[tag.group(3)] = True
                else:
                    tags[tag.group(1)] = _tag_value(tag.group(2))

            options = custom.get("options", [])
            if isinstance(default, bool):
                kind = "boolean"
            elif options:
                kind = "enum"
            elif isinstance(default, int):
                kind = "integer"
            elif isinstance(default, float):
                kind = "float"
            else:
                kind = "string"

            description = str(tags.get("description", ""))
            plain_comments = [item for item in preceding_comments[-2:] if not item.startswith(("[", "@"))]
            if not description and plain_comments:
                description = plain_comments[-1]
            parameter_section = str(tags.get("group", section))
            advanced = bool(tags.get("advanced")) or parameter_section.lower() == "advanced"
            try:
                order = int(str(tags.get("order", len(parameters))))
            except ValueError:
                order = len(parameters)
                warnings.append(f"Nieprawidłowy @order dla {name}")
            parameters.append(ScadParameter(
                id=name,
                name=name,
                label=str(tags.get("label", _humanize(name))),
                description=description,
                section=parameter_section,
                type=kind,
                defaultValue=default,
                currentValue=default,
                min=custom.get("min"),
                max=custom.get("max"),
                step=custom.get("step"),
                options=options,
                order=order,
                hidden=bool(tags.get("hidden")) or section.lower() == "hidden",
                advanced=advanced,
                unit=str(tags.get("unit", "")),
            ))
            preceding_comments.clear()

        includes = sorted(set(INCLUDE_RE.findall(source) + FILE_CALL_RE.findall(source)))
        return ParseResult(sorted(parameters, key=lambda item: (item.order, item.name)), includes, warnings)

    def parse_file(self, path: Path) -> ParseResult:
        return self.parse(path.read_text(encoding="utf-8"))


def validate_source_tree(root: Path) -> list[str]:
    """Reject path escapes before an untrusted module reaches OpenSCAD."""
    missing: list[str] = []
    parser = ScadParser()
    for source_file in root.rglob("*.scad"):
        source = source_file.read_text(encoding="utf-8")
        result = parser.parse(source)
        literal_calls = FILE_CALL_RE.findall(source)
        if len(FILE_CALL_ANY_RE.findall(source)) != len(literal_calls):
            raise ValueError(f"Dynamiczna ścieżka import/surface jest niedozwolona: {source_file.name}")
        for reference in result.includes:
            normalized = PurePosixPath(reference.replace("\\", "/"))
            if normalized.is_absolute() or ".." in normalized.parts or re.match(r"^[A-Za-z]:", reference):
                raise ValueError(f"Niedozwolona ścieżka w SCAD: {reference}")
            target = (source_file.parent / Path(*normalized.parts)).resolve()
            try:
                target.relative_to(root.resolve())
            except ValueError as exc:
                raise ValueError(f"Ścieżka wychodzi poza katalog modułu: {reference}") from exc
            if not target.is_file():
                missing.append(reference)
    return sorted(set(missing))
