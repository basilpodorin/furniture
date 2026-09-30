"""Проверка: глубина деталей каркаса под поверхностью обивки (толщина мягких слоёв)."""
import numpy as np

import params as P
from .frame import S


def part_points(part, step=8.0):
    """Точки по контуру детали на обеих пластях, мировые координаты."""
    pts2 = []
    for ring in [part.shape.exterior, *part.shape.interiors]:
        L = ring.length
        for s in np.arange(0, L, step):
            p = ring.interpolate(s)
            pts2.append((p.x, p.y))
    pts2 = np.array(pts2)
    out = []
    t = part.thickness
    if part.kind == "plate":
        for z in (part.z0, part.z0 + t):
            out.append(np.c_[pts2, np.full(len(pts2), z)])
        return np.vstack(out), [None]
    from .export_3d import placements
    variants = placements(part)
    for (ox, oy), (dx, dy), _ in variants:
        nx, ny = -dy, dx
        for side in (-t / 2, t / 2):
            X = ox + pts2[:, 0] * dx + side * nx
            Y = oy + pts2[:, 0] * dy + side * ny
            out.append(np.c_[X, Y, pts2[:, 1]])
    return np.vstack(out), variants


def clearance_report(frame):
    """Минимальная глубина под обивкой для каждой детали. Плоскость дна
    (z ≤ верх П1) исключена — снизу только ткань; для неё отдельная проверка
    отступа кромки П1 от боковой поверхности."""
    rows = []
    # у низа модель «проседает» (дно волнистое, z 36–47) — реальное дно плоское,
    # поэтому зону до 25 мм над П1 не проверяем
    zb = P.Z_P1 + P.PLY + 25
    for part in frame.parts:
        pts, _ = part_points(part)
        pts = pts[pts[:, 2] > zb] if part.code != "П1" else pts
        if part.code == "П1":
            ring = part.shape.exterior
            dmin, where = 1e9, None
            for z in (P.Z_P1 + 5, P.Z_P1 + P.PLY):
                sec = S.plan(z + 8)
                for s_ in np.arange(0, ring.length, 10):
                    q = ring.interpolate(s_)
                    d = sec.exterior.distance(q) if sec.contains(q) else -sec.exterior.distance(q)
                    if d < dmin:
                        dmin, where = d, np.array([q.x, q.y, z])
            rows.append((part.code, part.name + " (отступ кромки)", float(dmin), where))
            continue
        if len(pts) == 0:
            continue
        d = S.signed_distance(pts)
        i = int(np.argmin(d))
        rows.append((part.code, part.name, float(d.min()), pts[i]))
    return rows
