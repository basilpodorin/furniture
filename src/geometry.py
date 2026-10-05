"""Геометрия деталей стола Basil (мм, оси X вправо, Y вверх).

Все размеры взяты из «карты сборки» и DXF проекта (см. source/). Каждая
деталь — замкнутый контур из отрезков и дуг; хранится как список вершин
(x, y, bulge) в формате LWPOLYLINE (bulge = tan(sweep/4), >0 — против часовой).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

TOL = 0.3  # допуск стыковки концов дуг из DXF, мм


@dataclass
class Line:
    p: tuple
    q: tuple


@dataclass
class Arc:
    c: tuple
    r: float
    a0: float  # градусы, против часовой от a0 к a1
    a1: float

    def pt(self, a):
        t = math.radians(a)
        return (self.c[0] + self.r * math.cos(t), self.c[1] + self.r * math.sin(t))

    @property
    def p(self):
        return self.pt(self.a0)

    @property
    def q(self):
        return self.pt(self.a1)

    @property
    def sweep(self):
        return (self.a1 - self.a0) % 360


@dataclass
class Face:
    """Торцевая грань с пазами под ламели (центр грани и внутренняя нормаль)."""
    p: tuple
    q: tuple
    name: str = ""

    @property
    def length(self):
        return math.dist(self.p, self.q)

    @property
    def mid(self):
        return ((self.p[0] + self.q[0]) / 2, (self.p[1] + self.q[1]) / 2)


@dataclass
class Part:
    key: str
    title: str
    qty: str
    verts: list  # [(x, y, bulge)], замкнутый контур
    faces: list = field(default_factory=list)
    note: str = ""

    def bbox(self):
        pts = sample(self.verts)
        xs, ys = zip(*pts)
        return min(xs), min(ys), max(xs), max(ys)


# ---------------------------------------------------------------- контур ---

def _d(a, b):
    return math.dist(a, b)


def chain(ents, tol=TOL):
    """Склеивает отрезки/дуги в замкнутый контур -> [(x, y, bulge)]."""
    ents = list(ents)
    first = ents.pop(0)
    path = [(first.p, first.q, first)]
    while ents:
        end = path[-1][1]
        for e in ents:
            if _d(e.p, end) < tol:
                path.append((end, e.q, e)); ents.remove(e); break
            if _d(e.q, end) < tol:
                path.append((end, e.p, e)); ents.remove(e); break
        else:
            raise ValueError("контур не замкнут около %r" % (end,))
    if _d(path[-1][1], path[0][0]) > tol:
        raise ValueError("контур не замкнут")
    verts = []
    for s, e, ent in path:
        b = 0.0
        if isinstance(ent, Arc):
            ccw = _d(s, ent.p) < _d(s, ent.q)
            b = math.tan(math.radians(ent.sweep) / 4) * (1 if ccw else -1)
        verts.append([s[0], s[1], b])
    # снимаем микро-зазоры между дугами: вершина = конец предыдущего элемента
    for i, v in enumerate(verts):
        v[0], v[1] = path[i - 1][1] if _d(path[i - 1][1], v[:2]) < tol else v[:2]
    return [tuple(v) for v in verts]


def sample(verts, step_deg=1.0):
    """Контур -> полилиния (список точек), дуги разбиты на отрезки."""
    out = []
    n = len(verts)
    for i in range(n):
        x0, y0, b = verts[i]
        x1, y1, _ = verts[(i + 1) % n]
        out.append((x0, y0))
        if abs(b) > 1e-12:
            sweep = 4 * math.atan(b)
            ch = math.dist((x0, y0), (x1, y1))
            r = ch / (2 * math.sin(abs(sweep) / 2))
            mx, my = (x0 + x1) / 2, (y0 + y1) / 2
            h = r * math.cos(abs(sweep) / 2)
            ux, uy = (x1 - x0) / ch, (y1 - y0) / ch
            side = 1 if b > 0 else -1
            cx, cy = mx - side * uy * h, my + side * ux * h
            a0 = math.atan2(y0 - cy, x0 - cx)
            k = max(2, int(abs(math.degrees(sweep)) / step_deg))
            for j in range(1, k):
                a = a0 + sweep * j / k
                out.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return out


def area(verts):
    pts = sample(verts, 0.25)
    return sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1]
               for i in range(len(pts))) / 2


def transform(verts, rot_deg=0.0, dx=0.0, dy=0.0, mirror_x=False):
    """Поворот на rot_deg, затем (опц.) зеркало по X и сдвиг."""
    t = math.radians(rot_deg)
    c, s = math.cos(t), math.sin(t)
    out = []
    for x, y, b in verts:
        X, Y = x * c - y * s, x * s + y * c
        if mirror_x:
            X, b = -X, -b
        out.append((X + dx, Y + dy, b))
    return out


def tf_pt(p, rot_deg=0.0, dx=0.0, dy=0.0, mirror_x=False):
    t = math.radians(rot_deg)
    X = p[0] * math.cos(t) - p[1] * math.sin(t)
    Y = p[0] * math.sin(t) + p[1] * math.cos(t)
    if mirror_x:
        X = -X
    return (X + dx, Y + dy)


def arc_between(c, r, a, b):
    """Короткая дуга окружности (c, r) между точками a и b."""
    aa = math.degrees(math.atan2(a[1] - c[1], a[0] - c[0])) % 360
    ab = math.degrees(math.atan2(b[1] - c[1], b[0] - c[0])) % 360
    return Arc(c, r, aa, ab) if (ab - aa) % 360 <= 180 else Arc(c, r, ab, aa)


# ---------------------------------------------------------------- детали ---

def _ang(deg):
    return math.radians(deg)


def leg() -> Part:
    """Стойка (4 шт.): трапеция с двумя «скосами» и двумя вогнутыми дугами.
    Верхняя кромка 741.26 горизонтальна, материал ниже неё (как на чертеже)."""
    T0, T1 = (0.0, 0.0), (741.26, 0.0)
    a_left, a_right, tilt = 56.61, 40.12, 2.0
    P1 = (137.57 * math.cos(_ang(a_left)), -137.57 * math.sin(_ang(a_left)))
    # R110: касательная к длинной кромке (наклон 2°), дуга 39°, центр снизу
    t_start = tilt + 39.0
    O1 = (P1[0] + 110 * math.sin(_ang(t_start)), P1[1] - 110 * math.cos(_ang(t_start)))
    Q = (O1[0] - 110 * math.sin(_ang(tilt)), O1[1] + 110 * math.cos(_ang(tilt)))
    R1 = (Q[0] + 483.23 * math.cos(_ang(tilt)), Q[1] + 483.23 * math.sin(_ang(tilt)))
    # R25: дуга 51° (22.25 мм), центр снизу
    O2 = (R1[0] + 25 * math.sin(_ang(tilt)), R1[1] - 25 * math.cos(_ang(tilt)))
    t_end = tilt - 51.0
    S = (O2[0] - 25 * math.sin(_ang(t_end)), O2[1] + 25 * math.cos(_ang(t_end)))
    ents = [
        Line(T0, P1),
        arc_between(O1, 110, P1, Q),
        Line(Q, R1),
        arc_between(O2, 25, R1, S),
        Line(S, T1),
        Line(T1, T0),
    ]
    # контур по часовой стрелке/против — chain сам ориентирует по порядку; приведём к CCW
    verts = chain(ents)
    if area(verts) < 0:
        verts = _reverse(verts)
    return Part("leg", "Стойка", "4 шт.", verts,
                faces=[Face(T0, P1, "торец А (137.57)"), Face(S, T1, "торец Б (123.62)")],
                note="Толщина заготовки 70. Для зеркальной стойки шаблон переворачивают.")


def upper() -> Part:
    """Верхняя часть подстолья (4 шт.): 383.72 × 70, скос 39.88° и R25."""
    A, B, C = (0.0, 0.0), (383.72, 0.0), (383.72, -70.0)
    E = (383.72 - 269.42, -70.0)
    O = (E[0], -70.0 - 25.0)
    D = (O[0] - 25 * math.sin(_ang(51.0)), O[1] + 25 * math.cos(_ang(51.0)))
    ents = [Line(A, B), Line(B, C), Line(C, E),
            arc_between(O, 25, D, E),
            Line(D, A)]
    verts = chain(ents)
    if area(verts) < 0:
        verts = _reverse(verts)
    return Part("upper", "Верхняя часть подстолья", "4 шт.", verts,
                faces=[Face(D, A, "скос (123.62)"), Face(B, C, "торец (70)")],
                note="Толщина заготовки 70.")


def lower() -> Part:
    """Нижняя часть подстолья (4 шт.): 255 × 70, скос 43.39° и R110."""
    L0, L1, L2 = (0.0, 0.0), (255.0, 0.0), (255.0, 70.0)
    S0 = (255.0 - 85.81, 70.0)
    O = (S0[0], 70.0 + 110.0)
    P = (O[0] - 110 * math.sin(_ang(39.0)), O[1] - 110 * math.cos(_ang(39.0)))
    ents = [Line(L0, L1), Line(L1, L2), Line(L2, S0),
            arc_between(O, 110, P, S0),
            Line(P, L0)]
    verts = chain(ents)
    if area(verts) < 0:
        verts = _reverse(verts)
    return Part("lower", "Нижняя часть подстолья", "4 шт.", verts,
                faces=[Face(P, L0, "скос (137.57)"), Face(L1, L2, "торец (70)")],
                note="Толщина заготовки 70.")


def hub() -> Part:
    """Узел-«звезда» (ступица): три плоскости по 70 и три вогнутые дуги."""
    ents = [
        Line((-35.0, 0.0), (35.0, 0.0)),
        Arc((132.86, 0.0), 97.86, 180.0, 230.03),
        Line((70.0, -74.96), (35.0, -135.58)),
        Arc((0.0, -196.2), 70.0, 60.0, 120.0),
        Line((-35.0, -135.58), (-70.0, -74.96)),
        Arc((-132.86, 0.0), 97.86, 309.97, 360.0),
    ]
    verts = chain(ents, tol=0.1)
    if area(verts) < 0:
        verts = _reverse(verts)
    return Part("hub", "Узел-«звезда»", "4 шт.", verts,
                faces=[Face((-35.0, 0.0), (35.0, 0.0), "грань 1"),
                       Face((70.0, -74.96), (35.0, -135.58), "грань 2"),
                       Face((-35.0, -135.58), (-70.0, -74.96), "грань 3")],
                note="Толщина заготовки 70. Фигура симметрична — переворот не нужен.")


def _top_arcs(rs, re_, rc, end_a):
    """Дуги верхней (y>=0) половины столешницы/подстолья в системе DXF (длинная ось = Y).
    Центры и углы — из исходного DXF с полной точностью; радиусы: боковая rs, торцевая re_, угловая rc.
    end_a — угол конца торцевой дуги у оси (90.2349 для столешницы, 90.2409 для подстолья)."""
    CX, CY = 304.9036569372, 1044.6767781768     # центр угловой дуги
    EX, EY = 4.0807303435, 254.5959728026        # центр торцевой дуги
    SX = 11772.7485064293                         # |центр боковой дуги|
    a1, a2 = 4.943590257, 69.1556902163
    return [
        Arc((-SX, 0.0), rs, 0.0, a1),                         # правая боковая (половина)
        Arc((CX, CY), rc, a1, a2),                             # угол
        Arc((EX, EY), re_, a2, end_a),                         # торец (правая половина)
        Arc((-EX, EY), re_, 180.0 - end_a, 180.0 - a2),        # торец (левая половина)
        Arc((-CX, CY), rc, 180.0 - a2, 180.0 - a1),            # угол
        Arc((SX, 0.0), rs, 180.0 - a1, 180.0),                 # левая боковая (половина)
    ]


def _half_top(key, title, rs, re_, rc, end_a, note) -> Part:
    arcs = _top_arcs(rs, re_, rc, end_a)
    x_side = -11772.7485064293 + rs                                # = ±(w/2)
    close = Line((-x_side, 0.0), (x_side, 0.0))
    verts = chain(arcs + [close], tol=0.3)
    if area(verts) < 0:
        verts = _reverse(verts)
    # длинная ось -> X; ось симметрии (прямая кромка шаблона) остаётся на y=0 → x=0
    verts = transform(verts, rot_deg=-90.0)
    return Part(key, title, "1 шаблон; обрабатывает оба торца переворотом", verts,
                faces=[], note=note)


def tabletop_half() -> Part:
    return _half_top("tabletop_half", "Столешница 2500×1000×40 — ПОЛОВИНА (торцевая)", 12272.75, 995.41, 150.0, 90.2348868498,
                     "Прямая кромка шаблона = поперечная осевая линия заготовки. Обработать оба торца, переворачивая шаблон.")


def subplate_half() -> Part:
    return _half_top("subplate_half", "Подстолье 2450×950×24 — ПОЛОВИНА (торцевая)", 12247.75, 970.41, 125.0, 90.2409380971,
                     "Прямая кромка шаблона = поперечная осевая линия заготовки. Обработать оба торца, переворачивая шаблон.")


def _reverse(verts):
    """Обращение направления обхода контура с корректным переносом bulge."""
    n = len(verts)
    out = []
    for i in range(n):
        x, y, _ = verts[(n - i) % n]
        b_prev = verts[(n - i - 1) % n][2]
        out.append((x, y, -b_prev))
    return out


def all_parts():
    return [tabletop_half(), subplate_half(), leg(), upper(), lower(), hub()]
