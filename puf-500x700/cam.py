"""Траектории фрезы по раскладке — в нейтральном виде (штрихи X/Y/Z).

Штрих: опускание в первую точку, рез по точкам, подъём. Постпроцессор
только форматирует штрихи в G-код, так что цеховой пост подключается
заменой post_generic.py.
"""
import math
from dataclasses import dataclass

from shapely.geometry import LineString
from shapely.geometry.polygon import orient

import params as P

R = P.TOOL_D / 2


@dataclass
class Stroke:
    group: str      # mark / pocket / hole / nested / window / outline
    label: str
    points: list    # [(x, y, z)]


def _ring(poly, ccw):
    poly = orient(poly.simplify(P.ARC_TOL / 2), 1.0 if ccw else -1.0)
    return list(poly.exterior.coords)[:-1]


def _offset(contour, d):
    poly = contour.polygon(P.ARC_TOL).buffer(d, quad_segs=24)
    if poly.is_empty or poly.geom_type != "Polygon":
        return None
    return poly


def _dogbone_centers(contour):
    """Центры косточек: полуокружности (bulge ±1) у контуров, которые не окружности."""
    if contour.circle:
        return []
    pts = contour.pts
    n = len(pts)
    return [((pts[i][0] + pts[(i + 1) % n][0]) / 2, (pts[i][1] + pts[(i + 1) % n][1]) / 2)
            for i in range(n) if abs(abs(pts[i][2]) - 1.0) < 1e-9]


def _with_dogbones(loop, centers):
    """Явный заход фрезы в центр каждой косточки: эквидистанта доходит туда
    лишь вырожденным «усом», который теряется при аппроксимации."""
    for c in centers:
        n = len(loop)
        best = None
        for i in range(n):
            a, b = loop[i], loop[(i + 1) % n]
            dx, dy = b[0] - a[0], b[1] - a[1]
            L2 = dx * dx + dy * dy or 1e-12
            t = max(0.0, min(1.0, ((c[0] - a[0]) * dx + (c[1] - a[1]) * dy) / L2))
            q = (a[0] + t * dx, a[1] + t * dy)
            d = math.dist(q, c)
            if best is None or d < best[0]:
                best = (d, i, q)
        d, i, q = best
        assert d < R, "косточка далеко от траектории"
        if d > 1e-3:
            loop = loop[:i + 1] + [q, c, q] + loop[i + 1:]
    return loop


def pass_depths():
    n = math.ceil(P.CUT_DEPTH / P.PASS_MAX - 1e-9)
    return [-P.CUT_DEPTH * (i + 1) / n for i in range(n)]


def _start_on_longest(loop):
    """Начать контур на четверти самого длинного отрезка: врезание не в углу
    и не на перемычке (перемычки ставятся по серединам отрезков)."""
    n = len(loop)
    i = max(range(n), key=lambda k: math.dist(loop[k], loop[(k + 1) % n]))
    a, b = loop[i], loop[(i + 1) % n]
    st = (a[0] + (b[0] - a[0]) / 4, a[1] + (b[1] - a[1]) / 4)
    return [st] + loop[i + 1:] + loop[:i + 1]


def _tab_intervals(loop, count):
    """Интервалы длины дуги (по траектории), где фреза поднимается над перемычкой."""
    if count <= 0:
        return []
    closed = loop + [loop[0]]
    seglen = [math.dist(closed[k], closed[k + 1]) for k in range(len(loop))]
    total = sum(seglen)
    half = P.TAB_W / 2 + R
    cands, s = [], 0.0
    for L in seglen:
        if L >= 2 * half + 10:
            cands.append(s + L / 2)
        s += L
    chosen = []
    for i in range(count):
        target = total * (i + 0.5) / count
        free = [c for c in cands if c not in chosen]
        if not free:
            break
        chosen.append(min(free, key=lambda c: min(abs(c - target), total - abs(c - target))))
    return sorted((c - half, c + half) for c in chosen)


def _loop_at(loop, z, tabs, z_tab):
    """Точки одного обхода на глубине z с подъёмами над перемычками."""
    closed = loop + [loop[0]]
    if not tabs or z >= z_tab:
        return [(x, y, z) for x, y in closed]
    line = LineString(closed)
    cuts = sorted({0.0, line.length} | {v for iv in tabs for v in iv})
    out = []
    for a, b in zip(cuts, cuts[1:]):
        mid = (a + b) / 2
        zz = z_tab if any(t0 <= mid <= t1 for t0, t1 in tabs) else z
        seg = _substring(line, a, b)
        if out and out[-1][2] != zz:
            out.append((seg[0][0], seg[0][1], zz))
        out += [(x, y, zz) for x, y in (seg if not out else seg[1:])]
    if out[-1][2] != z:
        out.append((out[-1][0], out[-1][1], z))
    return out


def _substring(line, a, b):
    from shapely.ops import substring
    return list(substring(line, a, b).coords)


def profile(contour, outside, tabs=0, label="", group=""):
    poly = _offset(contour, R if outside else -R)
    assert poly is not None, f"{label}: фреза Ø{P.TOOL_D} не проходит"
    ccw = (not outside) if P.CLIMB else outside
    loop = _start_on_longest(_with_dogbones(_ring(poly, ccw), _dogbone_centers(contour)))
    z_tab = -(P.T - P.TAB_H)
    iv = _tab_intervals(loop, tabs)
    pts = []
    for z in pass_depths():
        pts += _loop_at(loop, z, iv, z_tab)
    return Stroke(group, label, pts)


def pocket(contour, label=""):
    """Паз под шип выбирается целиком — без незакреплённых обрезков."""
    loops, d, last = [], R, None
    while _offset(contour, -d) is not None:
        loops.append(_start_on_longest(_ring(_offset(contour, -d), P.CLIMB)))
        last = d
        d += P.STEPOVER * P.TOOL_D
    assert loops, f"{label}: паз уже фрезы"
    lo, hi = last, d                       # глубина «вписанного» радиуса
    for _ in range(40):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if _offset(contour, -mid) is not None else (lo, mid)
    if lo - last > R * 0.9:                # середина не выбрана — проход по оси
        loops.append(_start_on_longest(_ring(_offset(contour, -(lo - 0.05)), P.CLIMB)))
    loops[0] = _start_on_longest(_with_dogbones(loops[0], _dogbone_centers(contour)))
    loops.reverse()                        # изнутри наружу, последний — чистовой
    pts = []
    for z in pass_depths():
        for lp in loops:
            pts += [(x, y, z) for x, y in lp + [lp[0]]]
        pts.append((loops[0][0][0], loops[0][0][1], z))   # к началу внутреннего обхода
    return Stroke("pocket", label, pts[:-1])


def _nearest_order(strokes, start=(0.0, 0.0)):
    left, out, cur = list(strokes), [], start
    while left:
        s = min(left, key=lambda st: math.dist(cur, st.points[0][:2]))
        left.remove(s)
        out.append(s)
        cur = s.points[-1][:2]
    return out


def toolpaths(placed):
    """Все штрихи листа в порядке резки: метки, пазы, отверстия, вложенные
    детали, окна рамок, наружные контуры."""
    groups = {g: [] for g in ("mark", "pocket", "hole", "nested", "window", "outline")}
    for pl in placed:
        p = pl.part
        for x, y in p.marks:
            groups["mark"].append(Stroke("mark", f"{pl.label} опора", [(x, y, -P.MARK_DEPTH)]))
        for kind, c in p.holes:
            if kind == "slot":
                groups["pocket"].append(pocket(c, f"{pl.label} паз"))
            elif kind == "hole":
                groups["hole"].append(profile(c, False, 0, f"{pl.label} отв.", "hole"))
            else:
                groups["window"].append(profile(c, False, P.TABS_WINDOW, f"{pl.label} окно", "window"))
        g = "nested" if pl.parent else "outline"
        groups[g].append(profile(p.outline, True, P.TABS_OUTER, f"{pl.label} контур", g))
    out, cur = [], (0.0, 0.0)
    for g in groups.values():
        ordered = _nearest_order(g, cur)
        if ordered:
            cur = ordered[-1].points[-1][:2]
        out += ordered
    return out


def stats(strokes):
    cut = rapid = 0.0
    cur = (0.0, 0.0)
    for s in strokes:
        rapid += math.dist(cur, s.points[0][:2])
        for a, b in zip(s.points, s.points[1:]):
            cut += math.dist(a[:2], b[:2])
        cur = s.points[-1][:2]
    minutes = cut / P.F_CUT + len(strokes) * 2 * (P.SAFE_Z + P.T) / P.F_PLUNGE + rapid / 8000
    return {"cut_m": cut / 1000, "strokes": len(strokes), "minutes": minutes}
