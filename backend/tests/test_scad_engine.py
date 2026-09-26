import sys
from threading import Event
from pathlib import Path

from app.scad.engine import ScadEngine


class FakeEngine(ScadEngine):
    def __init__(self, script: Path):
        super().__init__(sys.executable)
        self.script = script
        self.timeout_seconds = 2

    def command(self, source, output, definitions, parameters, mode):
        action = parameters.pop("_test_action", "success")
        return [sys.executable, str(self.script), action, str(output)]

    def validate_parameters(self, definitions, supplied):
        return dict(supplied)

    def version(self):
        return "OpenSCAD version 2021.01"


def fake_script(tmp_path: Path) -> Path:
    path = tmp_path / "fake_openscad.py"
    path.write_text('''
import pathlib, sys, time
action, output = sys.argv[1:]
if action == "timeout": time.sleep(5)
elif action == "invalid":
    print("ERROR: Parser error: syntax error", file=sys.stderr)
    raise SystemExit(1)
elif action == "missing": raise SystemExit(0)
elif action == "large":
    print("x" * 250000)
    pathlib.Path(output).write_bytes(b"solid fake")
else:
    pathlib.Path(output).write_bytes(b"solid fake")
    print('ECHO: "INFO:ring_teeth=49"')
''', encoding="utf-8")
    return path


def render(tmp_path: Path, action: str):
    source = tmp_path / f"source-{action}"
    source.mkdir()
    (source / "main.scad").write_text("cube(1);", encoding="utf-8")
    return FakeEngine(fake_script(tmp_path)).render(source, "main.scad", [], {"_test_action": action}, tmp_path / f"{action}.stl")


def test_successful_render_and_metadata(tmp_path):
    result = render(tmp_path, "success")
    assert result.status == "completed"
    assert result.metadata["info"][0]["key"] == "ring_teeth"


def test_invalid_scad_and_missing_output_are_friendly(tmp_path):
    invalid = render(tmp_path, "invalid")
    assert invalid.error_code == "INVALID_SCAD"
    missing = render(tmp_path, "missing")
    assert missing.error_code == "OUTPUT_MISSING"


def test_timeout_terminates_process(tmp_path):
    engine = FakeEngine(fake_script(tmp_path))
    engine.timeout_seconds = 0
    source = tmp_path / "source-timeout"; source.mkdir()
    (source / "main.scad").write_text("cube(1);", encoding="utf-8")
    result = engine.render(source, "main.scad", [], {"_test_action": "timeout"}, tmp_path / "timeout.stl")
    assert result.status == "timed_out"


def test_cancelled_render_is_terminated(tmp_path):
    source = tmp_path / "source-cancel"; source.mkdir(); (source / "main.scad").write_text("cube(1);", encoding="utf-8")
    cancel = Event(); cancel.set()
    result = FakeEngine(fake_script(tmp_path)).render(source, "main.scad", [], {"_test_action":"timeout"}, tmp_path / "cancel.stl", cancel=cancel)
    assert result.status == "cancelled"


def test_missing_include_is_reported_before_process_start(tmp_path):
    source = tmp_path / "source-include"; source.mkdir(); (source / "main.scad").write_text("include <missing.scad>\ncube(1);", encoding="utf-8")
    result = FakeEngine(fake_script(tmp_path)).render(source, "main.scad", [], {}, tmp_path / "missing-include.stl")
    assert result.error_code == "MISSING_INCLUDE"


def test_large_stdout_is_truncated(tmp_path):
    result = render(tmp_path, "large")
    assert result.status == "completed"
    assert len(result.stdout) == 200000


def test_openscad_not_installed_and_unsupported_version(tmp_path):
    source = tmp_path / "source-engine"; source.mkdir(); (source / "main.scad").write_text("cube(1);", encoding="utf-8")
    missing = ScadEngine(str(tmp_path / "does-not-exist"))
    assert missing.render(source,"main.scad",[],{},tmp_path/"none.stl").error_code == "OPENSCAD_NOT_INSTALLED"
    old = FakeEngine(fake_script(tmp_path)); old.version = lambda: "OpenSCAD version 2019.05"
    assert old.render(source,"main.scad",[],{},tmp_path/"old.stl").error_code == "OPENSCAD_UNSUPPORTED"


def test_parameter_serialization_escapes_strings_and_checks_ranges():
    engine = ScadEngine("openscad")
    assert engine.serialize('quote " and slash \\', "string") == '"quote \\" and slash \\\\"'
    definitions = [{"name":"x","type":"integer","defaultValue":5,"min":1,"max":10,"step":1,"options":[]}]
    assert engine.validate_parameters(definitions,{"x":8}) == {"x":8}
