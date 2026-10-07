"""Entrypoint of the reference field package: the temperature rise over a heated plate.

A Contract fixture, not an engineering model. The prediction is a closed-form
expression with one fitted amplitude, so every number the package reports can
be recomputed from the two files it pins; its model card says how the
amplitude and the band were fitted and what the model must not be used for.

How it is called (section 12 of docs/spec/CONTRACT-v1.md; the manifest's
invocation.protocol is stdio_json). One JSON request arrives on stdin and is
read to end of file; the answer is one JSON frame per row on stdout, one per
line, and the process exits with code 0 whenever it gave an answer:

    {"run_id": "r1", "mode": "single",
     "inputs": {"power_W": 20.0, "length_m": 0.1, "width_m": 0.1}}
 -> {"run_id": "r1", "status": "ok", "outputs": {
        "temperature_rise": {"kind": "artifact", "path": "temperature_rise.vtp", ...},
        "temperature_rise_lower": {...}, "temperature_rise_upper": {...},
        "peak_rise": 9.37..., "peak_rise_lower": ..., "peak_rise_upper": ...}}

The field and the two edges of its band are written as VTK XML PolyData,
three files in the current directory, which is the working directory the caller
made for the request. Each is answered with a reference that carries the
file's sha256 and length, both read back from disk once the file is closed.
The peak and its band are plain numbers in the frame. With "mode": "batch",
"inputs" is a list; every row is answered with a frame of its own, in order,
and writes files whose names carry the row's index, so no two rows share a
file. A request it will not answer -- an input that is missing, not a number or
outside its declared range -- gets an error frame, and the exit code is still 0. Only
a package that cannot read its own weights, or a host that cannot write the
files, ends with exit 1.

Run it by hand:  echo {"inputs": {...}} | python predict.py
"""

import hashlib
import json
import math
import sys
from pathlib import Path

WEIGHTS_PATH = Path(__file__).resolve().parent / "model_weights.json"
INPUTS = ("power_W", "length_m", "width_m")
FIELD = "temperature_rise"
PEAK = "peak_rise"
UNITS = "K"
MEDIA_TYPE = "application/vnd.vtk.vtp+xml"


class Declined(Exception):
    """Raised for a request the model will not answer: the row gets an error frame, and the exit code stays 0."""

    def __init__(self, code, message, field=None):
        Exception.__init__(self, message)
        self.code, self.message, self.field = code, message, field


def load_weights():
    return json.loads(WEIGHTS_PATH.read_text(encoding="utf-8"))


def read_inputs(inputs, weights):
    """The three inputs as floats, in INPUTS order; Declined for anything the model will not take."""
    if not isinstance(inputs, dict):
        raise Declined("BAD_REQUEST", "inputs must be a JSON object")
    values = []
    for name in INPUTS:
        raw = inputs.get(name)
        if raw is None:
            raise Declined("MISSING_INPUT", "required input %r is missing" % name, name)
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise Declined("BAD_REQUEST", "input %r is %r, which is not a number" % (name, raw), name)
        try:
            value = float(raw)
        except OverflowError:
            value = math.inf
        low, high = weights["input_ranges"][name]
        if not (math.isfinite(value) and low <= value <= high):
            raise Declined("OUT_OF_RANGE", "%s = %r lies outside its declared range [%r, %r]"
                           % (name, raw, low, high), name)
        values.append(value)
    return values


def node_shape(n):
    """s(i) = u (1 - u) at u = i / (n - 1): the profile the field follows along each side."""
    steps = n - 1
    return [(i / steps) * (1.0 - i / steps) for i in range(n)]


def field_values(power_W, length_m, width_m, weights):
    """The predicted rise at every node, in K: y index outer, x index inner (row-major)."""
    n = weights["nodes_per_side"]
    k_t = weights["conductivity_W_mK"] * weights["thickness_m"]
    scale = (weights["amplitude"] * power_W * length_m * width_m
             / (k_t * (length_m * length_m + width_m * width_m)))
    s = node_shape(n)
    return [scale * (s[i] * s[j]) for j in range(n) for i in range(n)]


def vtp_text(array_name, values, length_m, width_m, n):
    """A VTK XML PolyData document: the n x n nodes, their quads, and one point array."""
    steps = n - 1
    points = ["%r %r 0" % ((i / steps) * length_m, (j / steps) * width_m) for j in range(n) for i in range(n)]
    quads = []
    for j in range(steps):
        for i in range(steps):
            a = j * n + i
            quads.append("%d %d %d %d" % (a, a + 1, a + n + 1, a + n))
    offsets = " ".join(str(4 * (q + 1)) for q in range(len(quads)))
    lines = [
        '<?xml version="1.0"?>',
        '<VTKFile type="PolyData" version="0.1" byte_order="LittleEndian">',
        "  <PolyData>",
        '    <Piece NumberOfPoints="%d" NumberOfVerts="0" NumberOfLines="0" NumberOfStrips="0" '
        'NumberOfPolys="%d">' % (len(values), len(quads)),
        '      <PointData Scalars="%s">' % array_name,
        '        <DataArray type="Float64" Name="%s" NumberOfComponents="1" format="ascii">' % array_name,
        "          " + " ".join(repr(v) for v in values),
        "        </DataArray>",
        "      </PointData>",
        "      <Points>",
        '        <DataArray type="Float64" Name="Points" NumberOfComponents="3" format="ascii">',
        "          " + " ".join(points),
        "        </DataArray>",
        "      </Points>",
        "      <Polys>",
        '        <DataArray type="Int32" Name="connectivity" format="ascii">',
        "          " + " ".join(quads),
        "        </DataArray>",
        '        <DataArray type="Int32" Name="offsets" format="ascii">',
        "          " + offsets,
        "        </DataArray>",
        "      </Polys>",
        "    </Piece>",
        "  </PolyData>",
        "</VTKFile>",
    ]
    return "\n".join(lines) + "\n"


def write_reference(path, array_name, values, length_m, width_m, n):
    """Write one payload, then describe the file on disk: its digest and length come from re-reading it."""
    path.write_bytes(vtp_text(array_name, values, length_m, width_m, n).encode("utf-8"))
    written = path.read_bytes()
    return {"kind": "artifact", "path": path.name, "media_type": MEDIA_TYPE,
            "sha256": hashlib.sha256(written).hexdigest(), "bytes": len(written),
            "field": {"name": array_name, "units": UNITS, "range": [min(values), max(values)],
                      "n_nodes": len(values)}}


def answer_row(run_id, inputs, weights, suffix):
    """One row's frame. Declined becomes an error frame; OSError is left to the caller."""
    try:
        power_W, length_m, width_m = read_inputs(inputs, weights)
    except Declined as exc:
        error = {"code": exc.code, "message": exc.message}
        if exc.field is not None:
            error["field"] = exc.field
        return {"run_id": run_id, "status": "error", "error": error}
    n = weights["nodes_per_side"]
    values = field_values(power_W, length_m, width_m, weights)
    peak = max(values)
    field_half = weights["field_half_width"] * peak
    peak_half = weights["peak_half_width"] * peak
    outputs = {}
    for key, shifted in ((FIELD, values),
                         (FIELD + "_lower", [v - field_half for v in values]),
                         (FIELD + "_upper", [v + field_half for v in values])):
        outputs[key] = write_reference(Path(key + suffix + ".vtp"), key, shifted, length_m, width_m, n)
    outputs[PEAK] = peak
    outputs[PEAK + "_lower"] = peak - peak_half
    outputs[PEAK + "_upper"] = peak + peak_half
    return {"run_id": run_id, "status": "ok", "outputs": outputs}


def write_frame(frame):
    sys.stdout.write(json.dumps(frame) + "\n")


def internal_error(run_id, exc):
    write_frame({"run_id": run_id, "status": "error",
                 "error": {"code": "INTERNAL_ERROR", "message": "%s: %s" % (type(exc).__name__, exc)}})
    return 1


def main():
    try:
        request = json.loads(sys.stdin.read())
    except ValueError as exc:
        write_frame({"run_id": None, "status": "error",
                     "error": {"code": "BAD_REQUEST", "message": "stdin does not hold JSON: %s" % exc}})
        return 0
    if not isinstance(request, dict):
        write_frame({"run_id": None, "status": "error",
                     "error": {"code": "BAD_REQUEST", "message": "the request must be a JSON object"}})
        return 0
    run_id, inputs = request.get("run_id"), request.get("inputs")
    mode = request.get("mode") or ("batch" if isinstance(inputs, list) else "single")
    if mode not in ("single", "batch") or (mode == "batch") != isinstance(inputs, list):
        write_frame({"run_id": run_id, "status": "error",
                     "error": {"code": "BAD_REQUEST",
                               "message": "mode %r with inputs of type %s: single takes an object, batch a list"
                                          % (mode, type(inputs).__name__)}})
        return 0
    try:
        weights = load_weights()
    except (OSError, ValueError) as exc:
        return internal_error(run_id, exc)
    rows = inputs if mode == "batch" else [inputs]
    for index, row in enumerate(rows):
        suffix = "-%d" % index if mode == "batch" else ""
        try:
            write_frame(answer_row(run_id, row, weights, suffix))
        except OSError as exc:
            return internal_error(run_id, exc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
