"""The stdio_json frame (the specification's section 12), held over two real entrypoints.

The reference package's entrypoint answers scalar outputs in band; the fixture in
``tests/fixtures/stdio_frame/`` answers a field and its band by reference, in the
shape a grid field producer documents for the packages it emits. Each is run the
way a consumer runs it -- one request on stdin, a working directory of its own --
in ``single`` and ``batch`` mode, for answers and for refusals, and every frame it
writes must hold under ``opencontractml.verify.frame_problems``. Defects planted in
real frames -- a declared output removed, a digest that is not the file's, a path
out of the working directory -- must not.
"""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from opencontractml import verify as vs

REPO = Path(__file__).resolve().parents[1]
REFERENCE_PACKAGE = REPO / "examples" / "reference-package"
GRID_FIELD = REPO / "tests" / "fixtures" / "stdio_frame" / "grid_field_predict.py"

#: The grid-field fixture's declaration: one field output, its band named by lower_field / upper_field.
GRID_FIELD_MANIFEST = {
    "spec_version": "1.1",
    "outputs": [{"name": "dT", "type": "field", "units": "K", "viewer": "field_contour",
                 "field": {"kind": "scalar", "units": "K", "support": "node",
                           "media_type": "application/vnd.vtk.vtp+xml", "shape": [4, 4],
                           "coordinate_ref": "nodes of a regular 4 x 4 grid, row-major, axis order (y, x)"}}],
    "uncertainty": {"form": "predictive_interval",
                    "per_output": {"dT": {"lower_field": "dT_lower", "upper_field": "dT_upper", "level": 0.9}}},
}
GRID_ROWS = [{"source_P_W": 12.0, "h_W_m2K": 60.0}, {"source_P_W": 25.0, "h_W_m2K": 10.0},
             {"source_P_W": 1.0, "h_W_m2K": 300.0}]
REFERENCE_ROWS = [{"peak_temp_K": 773.15, "cycle_count": 5000, "material": "GG25"},
                  {"peak_temp_K": 1023.15, "cycle_count": 20000, "material": "GGG70"}]


def _reference_manifest() -> dict:
    yaml = pytest.importorskip("yaml", reason="the reference package ships manifest.yaml")
    return yaml.safe_load((REFERENCE_PACKAGE / "manifest.yaml").read_text(encoding="utf-8"))


def dispatch(entrypoint: Path, request, run_dir: Path) -> subprocess.CompletedProcess:
    """Run an entrypoint once, as a consumer does: the request on stdin, then EOF, in its own working directory."""
    run_dir.mkdir(parents=True, exist_ok=True)
    payload = request if isinstance(request, str) else json.dumps(request)
    return subprocess.run([sys.executable, str(entrypoint)], input=payload + "\n", capture_output=True, text=True,
                          timeout=60, cwd=str(run_dir))


def frames_of(proc: subprocess.CompletedProcess) -> list:
    frames, problem = vs.read_frames(proc.stdout, strict=True)
    assert problem is None, problem
    return frames


# --------------------------------------------------------------------------- #
# The reference package's entrypoint: outputs and band in band.
# --------------------------------------------------------------------------- #
def test_the_reference_entrypoint_answers_a_single_request_in_the_frame(tmp_path: Path):
    man = _reference_manifest()
    proc = dispatch(REFERENCE_PACKAGE / "predict.py", vs.stdio_request("r-1", REFERENCE_ROWS[0]), tmp_path / "run")
    assert proc.returncode == 0, proc.stderr
    [frame] = frames_of(proc)
    assert frame["status"] == "ok" and frame["run_id"] == "r-1"
    assert vs.frame_problems(frame, man, tmp_path / "run", "r-1") == []
    assert list((tmp_path / "run").iterdir()) == [], "the entrypoint wrote into its working directory unasked"


def test_the_reference_entrypoint_answers_a_batch_with_a_frame_per_row_in_order(tmp_path: Path):
    man = _reference_manifest()
    assert man["invocation"]["batch_supported"] is True
    proc = dispatch(REFERENCE_PACKAGE / "predict.py", vs.stdio_request("r-2", REFERENCE_ROWS), tmp_path / "run")
    assert proc.returncode == 0, proc.stderr
    frames = frames_of(proc)
    assert len(frames) == len(REFERENCE_ROWS)
    singles = [frames_of(dispatch(REFERENCE_PACKAGE / "predict.py", vs.stdio_request("r-3", row), tmp_path / "s"))[0]
               for row in REFERENCE_ROWS]
    for frame, single in zip(frames, singles):
        assert vs.frame_problems(frame, man, tmp_path / "run", "r-2") == []
        assert frame["outputs"] == single["outputs"]            # in order: row k answers row k


@pytest.mark.parametrize("request_body,code,field", [
    (vs.stdio_request("r-4", dict(REFERENCE_ROWS[0], material="GG99")), "OUT_OF_RANGE", "material"),
    (vs.stdio_request("r-4", {"peak_temp_K": 773.15, "material": "GG25"}), "MISSING_INPUT", "cycle_count"),
    ("this is not JSON", "BAD_REQUEST", None),
    (vs.stdio_request("r-4", REFERENCE_ROWS[0], mode="batch"), "BAD_REQUEST", None),
], ids=["outside the choices", "a missing input", "stdin not JSON", "batch without an array"])
def test_the_reference_entrypoint_declines_in_band_with_exit_0(tmp_path: Path, request_body, code, field):
    proc = dispatch(REFERENCE_PACKAGE / "predict.py", request_body, tmp_path / "run")
    assert proc.returncode == 0, "a refusal is an answer, not a crash"
    [frame] = frames_of(proc)
    assert frame["status"] == "error" and frame["error"]["code"] == code
    assert frame["error"].get("field") == field and frame["error"]["message"]


def test_one_declined_row_does_not_stop_a_batch(tmp_path: Path):
    rows = [REFERENCE_ROWS[0], dict(REFERENCE_ROWS[1], material="GG99"), REFERENCE_ROWS[1]]
    frames = frames_of(dispatch(REFERENCE_PACKAGE / "predict.py", vs.stdio_request("r-5", rows), tmp_path / "run"))
    assert [f["status"] for f in frames] == ["ok", "error", "ok"]


# --------------------------------------------------------------------------- #
# The grid-field fixture: a field and its band by reference.
# --------------------------------------------------------------------------- #
def test_the_grid_field_entrypoint_answers_by_reference(tmp_path: Path):
    run = tmp_path / "run"
    proc = dispatch(GRID_FIELD, vs.stdio_request("g-1", GRID_ROWS[0]), run)
    assert proc.returncode == 0, proc.stderr
    [frame] = frames_of(proc)
    assert vs.frame_problems(frame, GRID_FIELD_MANIFEST, run, "g-1") == []
    for key in ("dT", "dT_lower", "dT_upper"):
        ref = frame["outputs"][key]
        assert ref["kind"] == "artifact" and (run / ref["path"]).is_file()
        assert hashlib.sha256((run / ref["path"]).read_bytes()).hexdigest() == ref["sha256"]
    assert {"dT_max_K", "units", "grid"} <= set(frame["outputs"])     # keys beyond the declaration are allowed


def test_the_grid_field_entrypoint_answers_a_batch_with_its_own_files_per_row(tmp_path: Path):
    run = tmp_path / "run"
    frames = frames_of(dispatch(GRID_FIELD, vs.stdio_request("g-2", GRID_ROWS), run))
    assert len(frames) == len(GRID_ROWS)
    paths = [frame["outputs"]["dT"]["path"] for frame in frames]
    assert len(set(paths)) == len(GRID_ROWS), "one path cannot carry two digests"
    for frame in frames:
        assert vs.frame_problems(frame, GRID_FIELD_MANIFEST, run, "g-2") == []


@pytest.mark.parametrize("row,code,field", [
    ({"source_P_W": 40.0, "h_W_m2K": 60.0}, "OUT_OF_RANGE", "source_P_W"),
    ({"h_W_m2K": 60.0}, "MISSING_INPUT", "source_P_W"),
    ({"source_P_W": "twelve", "h_W_m2K": 60.0}, "BAD_REQUEST", "source_P_W"),
])
def test_the_grid_field_entrypoint_declines_in_band_and_writes_nothing(tmp_path: Path, row, code, field):
    run = tmp_path / "run"
    proc = dispatch(GRID_FIELD, vs.stdio_request("g-3", row), run)
    assert proc.returncode == 0
    [frame] = frames_of(proc)
    assert frame["status"] == "error" and frame["error"]["code"] == code and frame["error"]["field"] == field
    assert list(run.iterdir()) == []


# --------------------------------------------------------------------------- #
# Planted defects in real frames: each must be named, under the rule that owns it.
# --------------------------------------------------------------------------- #
@pytest.fixture()
def answered(tmp_path: Path):
    run = tmp_path / "run"
    [frame] = frames_of(dispatch(GRID_FIELD, vs.stdio_request("g-4", GRID_ROWS[1]), run))
    assert vs.frame_problems(frame, GRID_FIELD_MANIFEST, run, "g-4") == []
    return frame, run


def _rules(problems) -> list:
    return sorted({rule for rule, _ in problems})


def test_a_frame_missing_a_declared_output_is_red(answered):
    frame, run = answered
    planted = copy.deepcopy(frame)
    del planted["outputs"]["dT"]
    problems = vs.frame_problems(planted, GRID_FIELD_MANIFEST, run, "g-4")
    assert _rules(problems) == ["S001"]
    assert "omits declared output(s) ['dT']" in problems[0][1]


def test_a_frame_missing_a_band_key_is_red(answered):
    frame, run = answered
    planted = copy.deepcopy(frame)
    del planted["outputs"]["dT_upper"]
    assert _rules(vs.frame_problems(planted, GRID_FIELD_MANIFEST, run, "g-4")) == ["S001"]


def test_a_reference_whose_digest_is_not_the_files_is_red(answered):
    frame, run = answered
    planted = copy.deepcopy(frame)
    planted["outputs"]["dT"]["sha256"] = "0" * 64
    problems = vs.frame_problems(planted, GRID_FIELD_MANIFEST, run, "g-4")
    assert _rules(problems) == ["S003"]
    assert "sha256 mismatch for 'dT.vtp'" in problems[0][1]


def test_a_file_changed_after_its_reference_was_written_is_red(answered):
    frame, run = answered
    with open(run / frame["outputs"]["dT_lower"]["path"], "a", encoding="utf-8") as fh:
        fh.write(" ")
    problems = vs.frame_problems(frame, GRID_FIELD_MANIFEST, run, "g-4")
    assert _rules(problems) == ["S003"]
    assert "bytes, not the declared" in problems[0][1]


@pytest.mark.parametrize("path,why", [
    ("../dT.vtp", "resolves outside the run's working directory"),
    ("/etc/hosts", "is absolute"),
    ("missing.vtp", "names no file"),
])
def test_a_reference_whose_path_is_not_a_file_in_the_working_directory_is_red(answered, path, why):
    frame, run = answered
    planted = copy.deepcopy(frame)
    planted["outputs"]["dT"]["path"] = path
    problems = vs.frame_problems(planted, GRID_FIELD_MANIFEST, run, "g-4")
    assert _rules(problems) == ["S003"] and why in problems[0][1], problems


def test_a_declared_field_answered_in_band_is_red(answered):
    frame, run = answered
    planted = copy.deepcopy(frame)
    planted["outputs"]["dT"] = [1.0, 2.0, 3.0]
    problems = vs.frame_problems(planted, GRID_FIELD_MANIFEST, run, "g-4")
    assert _rules(problems) == ["S003"] and "is not an artifact reference" in problems[0][1]


def test_from_1_1_a_frame_carries_status_and_echoes_run_id(answered):
    frame, run = answered
    no_status = {k: v for k, v in frame.items() if k != "status"}
    assert _rules(vs.frame_problems(no_status, GRID_FIELD_MANIFEST, run, "g-4")) == ["S001"]
    assert _rules(vs.frame_problems(frame, GRID_FIELD_MANIFEST, run, "another-run")) == ["S001"]
    as_1_0 = dict(GRID_FIELD_MANIFEST, spec_version="1.0")
    assert vs.frame_problems(no_status, as_1_0, run, "another-run") == []      # what a 1.0 entrypoint wrote


def test_reference_problems_names_every_key_a_reference_lacks(tmp_path: Path):
    problems = vs.reference_problems({"kind": "artifact"}, tmp_path)
    assert problems == ["lacks %r" % key for key in vs.REFERENCE_KEYS if key != "kind"]
    bad = {"kind": "file", "path": "x.vtp", "media_type": "VTK PolyData", "sha256": "ABC", "bytes": -1,
           "field": {"name": "", "units": 5, "range": [3.0, 1.0], "n_nodes": 0}}
    problems = vs.reference_problems(bad, tmp_path)
    for fragment in ("kind 'file'", "media_type 'VTK PolyData'", "sha256 'ABC'", "bytes -1", "field.name ''",
                     "field.units 5", "field.range [3.0, 1.0]", "field.n_nodes 0"):
        assert any(fragment in p for p in problems), (fragment, problems)


def test_read_frames_refuses_a_line_that_is_not_a_frame_from_1_1():
    stdout = 'model loaded\n{"run_id": "x", "status": "ok", "outputs": {}}\n'
    frames, problem = vs.read_frames(stdout, strict=True)
    assert problem is not None and "not a frame" in problem
    frames, problem = vs.read_frames(stdout, strict=False)
    assert problem is None and len(frames) == 1
    frames, problem = vs.read_frames('{\n  "run_id": "x",\n  "status": "ok",\n  "outputs": {}\n}\n', strict=True)
    assert problem is None and len(frames) == 1                  # one object over several lines is one frame


def test_the_reference_reports_serve_parity_reproduces(tmp_path: Path):
    """C2_serve_parity: the 12 cases its method names, served through the frame, against the in-process fit."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("reference_predict", REFERENCE_PACKAGE / "predict.py")
    model = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(model)
    weights = model.load_weights()
    cases = [{"peak_temp_K": t, "cycle_count": 5000, "material": m}
             for t in (473.15, 773.15, 973.15, 1123.15) for m in ("GG20", "GG25", "GGG70")]
    worst = 0.0
    for case in cases:
        [frame] = frames_of(dispatch(REFERENCE_PACKAGE / "predict.py", vs.stdio_request("c2", case), tmp_path / "r"))
        for key, value in model.predict(case, weights).items():
            worst = max(worst, abs(frame["outputs"][key] - value) / abs(value))
    report = json.loads((REFERENCE_PACKAGE / "validation_report.json").read_text(encoding="utf-8"))
    c2 = report["checks"]["C2_serve_parity"]
    assert c2["metrics"] == {"max_rel_diff": worst, "n_cases": len(cases)}
    assert "12 cases" in c2["method"]
