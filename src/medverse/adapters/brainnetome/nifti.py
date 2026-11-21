"""NIfTI-1 reading.  Uses nibabel when installed; otherwise a minimal built-in reader (single-file .nii/.nii.gz)
that preserves the sform/qform affine exactly.  `save_nifti` exists for tests and tooling."""
from __future__ import annotations

import gzip
import struct

import numpy as np

_DT = {2: "u1", 4: "<i2", 8: "<i4", 16: "<f4", 64: "<f8", 256: "i1", 512: "<u2", 768: "<u4"}


def _quat_affine(b, c, d, off, pixdim):
    a = np.sqrt(max(0.0, 1.0 - (b * b + c * c + d * d)))
    R = np.array([[a*a + b*b - c*c - d*d, 2*(b*c - a*d), 2*(b*d + a*c)],
                  [2*(b*c + a*d), a*a + c*c - b*b - d*d, 2*(c*d - a*b)],
                  [2*(b*d - a*c), 2*(c*d + a*b), a*a + d*d - b*b - c*c]])
    qfac = -1.0 if pixdim[0] < 0 else 1.0
    zooms = np.array([pixdim[1], pixdim[2], pixdim[3] * qfac])
    A = np.eye(4)
    A[:3, :3] = R * zooms
    A[:3, 3] = off
    return A


def _load_builtin(path):
    op = gzip.open if str(path).lower().endswith(".gz") else open
    with op(path, "rb") as fh:
        raw = fh.read()
    if struct.unpack("<i", raw[:4])[0] != 348:
        raise ValueError("only little-endian NIfTI-1 is supported by the built-in reader (install nibabel)")
    dim = struct.unpack("<8h", raw[40:56])
    dtype = struct.unpack("<h", raw[70:72])[0]
    pixdim = struct.unpack("<8f", raw[76:108])
    vox_offset = int(struct.unpack("<f", raw[108:112])[0])
    slope, inter = struct.unpack("<2f", raw[112:120])
    qcode, scode = struct.unpack("<2h", raw[252:256])
    qb, qc, qd, qx, qy, qz = struct.unpack("<6f", raw[256:280])
    srow = np.array(struct.unpack("<12f", raw[280:328])).reshape(3, 4)
    if dtype not in _DT:
        raise ValueError(f"unsupported NIfTI datatype {dtype}")
    shape = tuple(dim[1:1 + dim[0]])
    n = int(np.prod(shape))
    data = np.frombuffer(raw, dtype=np.dtype(_DT[dtype]), count=n, offset=vox_offset).reshape(shape, order="F")
    if scode > 0:
        A = np.eye(4)
        A[:3, :] = srow
    elif qcode > 0:
        A = _quat_affine(qb, qc, qd, (qx, qy, qz), pixdim)
    else:
        A = np.diag([pixdim[1], pixdim[2], pixdim[3], 1.0])
    if slope not in (0.0, 1.0) or inter != 0.0:
        data = data * (slope or 1.0) + inter
    return np.asarray(data), A


def load_nifti(path):
    """-> (data ndarray, affine 4x4)."""
    try:
        import nibabel as nib
    except ImportError:
        return _load_builtin(path)
    img = nib.load(str(path))
    return np.asarray(img.dataobj), np.asarray(img.affine, dtype=float)


def save_nifti(path, data, affine):
    """Minimal NIfTI-1 writer (sform only) for tests."""
    data = np.asarray(data)
    dt = {np.dtype("uint8"): 2, np.dtype("int16"): 4, np.dtype("int32"): 8, np.dtype("float32"): 16}[data.dtype]
    h = bytearray(352)
    struct.pack_into("<i", h, 0, 348)
    struct.pack_into("<8h", h, 40, data.ndim, *data.shape, *([1] * (7 - data.ndim)))
    struct.pack_into("<h", h, 70, dt)
    struct.pack_into("<h", h, 72, data.dtype.itemsize * 8)
    zooms = np.linalg.norm(np.asarray(affine)[:3, :3], axis=0)
    struct.pack_into("<8f", h, 76, 1.0, *zooms, 0, 0, 0, 0)
    struct.pack_into("<f", h, 108, 352.0)
    struct.pack_into("<2f", h, 112, 1.0, 0.0)
    struct.pack_into("<2h", h, 252, 0, 1)
    struct.pack_into("<12f", h, 280, *np.asarray(affine, dtype=float)[:3, :].ravel())
    h[344:348] = b"n+1\0"
    payload = bytes(h) + np.asfortranarray(data).tobytes(order="F")
    op = gzip.open if str(path).lower().endswith(".gz") else open
    with op(path, "wb") as fh:
        fh.write(payload)
