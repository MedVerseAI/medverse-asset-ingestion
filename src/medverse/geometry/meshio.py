"""Mesh file I/O (OBJ read, binary PLY read/write).  Pure numpy -- usable inside and outside Blender."""
from __future__ import annotations

import numpy as np

_PLY_TYPES = {"char": "i1", "uchar": "u1", "int8": "i1", "uint8": "u1", "short": "<i2", "ushort": "<u2",
              "int16": "<i2", "uint16": "<u2", "int": "<i4", "uint": "<u4", "int32": "<i4", "uint32": "<u4",
              "float": "<f4", "float32": "<f4", "double": "<f8", "float64": "<f8"}


def read_ply_binary(path):
    """Read a binary_little_endian triangle PLY.
    Returns verts (N,3) float64, faces (M,3) int64, rgb (N,3) uint8 or None."""
    with open(path, "rb") as fh:
        data = fh.read()
    end = data.find(b"end_header")
    if end < 0:
        raise ValueError("no PLY header")
    nl = data.find(b"\n", end)
    header = data[:nl].decode("ascii", errors="replace").splitlines()
    body = nl + 1
    if not any(l.strip() == "format binary_little_endian 1.0" for l in header):
        raise ValueError("only binary_little_endian PLY is supported")
    elements, cur = [], None
    for l in header:
        p = l.split()
        if not p:
            continue
        if p[0] == "element":
            cur = {"name": p[1], "count": int(p[2]), "props": []}
            elements.append(cur)
        elif p[0] == "property" and cur is not None:
            if p[1] == "list":
                cur["props"].append(("list", p[4], p[2], p[3]))
            else:
                cur["props"].append(("scalar", p[2], p[1]))
    verts = faces = rgb = None
    off = body
    for el in elements:
        if el["name"] == "vertex":
            dt = np.dtype([(pr[1], _PLY_TYPES[pr[2]]) for pr in el["props"] if pr[0] == "scalar"])
            arr = np.frombuffer(data, dtype=dt, count=el["count"], offset=off)
            off += dt.itemsize * el["count"]
            verts = np.stack([arr["x"], arr["y"], arr["z"]], 1).astype(np.float64)
            if all(k in arr.dtype.names for k in ("red", "green", "blue")):
                rgb = np.stack([arr["red"], arr["green"], arr["blue"]], 1).astype(np.uint8)
        elif el["name"] == "face":
            lp = el["props"][0]
            if lp[0] != "list":
                raise ValueError("unexpected face property")
            dt = np.dtype([("n", _PLY_TYPES[lp[2]]), ("idx", _PLY_TYPES[lp[3]], (3,))])
            arr = np.frombuffer(data, dtype=dt, count=el["count"], offset=off)
            off += dt.itemsize * el["count"]
            if len(arr) and not (arr["n"] == 3).all():
                raise ValueError("non-triangular faces are not supported")
            faces = arr["idx"].astype(np.int64)
        else:
            raise ValueError(f"unsupported PLY element '{el['name']}'")
    if verts is None or faces is None:
        raise ValueError("PLY has no vertex/face element")
    return verts, faces, rgb


def write_ply_binary(path, verts, faces, rgb=None):
    """Write a triangle mesh as binary_little_endian PLY (optional single RGB colour for all vertices)."""
    if rgb is not None:
        return _write_ply_rgb(path, verts, faces, rgb)
    v = np.empty(len(verts), dtype=[("x", "<f4"), ("y", "<f4"), ("z", "<f4")])
    v["x"], v["y"], v["z"] = verts[:, 0], verts[:, 1], verts[:, 2]
    f = np.empty(len(faces), dtype=[("n", "u1"), ("idx", "<i4", (3,))])
    f["n"] = 3
    f["idx"] = faces
    header = ("ply\nformat binary_little_endian 1.0\n"
              f"element vertex {len(v)}\n"
              "property float x\nproperty float y\nproperty float z\n"
              f"element face {len(f)}\n"
              "property list uchar int vertex_indices\nend_header\n")
    with open(path, "wb") as fh:
        fh.write(header.encode("ascii"))
        fh.write(v.tobytes())
        fh.write(f.tobytes())


def read_obj(path):
    """Read an OBJ (v / f only); n-gons are fan-triangulated."""
    verts, faces = [], []
    with open(path, "r", errors="replace") as fh:
        for line in fh:
            if line.startswith("v "):
                p = line.split()
                verts.append((float(p[1]), float(p[2]), float(p[3])))
            elif line.startswith("f "):
                idx = []
                for tok in line.split()[1:]:
                    i = int(tok.split("/")[0])
                    idx.append(i - 1 if i > 0 else len(verts) + i)
                for k in range(1, len(idx) - 1):
                    faces.append((idx[0], idx[k], idx[k + 1]))
    v = np.asarray(verts, dtype=np.float64).reshape(-1, 3)
    f = np.asarray(faces, dtype=np.int64).reshape(-1, 3)
    if len(f) and (f.min() < 0 or f.max() >= len(v)):
        raise ValueError(f"face index out of range in {path}")
    return v, f


def _write_ply_rgb(path, verts, faces, rgb):
    v = np.empty(len(verts), dtype=[("x", "<f4"), ("y", "<f4"), ("z", "<f4"), ("r", "u1"), ("g", "u1"), ("b", "u1")])
    v["x"], v["y"], v["z"] = verts[:, 0], verts[:, 1], verts[:, 2]
    v["r"], v["g"], v["b"] = rgb
    f = np.empty(len(faces), dtype=[("n", "u1"), ("idx", "<i4", (3,))])
    f["n"] = 3
    f["idx"] = faces
    header = ("ply\nformat binary_little_endian 1.0\n" f"element vertex {len(v)}\n"
              "property float x\nproperty float y\nproperty float z\n"
              "property uchar red\nproperty uchar green\nproperty uchar blue\n"
              f"element face {len(f)}\n" "property list uchar int vertex_indices\nend_header\n")
    with open(path, "wb") as fh:
        fh.write(header.encode("ascii"))
        fh.write(v.tobytes())
        fh.write(f.tobytes())
