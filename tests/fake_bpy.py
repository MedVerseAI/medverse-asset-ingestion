"""
Minimal in-memory stand-in for `bpy` / `mathutils`, just enough to run step 03 outside Blender.
Used only by tests (tests/test_build_modes.py). It records what the pipeline builds.
"""
import sys
import types
from unittest import mock

import numpy as np


class _Link(list):
    def link(self, item):
        self.append(item)


class _Coll:
    def __init__(self, name):
        self.name = name
        self.objects = _Link()
        self.children = _Link()


class _Verts:
    def __init__(self, arr):
        self._a = arr

    def __len__(self):
        return len(self._a)

    def foreach_get(self, attr, buf):
        buf[:] = self._a.astype(np.float32).ravel()


class _Polys(list):
    def foreach_set(self, *a):
        pass


class _Mesh:
    users = 1

    def __init__(self, name):
        self.name = name
        self.materials = []
        self.vertices = _Verts(np.zeros((0, 3)))
        self.polygons = _Polys()

    def from_pydata(self, verts, edges, faces):
        self.vertices = _Verts(np.asarray(verts, float).reshape(-1, 3))
        self.polygons = _Polys(faces)

    def update(self):
        pass

    def validate(self):
        pass


class _Obj:
    def __init__(self, name, data=None):
        self.name, self.data, self.parent = name, data, None
        self.location = (0.0, 0.0, 0.0)
        self.hide_viewport = False
        self._props = {}
        self.type = "MESH" if data is not None else "EMPTY"

    def __setitem__(self, k, v):
        self._props[k] = v

    def get(self, k, default=None):
        return self._props.get(k, default)

    def select_set(self, flag):
        pass

    @property
    def matrix_world(self):
        m = np.eye(4)
        m[:3, 3] = self.location
        return m

    @property
    def bound_box(self):
        a = self.data.vertices._a
        lo, hi = a.min(0), a.max(0)
        return [[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])]


class _Manager(list):
    def __init__(self, factory, state=None):
        super().__init__()
        self._factory, self._state = factory, state

    def new(self, name, *args):
        item = self._factory(name, *args)
        self.append(item)
        return item

    def get(self, name):
        return next((i for i in self if i.name == name), None)

    def remove(self, item, **kw):
        if item in self:
            super().remove(item)
        if self._state is not None and kw.get("do_unlink", False):
            for c in self._state["collections"]:
                if item in c.objects:
                    c.objects.remove(item)


def install():
    """Insert fake `bpy` and `mathutils` modules into sys.modules; returns a state dict."""
    state = {"saved": None}
    colls = _Manager(_Coll)
    state["collections"] = colls
    objs = _Manager(_Obj, state)
    scene = types.SimpleNamespace(collection=_Coll("Scene Collection"),
                                  unit_settings=types.SimpleNamespace())

    bpy = types.ModuleType("bpy")
    bpy.data = types.SimpleNamespace(collections=colls, objects=objs, meshes=_Manager(_Mesh),
                                     materials=mock.MagicMock(), texts=mock.MagicMock(),
                                     screens=mock.MagicMock(), orphans_purge=mock.MagicMock())
    bpy.context = types.SimpleNamespace(scene=scene, view_layer=mock.MagicMock())
    bpy.types = types.SimpleNamespace(Mesh=_Mesh)

    def save_as_mainfile(filepath, copy=False):
        state["saved"] = filepath
        open(filepath, "wb").close()
    bpy.ops = types.SimpleNamespace(wm=types.SimpleNamespace(save_as_mainfile=save_as_mainfile),
                                    outliner=mock.MagicMock())
    mathutils = types.ModuleType("mathutils")
    mathutils.Euler = mock.MagicMock()
    sys.modules["bpy"], sys.modules["mathutils"] = bpy, mathutils
    state["bpy"] = bpy
    return state
