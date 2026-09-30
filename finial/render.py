"""Предпросмотр: трассировка лучей по неявной поверхности (только numpy).

Рисует наконечник на отрезке штанги Ø40 (штанга условная — 10 валиков,
как на фото), чтобы оценить пропорции.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from PIL import Image

from geom import Params, build_profile, end_x, radius_table, reed_d, reed_dv, reed_v

WOOD = np.array([0.80, 0.64, 0.45])
ROD_REEDS = 10
ROD_LEN = 150.0


class Body:
    """Тело вращения вокруг X: r(x, φ) = R0(x) − d(x)·v(φ);
    cap — торец x ≤ X(ρ, θ) при ρ < rho_cap (таблица на полярной сетке)."""

    def __init__(self, x, R0, d, v, dv, cap=None):
        self.cap = cap
        self.x0, self.x1 = x[0], x[-1]
        self.h = x[1] - x[0]
        self.R0, self.d = R0, d
        self.dR0 = np.gradient(R0, self.h)
        self.dd = np.gradient(d, self.h)
        self.v, self.dv = v, dv
        self.rmax = R0.max()

    def _i(self, x, arr):
        return np.interp(x, np.linspace(self.x0, self.x1, len(arr)), arr, left=0.0, right=0.0)

    def field(self, p):
        """> 0 внутри."""
        x, y, z = p[..., 0], p[..., 1], p[..., 2]
        rho = np.hypot(y, z)
        phi = np.arctan2(y, z)
        F = self._i(x, self.R0) - self._i(x, self.d) * self.v(phi) - rho
        if self.cap is not None:
            rc, dr, dth, tab = self.cap
            m = rho < rc - dr
            if m.any():
                a = rho[m] / dr
                b = (phi[m] % (2 * np.pi)) / dth
                i0, j0 = np.floor(a).astype(int), np.floor(b).astype(int)
                fa, fb = a - i0, b - j0
                nj = tab.shape[1]
                j1 = (j0 + 1) % nj
                j0 %= nj
                X = ((1 - fa) * ((1 - fb) * tab[i0, j0] + fb * tab[i0, j1])
                     + fa * ((1 - fb) * tab[i0 + 1, j0] + fb * tab[i0 + 1, j1]))
                F[m] = np.minimum(F[m], X - x[m])
        return F

    def normal(self, p, h=0.01):
        g = np.zeros_like(p)
        for k in range(3):
            e = np.zeros(3)
            e[k] = h
            g[:, k] = self.field(p - e) - self.field(p + e)
        return g / np.maximum(np.linalg.norm(g, axis=1, keepdims=True), 1e-12)


def bodies(P: Params, with_rod=True):
    prof = build_profile(P)
    x = np.arange(-P.tenon_l, P.length + 1e-9, 0.01)
    R0 = radius_table(prof, x)
    d = reed_d(P, prof, x, R0)
    cap = None
    if P.rosette:
        dr, dth = 0.02, np.radians(0.1)
        rc = P.rosette_r + 0.5
        rr = np.arange(0, rc + 2 * dr, dr)
        tt = np.arange(0, 2 * np.pi, dth)
        RR, TT = np.meshgrid(rr, tt, indexing="ij")
        cap = (rc, dr, dth, end_x(P, prof, RR, TT))
    out = [Body(x, R0, d, lambda f: reed_v(P, f), lambda f: reed_dv(P, f), cap)]
    if with_rod:
        xr = np.arange(-ROD_LEN, 0.0 + 1e-9, 0.05)
        n = ROD_REEDS
        v = lambda f: (0.5 * (1 + np.cos(n * (f - math.pi / n)))) ** 4
        dv = lambda f: 4 * (0.5 * (1 + np.cos(n * (f - math.pi / n)))) ** 3 * (-0.5 * n) * np.sin(n * (f - math.pi / n))
        out.append(Body(xr, np.full_like(xr, P.rod_d / 2), np.full_like(xr, 1.6), v, dv))
    return out


def trace(objs, eye_dir, width_mm, W, H, center, ss=2, step=0.4):
    f = -np.asarray(eye_dir, float)
    f /= np.linalg.norm(f)
    r = np.cross(f, [0, 0, 1.0])
    r /= np.linalg.norm(r)
    u = np.cross(r, f)
    Ws, Hs = W * ss, H * ss
    s = width_mm / Ws
    jj, ii = np.meshgrid(np.arange(Ws) + 0.5, np.arange(Hs) + 0.5)
    O = (np.asarray(center, float) + ((jj - Ws / 2) * s)[..., None] * r
         - ((ii - Hs / 2) * s)[..., None] * u - 400 * f).reshape(-1, 3)
    n_rays = len(O)
    hit_t = np.full(n_rays, np.inf)
    hit_obj = np.full(n_rays, -1)
    for k, ob in enumerate(objs):
        # пересечение с ограничивающим цилиндром
        R = ob.rmax + 0.5
        a = f[1] ** 2 + f[2] ** 2
        b = 2 * (O[:, 1] * f[1] + O[:, 2] * f[2])
        c = O[:, 1] ** 2 + O[:, 2] ** 2 - R * R
        if a < 1e-12:                       # луч вдоль оси тела
            ok = c < 0
            t0, t1 = np.full(n_rays, -1e9), np.full(n_rays, 1e9)
        else:
            disc = b * b - 4 * a * c
            ok = disc > 0
            sq = np.sqrt(np.where(ok, disc, 0))
            t0, t1 = (-b - sq) / (2 * a), (-b + sq) / (2 * a)
        if abs(f[0]) > 1e-9:
            tx0, tx1 = (ob.x0 - 0.5 - O[:, 0]) / f[0], (ob.x1 + 0.5 - O[:, 0]) / f[0]
            t0 = np.maximum(t0, np.minimum(tx0, tx1))
            t1 = np.minimum(t1, np.maximum(tx0, tx1))
        ok &= t1 > t0
        idx = np.nonzero(ok)[0]
        for chunk in np.array_split(idx, max(1, len(idx) // 20000)):
            if len(chunk) == 0:
                continue
            ta, tb = t0[chunk], t1[chunk]
            n = int(math.ceil((tb - ta).max() / step)) + 1
            ts = ta[:, None] + np.arange(n)[None, :] * step
            P_ = O[chunk, None, :] + ts[..., None] * f
            F = ob.field(P_)
            F[ts > tb[:, None]] = -1
            inside = F > 0
            has = inside.any(axis=1)
            first = inside.argmax(axis=1)
            sel = np.nonzero(has & (first > 0))[0]
            lo = ts[sel, first[sel] - 1]
            hi = ts[sel, first[sel]]
            oo = O[chunk[sel]]
            for _ in range(14):
                mid = 0.5 * (lo + hi)
                ins = ob.field(oo + mid[:, None] * f) > 0
                hi = np.where(ins, mid, hi)
                lo = np.where(ins, lo, mid)
            rid = chunk[sel]
            better = hi < hit_t[rid]
            hit_t[rid[better]] = hi[better]
            hit_obj[rid[better]] = k
    img = background(Hs, Ws).reshape(-1, 3)
    for k, ob in enumerate(objs):
        m = np.nonzero(hit_obj == k)[0]
        if len(m) == 0:
            continue
        p = O[m] + hit_t[m, None] * f
        img[m] = shade(p, ob.normal(p), -f)
    img = img.reshape(Hs, Ws, 3)
    img = img.reshape(H, ss, W, ss, 3).mean(axis=(1, 3))
    return Image.fromarray((np.clip(img, 0, 1) ** (1 / 1.1) * 255).astype(np.uint8))


def background(H, W):
    g = np.linspace(0.97, 0.90, H)[:, None, None]
    return np.broadcast_to(g, (H, W, 3)).copy() * np.array([1.0, 0.995, 0.985])


def shade(p, n, v):
    L1 = np.array([-0.45, -0.55, 0.75]); L1 /= np.linalg.norm(L1)
    L2 = np.array([0.8, -0.45, -0.05]); L2 /= np.linalg.norm(L2)
    d1 = np.clip(n @ L1, 0, 1)
    d2 = np.clip(n @ L2, 0, 1)
    amb = 0.30 + 0.12 * n[:, 2]
    h = L1 + v
    h /= np.linalg.norm(h)
    spec = np.clip(n @ h, 0, 1) ** 36 * 0.16
    # годичные кольца ясеня: пласть, сердцевина далеко внизу, волокна вдоль X
    dist = (np.hypot(p[:, 1] - 3.0, p[:, 2] + 260.0 + 0.015 * p[:, 0])
            + 0.9 * np.sin(p[:, 0] * 0.045 + p[:, 1] * 0.03) + 0.5 * np.sin(p[:, 0] * 0.13))
    fr = (dist / 3.1 + 0.25 * np.sin(dist * 0.21)) % 1.0
    grain = (1 - 0.07 * np.exp(-((fr - 0.5) / 0.07) ** 2) - 0.03 * np.exp(-((fr - 0.62) / 0.2) ** 2)
             + 0.025 * np.sin(dist * 0.45))
    col = WOOD * grain[:, None]
    return col * (amb + 0.75 * d1 + 0.22 * d2)[:, None] + spec[:, None]


def make(P: Params, out: Path):
    objs = bodies(P)
    views = {
        "render_3q.png": dict(eye_dir=(0.62, -1.0, 0.55), width_mm=150, W=1400, H=900, center=(8, 0, -2)),
        "render_side.png": dict(eye_dir=(0.0, -1.0, 0.0), width_mm=150, W=1400, H=700, center=(10, 0, 0)),
        "render_tip.png": dict(eye_dir=(1.0, -0.62, 0.42), width_mm=100, W=1100, H=900, center=(30, 0, 0)),
        "render_end.png": dict(eye_dir=(1.0, 0.0, 0.0), width_mm=62, W=900, H=900, center=(50, 0, 0)),
    }
    for name, kw in views.items():
        trace(objs, **kw).save(out / name)
        print(name)


if __name__ == "__main__":
    import sys
    o = Path(__file__).resolve().parent / "out"
    o.mkdir(exist_ok=True)
    make(Params(), o)
