"""A stdio_json entrypoint in the shape a grid field producer documents for the packages it emits.

A test fixture, standard library only. It answers each row with a temperature-rise
field on a 4 x 4 grid of nodes, written as VTK XML PolyData into its working
directory and returned by reference, with its lower and upper band the same way
(named by `lower_field` / `upper_field`, as such a producer names them), and three
in-band diagnostics beyond the declared outputs. In `batch` mode each row writes
its own files. A request it will not take gets an in-band error frame and exit 0;
an internal failure exits 1.

`DEFECT` plants one protocol defect for the negative tests; "none" is the
conformant entrypoint. The field is a closed-form toy, not a model.
"""

import hashlib
import json
import sys
from pathlib import Path

DEFECT = "none"
MEDIA_TYPE = "application/vnd.vtk.vtp+xml"
NX = NY = 4
RANGES = {"source_P_W": (1.0, 25.0), "h_W_m2K": (10.0, 300.0)}
HALF_WIDTH_K = 0.5


class Declined(Exception):
    def __init__(self, code, message, field=None):
        Exception.__init__(self, message)
        self.code, self.message, self.field = code, message, field


def nodes():
    return [(0.01 * i, 0.01 * j) for j in range(NY) for i in range(NX)]


def field_values(inputs):
    if not isinstance(inputs, dict):
        raise Declined("BAD_REQUEST", "inputs must be a JSON object")
    values = {}
    for name, (low, high) in RANGES.items():
        if inputs.get(name) is None:
            raise Declined("MISSING_INPUT", "required input %r is missing" % name, name)
        value = inputs[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise Declined("BAD_REQUEST", "%s must be a number" % name, name)
        if not low <= value <= high:
            raise Declined("OUT_OF_RANGE", "%s=%r is outside [%g, %g]" % (name, value, low, high), name)
        values[name] = float(value)
    scale = values["source_P_W"] / values["h_W_m2K"] * 100.0
    return [scale * (1.0 + x * 10.0) * (1.0 + y * 10.0) for x, y in nodes()]


def write_vtp(path, name, values):
    points = " ".join("%r %r 0" % xy for xy in nodes())
    quads = []
    for j in range(NY - 1):
        for i in range(NX - 1):
            a = j * NX + i
            quads.append("%d %d %d %d" % (a, a + 1, a + NX + 1, a + NX))
    offsets = " ".join(str(4 * (k + 1)) for k in range(len(quads)))
    lines = [
        '<?xml version="1.0"?>',
        '<VTKFile type="PolyData" version="1.0" byte_order="LittleEndian">',
        "  <PolyData>",
        '    <Piece NumberOfPoints="%d" NumberOfVerts="0" NumberOfLines="0" NumberOfStrips="0" NumberOfPolys="%d">'
        % (NX * NY, len(quads)),
        '      <Points><DataArray type="Float64" NumberOfComponents="3" format="ascii">%s</DataArray></Points>'
        % points,
        '      <Polys><DataArray type="Int32" Name="connectivity" format="ascii">%s</DataArray>' % " ".join(quads),
        '      <DataArray type="Int32" Name="offsets" format="ascii">%s</DataArray></Polys>' % offsets,
        '      <PointData Scalars="%s"><DataArray type="Float64" Name="%s" format="ascii">%s</DataArray></PointData>'
        % (name, name, " ".join(repr(v) for v in values)),
        "    </Piece>",
        "  </PolyData>",
        "</VTKFile>",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def reference(path, name, values):
    blob = path.read_bytes()
    ref = {"kind": "artifact", "path": path.name, "media_type": MEDIA_TYPE,
           "sha256": hashlib.sha256(blob).hexdigest(), "bytes": len(blob),
           "field": {"name": name, "units": "K", "range": [min(values), max(values)], "n_nodes": NX * NY}}
    if DEFECT == "wrong_digest":
        ref["sha256"] = hashlib.sha256(blob + b" ").hexdigest()
    elif DEFECT == "wrong_size":
        ref["bytes"] = len(blob) + 1
    elif DEFECT == "missing_file":
        path.unlink()
    elif DEFECT == "outside_path":
        ref["path"] = "../" + path.name
    elif DEFECT == "wrong_media":
        ref["media_type"] = "text/plain"
    elif DEFECT == "wrong_units":
        ref["field"]["units"] = "degC"
    elif DEFECT == "no_field_descriptor":
        del ref["field"]
    return ref


def run_row(run_id, inputs, out_dir, suffix):
    try:
        dT = field_values(inputs)
    except Declined as exc:
        error = {"code": exc.code, "message": exc.message}
        if exc.field is not None:
            error["field"] = exc.field
        return {"run_id": run_id, "status": "error", "error": error}
    outputs = {}
    for name, values in (("dT", dT), ("dT_lower", [v - HALF_WIDTH_K for v in dT]),
                         ("dT_upper", [v + HALF_WIDTH_K for v in dT])):
        target = out_dir / ("%s%s.vtp" % (name, suffix))
        write_vtp(target, name, values)
        outputs[name] = reference(target, name, values)
    outputs.update({"dT_max_K": max(dT), "units": "K", "grid": [NY, NX]})
    if DEFECT == "inline_field":
        outputs["dT"] = dT
    elif DEFECT == "missing_output":
        del outputs["dT"]
    frame = {"run_id": run_id, "status": "ok", "outputs": outputs}
    if DEFECT == "no_status":
        del frame["status"]
    elif DEFECT == "wrong_run_id":
        frame["run_id"] = "another-run"
    return frame


def write_frame(frame):
    sys.stdout.write(json.dumps(frame) + "\n")


def main():
    try:
        request = json.loads(sys.stdin.read())
    except ValueError as exc:
        write_frame({"run_id": None, "status": "error",
                     "error": {"code": "BAD_REQUEST", "message": "stdin is not valid JSON (%s)" % exc}})
        return 0
    if not isinstance(request, dict):
        write_frame({"run_id": None, "status": "error",
                     "error": {"code": "BAD_REQUEST", "message": "the request must be a JSON object"}})
        return 0
    run_id, inputs = request.get("run_id"), request.get("inputs")
    mode = request.get("mode") or ("batch" if isinstance(inputs, list) else "single")
    if mode not in ("single", "batch") or (mode == "batch") != isinstance(inputs, list):
        write_frame({"run_id": run_id, "status": "error",
                     "error": {"code": "BAD_REQUEST", "message": "single takes an object, batch an array"}})
        return 0
    if DEFECT == "banner":
        sys.stdout.write("model loaded\n")
    out_dir = Path.cwd()
    rows = inputs if mode == "batch" else [inputs]
    for index, row in enumerate(rows):
        write_frame(run_row(run_id, row, out_dir, "" if mode == "single" else "_row%d" % index))
    if DEFECT == "extra_frame":
        write_frame({"run_id": run_id, "status": "ok", "outputs": {}})
    return 1 if DEFECT == "nonzero_exit" else 0


if __name__ == "__main__":
    sys.exit(main())
