"""Контуры с дугами: вершины (x, y, bulge), как в DXF LWPOLYLINE.

bulge вершины относится к сегменту от неё до следующей: 0 — прямая,
tan(угол/4) — дуга, >0 — против часовой.
"""
import math

from shapely.geometry import Polygon
from shapely.geometry.polygon import orient

K90 = math.tan(math.pi / 8)   # bulge дуги 90°


class Contour:
    def __init__(self, pts, circle=None):
        self.pts = [(float(x), float(y), float(b)) for x, y, b in pts]
        self.circle = circle          # (cx, cy, r) для отверстий -> CIRCLE в DXF

    # --- преобразования
    def moved(self, dx, dy):
        c = self.circle and (self.circle[0] + dx, self.circle[1] + dy, self.circle[2])
        return Contour([(x + dx, y + dy, b) for x, y, b in self.pts], c)

    def rot90(self):
        """Поворот на 90° против часовой вокруг начала координат."""
        c = self.circle and (-self.circle[1], self.circle[0], self.circle[2])
        return Contour([(-y, x, b) for x, y, b in self.pts], c)

    def reversed(self):
        n = len(self.pts)
        out = []
        for k in range(n):
            x, y, _ = self.pts[n - 1 - k]
            b = self.pts[(n - 2 - k) % n][2]
            out.append((x, y, -b))
        return Contour(out, self.circle)

    # --- дискретизация
    def points(self, tol=0.05):
        out = []
        n = len(self.pts)
        for i in range(n):
            x1, y1, b = self.pts[i]
            x2, y2, _ = self.pts[(i + 1) % n]
            out.append((x1, y1))
            if abs(b) > 1e-12:
                out.extend(arc_points((x1, y1), (x2, y2), b, tol)[1:-1])
        return out

    def polygon(self, tol=0.05):
        return orient(Polygon(self.points(tol)), 1.0)

    def bbox(self):
        xs, ys = zip(*self.points(0.5))
        return min(xs), min(ys), max(xs), max(ys)


def arc_points(p1, p2, b, tol):
    theta = 4 * math.atan(b)
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    c = math.hypot(dx, dy)
    r = c / (2 * math.sin(abs(theta) / 2))
    mx, my = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2
    nx, ny = -dy / c, dx / c                      # левая нормаль к хорде
    h = (c / 2) / math.tan(theta / 2)
    cx, cy = mx + nx * h, my + ny * h
    a1 = math.atan2(p1[1] - cy, p1[0] - cx)
    step = 2 * math.acos(max(-1.0, 1 - tol / r)) if r > tol else math.pi / 4
    n = max(2, math.ceil(abs(theta) / step))
    return [(cx + r * math.cos(a1 + theta * k / n), cy + r * math.sin(a1 + theta * k / n))
            for k in range(n + 1)]


# ---------------------------------------------------------------- фигуры
def rounded_rect(w, h, r, cx=0.0, cy=0.0):
    x0, y0, x1, y1 = cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2
    if r <= 0:
        return Contour([(x0, y0, 0), (x1, y0, 0), (x1, y1, 0), (x0, y1, 0)])
    return Contour([
        (x0 + r, y0, 0), (x1 - r, y0, K90), (x1, y0 + r, 0), (x1, y1 - r, K90),
        (x1 - r, y1, 0), (x0 + r, y1, K90), (x0, y1 - r, 0), (x0, y0 + r, K90),
    ])


def circle(cx, cy, r):
    return Contour([(cx - r, cy, 1.0), (cx + r, cy, 1.0)], circle=(cx, cy, r))


def dogboned(pts, corners, r):
    """Многоугольник из прямых; в углах из `corners` — «косточка» радиуса r.

    Косточка: полуокружность через вершину угла с центром на биссектрисе
    свободной зоны в r от вершины — фреза радиуса r выбирает угол полностью.
    """
    s = math.sqrt(2) * r
    n = len(pts)
    out = []
    for i, (px, py) in enumerate(pts):
        if i not in corners:
            out.append((px, py, 0.0))
            continue
        ax, ay = pts[i - 1]
        bx, by = pts[(i + 1) % n]
        li, lo = math.hypot(px - ax, py - ay), math.hypot(bx - px, by - py)
        assert li > s and lo > s, "ребро короче косточки"
        dix, diy = (px - ax) / li, (py - ay) / li
        dox, doy = (bx - px) / lo, (by - py) / lo
        assert abs(dix * dox + diy * doy) < 1e-9, "косточка только в прямом угле"
        p1 = (px - s * dix, py - s * diy)
        p2 = (px + s * dox, py + s * doy)
        cross = (p2[0] - p1[0]) * (py - p1[1]) - (p2[1] - p1[1]) * (px - p1[0])
        out.append((p1[0], p1[1], 1.0 if cross < 0 else -1.0))
        out.append((p2[0], p2[1], 0.0))
    return Contour(out)


def slot(cx, cy, w, h, r):
    """Прямоугольный паз w x h с косточками во всех углах."""
    x0, y0, x1, y1 = cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2
    return dogboned([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], {0, 1, 2, 3}, r)
