"""Загрузка поверхности обивки в мировых координатах изделия."""
from functools import lru_cache
from pathlib import Path

import numpy as np

import params as P
from .geom import Surface, catmull_clark, triangulate

DATA = Path(__file__).resolve().parents[1] / "data" / "spin_cage.npz"


def to_world(V, ref):
    """Координаты модели → мировые. ref — сетка, по которой берутся ось и низ
    (всегда подразделённая, чтобы уровни совпадали)."""
    zmin = ref[:, 2].min()
    band = (ref[:, 2] > zmin + 150) & (ref[:, 2] < zmin + 400)
    xc = (ref[band, 0].min() + ref[band, 0].max()) / 2
    W = np.empty_like(V)
    W[:, 0] = (V[:, 0] - xc) * P.MODEL_XY_SCALE
    W[:, 1] = (V[:, 1] - P.MODEL_AXIS_Y) * P.MODEL_XY_SCALE
    W[:, 2] = V[:, 2] - zmin + P.Z_BODY_BOTTOM
    return W


def mesh_level(n):
    V, F = load_cage()
    for _ in range(n):
        V, F = catmull_clark(V, F)
    return V, F


def viewer_mesh():
    """Сетка 1-го уровня сглаживания в мировых координатах (для 3D-просмотра)."""
    V1, Q1 = mesh_level(1)
    # опорная сетка — финальная поверхность: восстанавливаем преобразование по ней
    V2, _ = mesh_level(P.MODEL_SUBDIV)
    return to_world(V1, ref=V2), np.asarray(Q1)


def load_cage():
    d = np.load(DATA)
    V = d["V"].astype(float)
    F, off = [], 0
    for c in d["counts"]:
        F.append(list(d["faces"][off:off + c]))
        off += c
    return V, F


CACHE = Path(__file__).resolve().parents[1] / ".cache" / "surface.npz"


@lru_cache(maxsize=1)
def surface():
    key = np.array([P.MODEL_SUBDIV, P.MODEL_XY_SCALE, P.MODEL_AXIS_Y, P.Z_BODY_BOTTOM])
    if CACHE.exists() and CACHE.stat().st_mtime > DATA.stat().st_mtime:
        c = np.load(CACHE)
        if np.allclose(c["key"], key):
            return Surface(c["V"], c["T"])
    V, F = mesh_level(P.MODEL_SUBDIV)
    W = to_world(V, ref=V)
    T = triangulate(F)
    CACHE.parent.mkdir(exist_ok=True)
    np.savez(CACHE, V=W, T=T, key=key)
    return Surface(W, T)
