"""Построение деталей каркаса кресла SPIN по поверхности 3D-модели.

Принцип: кромки каркаса — эквидистанта поверхности обивки внутрь на толщину
мягких слоёв. Горизонтальные плиты-обвязки (П1, П3, П4) строятся по сечениям в плане,
вертикальные лекала — по сечениям модели в своей плоскости.

Схема (как в ЧПУ-каркасах диванов с лекалами):
  • боковина Б — одно цельное лекало на сторону (x = ±SIDE_X), от низа до П4 и от торца
    до угла спинки; она же — боковая стенка короба сиденья;
  • короб сиденья — П1 (дно) + перегородки ПГ1/ПГ2 (сквозные шипы в боковины) + П3;
  • спинка — рёбра-лекала РС на всю высоту (П1…П4), проходят сквозь П3 «паз в паз»;
  • фасад под сиденьем — короткие рёбра РН (П1…П3);
  • П4 — верхняя обвязка, надевается последней на шипы РС и Б и запирает сборку.
"""
from dataclasses import dataclass, field

import numpy as np
from shapely import affinity
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union

import params as P
from .geom import largest, rounded_rect
from .model import surface

T = P.PLY
X_IN, X_OUT = P.SIDE_X - P.SIDE_T / 2, P.SIDE_X + P.SIDE_T / 2   # пласти боковины
RIB_KW = dict(thickness=P.PLY_RIB, material=f"Фанера берёзовая ФК {P.PLY_RIB} мм")


# ------------------------------------------------------------------ детали
@dataclass
class Part:
    code: str                 # маркировка детали (П1, Р-Н3 …)
    name: str
    shape: Polygon            # контур в локальных координатах
    kind: str = "plate"       # plate — горизонтальная; rib — вертикальная
    thickness: float = T
    qty: int = 1
    z0: float = 0.0           # plate: низ детали
    origin: tuple = (0.0, 0.0)  # rib: точка u=0 в плане (мировые X, Y)
    direction: tuple = (1.0, 0.0)  # rib: направление оси u в плане
    material: str = "Фанера берёзовая ФК 18 мм"
    holes: list = field(default_factory=list)   # (x, y, d) — сверления
    marks: list = field(default_factory=list)   # линии разметки (гравировка)
    note: str = ""
    mirror_of: str = ""       # деталь симметрична другой (для 3D)
    instances: list = field(default_factory=list)  # [(origin, direction)] — несколько мест

    @property
    def area_m2(self):
        return self.shape.area / 1e6

    @property
    def mass_kg(self):
        return self.area_m2 * self.thickness / 1000 * P.PLY_RHO * self.qty


# ------------------------------------------------------------------ геометрия
S = surface()
_env_cache = {}


def plan_env(z, r=P.OUT_OFFSET, steps=9):
    """Плановое сечение, сжатое шаром радиуса r (эквидистанта внутрь в 3D)."""
    key = (round(z, 2), r)
    if key in _env_cache:
        return _env_cache[key]
    acc = None
    for dz in np.linspace(-r, r, steps):
        sec = S.plan(z + dz)
        if sec.is_empty:
            acc = Polygon()
            break
        g = sec.buffer(-np.sqrt(max(r * r - dz * dz, 0.0)), quad_segs=8)
        acc = g if acc is None else acc.intersection(g)
    acc = acc if acc is not None else Polygon()
    _env_cache[key] = acc
    return acc


def plate_env(z0, thickness=T, r=P.OUT_OFFSET):
    return plan_env(z0, r).intersection(plan_env(z0 + thickness, r))


def smooth(poly, r=6):
    return largest(poly.buffer(r, quad_segs=8).buffer(-2 * r, quad_segs=8).buffer(r, quad_segs=8))


def fair_ring(coords, sigma=8.0, step=2.0):
    """Сглаживание замкнутого контура гауссовым фильтром по длине дуги (без волн и изломов)."""
    ls = LineString(coords)
    L = ls.length
    n = max(int(L / step), 32)
    pts = np.array([ls.interpolate(t).coords[0] for t in np.linspace(0, L, n, endpoint=False)])
    k = max(int(3 * sigma / (L / n)), 1)
    w = np.exp(-0.5 * (np.arange(-k, k + 1) * (L / n) / sigma) ** 2)
    w /= w.sum()
    ext = np.r_[pts[-k:], pts, pts[:k]]
    return np.c_[np.convolve(ext[:, 0], w, "valid"), np.convolve(ext[:, 1], w, "valid")]


def fair(poly, r_close=25, r_open=25, sigma=8.0):
    """«Чистовой» контур детали из сечений модели: закрытие (заполнить мелкие впадины),
    открытие (скруглить выступы и углы), затем плавная кривизна. Детали без волн."""
    g = largest(poly)
    if r_close:
        g = largest(g.buffer(r_close, quad_segs=16).buffer(-r_close, quad_segs=16))
    if r_open:
        g = largest(g.buffer(-r_open, quad_segs=16).buffer(r_open, quad_segs=16))
    g = Polygon(fair_ring(g.exterior.coords, sigma)).buffer(0)
    return largest(g).simplify(0.15, preserve_topology=True)


def symmetric(poly):
    """Точная симметрия относительно плоскости x = 0 (пересечение с зеркальным)."""
    return largest(poly.intersection(affinity.scale(poly, -1, 1, origin=(0, 0))))


def plane_section(origin, direction):
    """Сечение поверхности вертикальной плоскостью через origin вдоль direction.
    Возвращает область в координатах (u, z)."""
    ox, oy = origin
    dx, dy = direction
    nx, ny = -dy, dx
    V = S.V
    d = (V[:, 0] - ox) * nx + (V[:, 1] - oy) * ny
    d = np.where(d == 0, 1e-7, d)
    Tt = S.T
    dt = d[Tt]
    tris = Tt[~((dt > 0).all(1) | (dt < 0).all(1))]
    adj, pts = {}, {}
    for tri in tris:
        es = []
        for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
            if (d[a] > 0) != (d[b] > 0):
                k = (a, b) if a < b else (b, a)
                if k not in pts:
                    i, j = k
                    t = d[i] / (d[i] - d[j])
                    p = V[i] + t * (V[j] - V[i])
                    pts[k] = ((p[0] - ox) * dx + (p[1] - oy) * dy, p[2])
                es.append(k)
        if len(es) == 2:
            adj.setdefault(es[0], []).append(es[1])
            adj.setdefault(es[1], []).append(es[0])
    polys, seen = [], set()
    for start in adj:
        if start in seen:
            continue
        loop, prev, cur = [start], None, start
        seen.add(start)
        while True:
            nxt = [q for q in adj[cur] if q != prev and q not in seen]
            if not nxt:
                break
            prev, cur = cur, nxt[0]
            loop.append(cur)
            seen.add(cur)
        if len(loop) > 3:
            polys.append(Polygon([pts[k] for k in loop]).buffer(0))
    polys = sorted((p for p in polys if p.area > 100), key=lambda p: -p.area)
    region = Polygon()
    for p in polys:
        region = region.symmetric_difference(p)
    return region


def pick(region, pt):
    geoms = getattr(region, "geoms", [region])
    for g in geoms:
        if g.contains(Point(pt)):
            return g
    return min(geoms, key=lambda g: g.distance(Point(pt))) if geoms else Polygon()


# ------------------------------------------------------------------ полость
def back_belt_y(z):
    z0, z1 = P.Z_P3 + T, P.Z_P4 + T
    t = np.clip((z - z0) / (z1 - z0), 0, 1)
    return P.BACK_BELT_Y0 + t * (P.BACK_BELT_Y1 - P.BACK_BELT_Y0)


def back_gap(z):
    z0, z1 = P.Z_P3 + T, P.Z_P4
    t = np.clip((z - z0) / (z1 - z0), 0, 1)
    return P.BACK_BELT_GAP * (1 - t) + 5 * t


def cavity(z, extra_back=0.0):
    """Внутренняя граница каркаса стенки (обшивка подлокотников, ремни спинки)."""
    yb = back_belt_y(z) + extra_back
    return rounded_rect(-P.ARM_SKIN_X, -1200, P.ARM_SKIN_X, yb, P.CAVITY_R)


# ------------------------------------------------------------------ станции рёбер
def half_curve(poly):
    """Правая половина (x ≥ 0) наружного контура от центра спинки к центру фасада."""
    ring = LineString(poly.exterior.coords)
    cut = box(0, -2000, 2000, 2000)
    half = ring.intersection(cut)
    if half.geom_type == "MultiLineString":
        from shapely.ops import linemerge
        half = linemerge(half)
    coords = np.array(half.coords)
    if coords[0, 1] < coords[-1, 1]:
        coords = coords[::-1]           # от спинки (y>0) к фасаду
    return LineString(coords)


def stations(curve, pitch, start=0.0, end=None):
    L = curve.length if end is None else end
    n = max(int(round((L - start) / pitch)), 1)
    out = []
    for s in np.linspace(start, L, n + 1):
        p = curve.interpolate(s)
        a = curve.interpolate(max(s - 5, 0))
        b = curve.interpolate(min(s + 5, curve.length))
        tx, ty = b.x - a.x, b.y - a.y
        ln = np.hypot(tx, ty)
        # внутренняя нормаль: кривая идёт по часовой (спинка → бок → фасад)
        nx, ny = -ty / ln, tx / ln
        if nx * (0 - p.x) + ny * (0 - p.y) < 0:
            nx, ny = -nx, -ny
        out.append(((p.x, p.y), (nx, ny), s))
    return out



# ------------------------------------------------------------------ продольное лекало (боковина)
def y_interval(region, x, y_ref=0.0):
    """Отрезок области на вертикали x, содержащий y_ref: (y_min, y_max) или None."""
    hit = LineString([(x, -1500), (x, 1500)]).intersection(region)
    for g in getattr(hit, "geoms", [hit]):
        if g.is_empty or g.geom_type != "LineString":
            continue
        ys = [c[1] for c in g.coords]
        if min(ys) <= y_ref <= max(ys):
            return min(ys), max(ys)
    return None


def side_rows(faces, z_lo, z_hi, step=5.0):
    """Контур продольного лекала: для каждой высоты — (z, y_перед, y_зад), где все
    контрольные линии x (обе пласти и середина) лежат внутри обивки с отступом r(z)."""
    rows = []
    for z in np.unique(np.append(np.arange(z_lo, z_hi, step), z_hi)):
        f, b = -1e9, 1e9
        for x, r in faces:
            iv = y_interval(plan_env(z, round(r(z))), x)
            if iv is None:
                f = None
                break
            f, b = max(f, iv[0]), min(b, iv[1])
        if f is not None and b - f > 30:
            rows.append((float(z), f, b))
    return rows


def rows_polygon(rows, y_ref):
    """(z, y_перед, y_зад) → полигон в координатах лекала (u = y_ref − y, z)."""
    front = close_profile([(y_ref - f, z) for z, f, b in rows])
    back = [(-u, z) for u, z in close_profile([(-(y_ref - b), z) for z, f, b in rows])]
    return smooth(largest(Polygon(front + back[::-1]).buffer(0)), 3)


def windows(shape, busy, web=P.SIDE_WEB, max_w=170, r=20, min_area=5000):
    """Облегчающие окна: свободная зона лекала (перемычки ≥ web по контуру и вокруг
    занятых зон), разбитая вертикальными перемычками на окна шириной ≤ max_w."""
    free = shape.buffer(-web).difference(busy.buffer(web / 2))
    out = []
    for g in getattr(free, "geoms", [free]):
        if g.is_empty:
            continue
        x0, z0, x1, z1 = g.bounds
        n = int(np.ceil((x1 - x0 + web) / (max_w + web)))
        if n > 1:
            w = (x1 - x0 - (n - 1) * web) / n
            for k in range(1, n):
                xc = x0 + k * w + (k - 0.5) * web
                g = g.difference(box(xc - web / 2, z0 - 1, xc + web / 2, z1 + 1))
        for h in getattr(g, "geoms", [g]):
            h = h.buffer(-r, quad_segs=8).buffer(r, quad_segs=8)
            for k in getattr(h, "geoms", [h]):
                if not k.is_empty and k.area > min_area:
                    out.append(k)
    return out


# ------------------------------------------------------------------ шипы / пазы
def tenon(u0, u1, z_edge, up, depth):
    """Шип на кромке ребра: прямоугольник по u∈[u0,u1], выступ depth вверх/вниз."""
    if up:
        return box(u0, z_edge - 2, u1, z_edge + depth)
    return box(u0, z_edge - depth, u1, z_edge + 2)


def dogbone_slot(cx, cy, length, width, angle_deg):
    """Сквозной паз под шип с «собачьими косточками» (фреза TOOL_D)."""
    r = P.TOOL_D / 2
    L, W = length + P.FIT, width + P.FIT
    g = box(-L / 2, -W / 2, L / 2, W / 2)
    k = r / np.sqrt(2)
    for sx in (-1, 1):
        for sy in (-1, 1):
            g = g.union(Point(sx * (L / 2 - k), sy * (W / 2 - k)).buffer(r, quad_segs=6))
    g = affinity.rotate(g, angle_deg, origin=(0, 0))
    return affinity.translate(g, cx, cy)


def close_profile(pts, half=6):
    """Морфологическое закрытие кромки u(z): убирает узкие выемки (≤ 2·half шагов),
    не выдвигая кромку на гладких участках."""
    u = np.array([p[0] for p in pts], float)
    n = len(u)
    up = np.r_[np.full(2 * half, u[0]), u, np.full(2 * half, u[-1])]   # края — без «наплыва»
    m = len(up)
    mx = np.array([up[max(0, i - half):i + half + 1].max() for i in range(m)])
    cl = np.array([mx[max(0, i - half):i + half + 1].min() for i in range(m)])[2 * half:2 * half + n]
    return [(float(c), z) for c, (_, z) in zip(cl, pts)]


def smooth_down(pts, half=12):
    """Плавная кромка без выхода вперёд: минимум по окну, затем среднее по тому же окну
    (результат не больше исходного u ни в одной точке)."""
    u = np.array([p[0] for p in pts], float)
    n = len(u)
    mn = np.array([u[max(0, i - half):i + half + 1].min() for i in range(n)])
    av = np.array([mn[max(0, i - half):i + half + 1].mean() for i in range(n)])
    return [(float(a), z) for a, (_, z) in zip(av, pts)]


def front_y(region, x, y_max=0.0):
    """Самая передняя (минимальная) координата y области на вертикали x (в передней половине)."""
    hit = LineString([(x, -1500), (x, y_max)]).intersection(region)
    ys = [c[1] for g in getattr(hit, "geoms", [hit]) if not g.is_empty for c in g.coords]
    return min(ys) if ys else None


def face_y_at(rib, x):
    """y передней (обращённой к фасаду) пласти ребра на линии x = const."""
    (ox, oy), (dx, dy) = rib.origin, rib.direction
    if abs(dx) < 1e-6:
        return None
    u = (x - ox) / dx
    u0, _, u1, _ = rib.shape.bounds
    if not (u0 - 5 <= u <= u1 + 5):          # линия x = const не пересекает само ребро
        return None
    return oy + u * dy - (rib.thickness / 2) / abs(dx)


def plate_interval(plate, origin, direction, margin=T / 2 + 6):
    """Интервалы u, где паз шириной T целиком попадает в плиту (с полем 6 мм)."""
    ox, oy = origin
    dx, dy = direction
    line = LineString([(ox - 600 * dx, oy - 600 * dy), (ox + 900 * dx, oy + 900 * dy)])
    inner = plate.buffer(-margin)
    hit = line.intersection(inner)
    out = []
    for g in getattr(hit, "geoms", [hit]):
        if g.is_empty or g.geom_type != "LineString":
            continue
        us = [(x - ox) * dx + (y - oy) * dy for x, y in g.coords]
        out.append((min(us), max(us)))
    return out


def mortise_for(rib, u_mid, width):
    """Паз в горизонтальной плите под шип ребра (в мировых координатах)."""
    ox, oy = rib.origin
    dx, dy = rib.direction
    cx, cy = ox + u_mid * dx, oy + u_mid * dy
    ang = np.degrees(np.arctan2(dy, dx))
    return dogbone_slot(cx, cy, width, rib.thickness, ang)


def open_slot(origin, direction, u_from, u_to, width):
    """Открытый паз «с выходом на кромку» вдоль линии ребра: u ∈ [u_from, u_to],
    ширина width (+FIT); у закрытого конца u_to — «собачьи косточки»."""
    r = P.TOOL_D / 2
    k = r / np.sqrt(2)
    W = width + P.FIT
    u_to = u_to + P.FIT / 2
    g = box(u_from, -W / 2, u_to, W / 2)
    for sy in (-1, 1):
        g = g.union(Point(u_to - k, sy * (W / 2 - k)).buffer(r, quad_segs=6))
    (ox, oy), (dx, dy) = origin, direction
    ang = np.degrees(np.arctan2(dy, dx))
    g = affinity.rotate(g, ang, origin=(0, 0))
    return affinity.translate(g, ox, oy)


def notch(u_from, z0, z1):
    """Вырез в ребре от внутренней кромки (u ≥ u_from) на высоте плиты z0…z1 («паз в паз»)."""
    r = P.TOOL_D / 2
    k = r / np.sqrt(2)
    z0, z1 = z0 - P.FIT / 2, z1 + P.FIT / 2
    g = box(u_from, z0, u_from + 1000, z1)
    for zc in (z0 + k, z1 - k):
        g = g.union(Point(u_from + k, zc).buffer(r, quad_segs=6))
    return g


# ------------------------------------------------------------------ сборка каркаса
class Frame:
    def __init__(self):
        self.parts = []
        self.mortises = {"П1": [], "П3": [], "П4": []}
        self.side_holes = []          # пазы в боковине (локальные координаты u, z)
        self.info = {}
        self._build()

    # ---------------------------------------------------------- плиты
    def _plates(self):
        z1t = P.Z_P1 + T
        # П1 — дно: сечение у низа, отступ под завёртку ткани
        p1 = plan_env(z1t + 25, 25).intersection(S.plan(P.Z_P1 + 12).buffer(-P.BOTTOM_MARGIN))
        p1 = Polygon(largest(p1).exterior)
        self.p1 = symmetric(fair(symmetric(p1), 40, 60, 10))
        # П3 — плита уровня сиденья; по бокам упирается в боковины (x = ±X_IN)
        p3o = symmetric(fair(symmetric(largest(plate_env(P.Z_P3))), 30, 60, 10))
        front_y = min(y for x, y in p3o.exterior.coords if abs(x) < 40)
        self.front_rail_in = front_y + P.FRONT_RAIL_W
        opening = rounded_rect(-P.SEAT_OPEN_X, self.front_rail_in, P.SEAT_OPEN_X,
                               P.SEAT_OPEN_BACK, 30)
        self.p3_outer = p3o
        p3 = p3o.intersection(box(-X_IN, -2000, X_IN, 2000))
        self.p3 = largest(p3.buffer(-10, quad_segs=8).buffer(10, quad_segs=8)).difference(opening)
        # П4 — верхняя обвязка (П-образная): наружная кромка — чистовой контур, внутренняя — полость
        zt = P.Z_P4 + T
        p4o = symmetric(fair(symmetric(largest(plate_env(P.Z_P4))), 20, 8, 6))
        self.p4 = largest(p4o.difference(cavity(zt)))

    # ---------------------------------------------------------- боковина
    def _side(self):
        """Боковина: одно продольное лекало посередине толщины подлокотника.
        Контур — сечение кресла плоскостью x = SIDE_X, сжатое на толщину мягких слоёв
        (у скругления низа — меньше: там поролон заворачивается под дно)."""
        def r(z):
            t = float(np.clip((z - 90) / 60, 0, 1))
            return P.SIDE_BOTTOM_R + (P.OUT_OFFSET - P.SIDE_BOTTOM_R) * t
        faces = [(X_IN, r), (P.SIDE_X, r), (X_OUT, r)]
        z4, z4t = P.Z_P4, P.Z_P4 + T
        rows = side_rows(faces, P.Z_P1 + T, z4t + 40)
        y_ref = float(np.ceil(max(b for z, f, b in rows) / 5) * 5)
        prof = fair(rows_polygon(rows, y_ref), P.SIDE_FAIR_R, 45, 10)
        prof = fair(prof.convex_hull, 0, 40, 12)   # «яйцо»: выпуклый плавный контур без S-изгибов
        prof = prof.intersection(box(-100, 0, 2000, z4t))          # верх над подлокотником — ровный
        prof = largest(prof.buffer(-12, quad_segs=12).buffer(12, quad_segs=12))
        rows = [r for r in rows if r[0] <= z4t]
        # над подлокотником верх боковины — на уровне верха П4 (П4 там уже 30 мм — не нужна);
        # сзади П4 ложится на уступ боковины длиной P4_LAP (клей + 2 самореза + шкант)
        b4 = max(b for z, f, b in rows if z4 <= z <= z4t)
        self.y4j = b4 - P.P4_LAP
        uj = y_ref - self.y4j
        k = P.TOOL_D / 2 / np.sqrt(2)
        step = box(-100, z4 - P.FIT / 2, uj, 900).union(
            Point(uj - k, z4 + k).buffer(P.TOOL_D / 2, quad_segs=6))
        self.side_nostep = prof
        prof = largest(prof.difference(step))
        self.side = Part("Б", "Боковина (лекало подлокотника и стенка короба)", prof, "rib",
                         qty=2, thickness=P.SIDE_T, material=f"Фанера берёзовая ФК {P.SIDE_T} мм",
                         origin=(P.SIDE_X, y_ref), direction=(0.0, -1.0),
                         note="пара (зеркально не отличаются); контур — сечение кресла по оси "
                              "подлокотника; поролон с обеих сторон")
        # ряды по чистовому контуру (для поролона и 3D)
        clean = []
        for z, _, _ in rows:
            hit = LineString([(-100, z), (2000, z)]).intersection(prof)
            us = [c[0] for g in getattr(hit, "geoms", [hit]) if not g.is_empty for c in g.coords]
            if us:
                clean.append((z, y_ref - max(us), y_ref - min(us)))
        rows = clean
        self.side_rows = rows
        self.side_y_ref = y_ref
        zt = P.Z_P3 + T
        self.arm_front_y = min(f for z, f, b in rows if z >= zt)
        self.side_front = [(f, z) for z, f, b in rows]
        self.side_back = [(b, z) for z, f, b in rows]
        y0, y1 = min(f for z, f, b in rows), max(b for z, f, b in rows)
        # зона боковины и путь её установки (сбоку, вдоль −x): здесь не должно быть рёбер
        self.side_zone = box(X_IN - 4, y0 - 4, 2000, y1 + 4)

    def side_u(self, y):
        return self.side_y_ref - y

    def side_has(self, y0, y1, z0, z1, margin=8):
        """Боковина сплошная в прямоугольнике y0…y1 × z0…z1 (+ поле)."""
        u0, u1 = sorted((self.side_u(y0), self.side_u(y1)))
        return self.side.shape.contains(box(u0 - margin, z0 - margin, u1 + margin, z1 + margin))

    # ---------------------------------------------------------- перегородки короба
    def _partitions(self):
        z0, z1 = P.Z_P1 + T, P.Z_P3
        yf = self.front_rail_in - T / 2 - 6       # ось передней
        yb = P.BACK_PART_Y + T / 2                # ось задней
        self.part_axes = dict(yf=yf, yb=yb)
        L = 2 * X_IN
        parts = []
        for code, name, y, ztop, top_tenons, note in (
                ("ПГ1", "Перегородка передняя", yf, z1, True, "сквозные шипы в боковины"),
                ("ПГ2", "Перегородка задняя (опора ремней сиденья)", yb, P.Z_SEAT_BACK, False,
                 "сквозные шипы в боковины; верхнюю кромку скруглить R5 — по ней идут ремни")):
            # концы у скругления низа корпуса — по сечению модели (дно не учитывается)
            sec = pick(plane_section((-X_IN, y), (1, 0)), (X_IN, 200))
            a, _, b, _ = sec.intersection(box(-2000, z0, 2000, z0 + 1)).bounds
            sec = sec.union(box(a, -500, b, z0 + 1))
            env = fair(sec.buffer(-P.SIDE_BOTTOM_R, quad_segs=8), 20, 30, 6)
            prof = largest(box(0, z0, L, ztop).intersection(env))
            prof = largest(prof.intersection(affinity.scale(prof, -1, 1, origin=(L / 2, 0))))
            prof = largest(prof.buffer(-6, quad_segs=8).buffer(6, quad_segs=8))
            # шипы вниз в П1 и вверх в П3
            for u0 in (L * 0.25 - TENW / 2, L * 0.75 - TENW / 2):
                prof = prof.union(tenon(u0, u0 + TENW, z0, False, T))
                if top_tenons:
                    prof = prof.union(tenon(u0, u0 + TENW, z1, True, T / 2))
            # сквозные шипы в боковины: два на конец, как можно дальше друг от друга
            ok = [zc for zc in np.arange(z0 + 40, ztop - TENW / 2 - 10, 5.0)
                  if prof.contains(box(L - 30, zc - TENW / 2 - 6, L - 1, zc + TENW / 2 + 6))
                  and self.side_has(y - T / 2, y + T / 2, zc - TENW / 2, zc + TENW / 2)]
            zcs = [ok[0], ok[-1]] if ok[-1] - ok[0] > 2 * TENW else [ok[len(ok) // 2]]
            for zc in zcs:
                prof = prof.union(box(-P.SIDE_T, zc - TENW / 2, 0.01, zc + TENW / 2))
                prof = prof.union(box(L - 0.01, zc - TENW / 2, L + P.SIDE_T, zc + TENW / 2))
                self.side_holes.append(dogbone_slot(self.side_u(y), zc, TENW, T, 90))
            parts.append(Part(code, name, prof, "rib", origin=(-X_IN, y), direction=(1, 0),
                              note=note))
        # облегчающие окна: два одинаковых, симметрично, поле 45 мм по контуру
        for p in parts:
            body = p.shape.intersection(box(0, z0, L, z1))
            inner = body.buffer(-45)
            top = min(body.bounds[3], P.Z_SEAT_BACK) - 45
            for shrink in range(0, 200, 5):
                a0, a1 = 45 + shrink, L / 2 - 22.5
                win = rounded_rect(a0, z0 + 45, a1, top, 25)
                if inner.contains(win):
                    break
            for w in (win, affinity.scale(win, -1, 1, origin=(L / 2, 0))):
                p.shape = p.shape.difference(w)
        self.partitions = parts
        for p in parts:
            self._add_mortises(p, p.shape, plates=("П1", "П3"))
        # короб сиденья: рёбра не заходят внутрь
        self.part_block = box(-X_IN, yf - T / 2, X_IN, yb + T / 2)

    def _add_mortises(self, rib, prof, plates=("П1", "П3", "П4")):
        """Найти шипы ребра (выступы за z0/z1) и добавить пазы в плиты."""
        levels = {"П1": (P.Z_P1, P.Z_P1 + T), "П3": (P.Z_P3, P.Z_P3 + T),
                  "П4": (P.Z_P4, P.Z_P4 + T)}
        for plate in plates:
            za, zb = levels[plate]
            band = prof.intersection(box(-5000, za + 0.5, 5000, zb - 0.5))
            for g in getattr(band, "geoms", [band]):
                if g.is_empty or g.area < 20:
                    continue
                u0, _, u1, _ = g.bounds
                self.mortises[plate].append(mortise_for(rib, (u0 + u1) / 2, u1 - u0))

    # ---------------------------------------------------------- рёбра
    def _rib_profile(self, origin, direction, zlo, zhi, u_inner_pts, offset=P.OUT_OFFSET,
                     base_zone=None):
        sec = plane_section(origin, direction)
        reg = pick(sec, (60, (zlo + zhi) / 2))
        env = fair(reg.buffer(-offset, quad_segs=8), 20, 25, 6)
        if base_zone is not None:
            env = env.union(base_zone)
        inner = Polygon([(-500, zlo - 1), *u_inner_pts, (-500, zhi + 1)])
        prof = largest(env.intersection(inner).intersection(box(-500, zlo, 2000, zhi)))
        prof = largest(prof.buffer(12, quad_segs=12).buffer(-12, quad_segs=12))   # плавные впадины
        prof = prof.intersection(inner).intersection(box(-500, zlo, 2000, zhi))
        return largest(largest(prof).buffer(-8, quad_segs=8).buffer(8, quad_segs=8))

    def _low_depth(self, q, n, dmax=P.RIB_DEPTH_LOW):
        """Глубина ребра в нижнем коробе: не дальше перегородок; зона опоры на П1."""
        zlo, zhi = P.Z_P1 + T, P.Z_P3
        ray = LineString([q, (q[0] + 400 * n[0], q[1] + 400 * n[1])])
        depth = dmax
        hit = ray.intersection(self.part_block.buffer(0.5))
        if not hit.is_empty:
            depth = min(depth, Point(q).distance(hit) - 0.5)
        base, u1, c = None, None, 0
        hit1 = ray.intersection(self.p1)
        if not hit1.is_empty:
            u1 = Point(q).distance(hit1) + 3
            if u1 < depth - 25:
                c = min(22, depth - u1 - 12)   # скругление у скругления низа корпуса
                base = unary_union([box(u1 + c, zlo, depth, zhi), box(u1, zlo + c, depth, zhi),
                                    Point(u1 + c, zlo + c).buffer(c, quad_segs=12)])
            else:
                u1 = None
        return depth, base, u1, c

    def _cavity_depth(self, q, n, z):
        cav = cavity(z, extra_back=back_gap(z))
        ray = LineString([q, (q[0] + 600 * n[0], q[1] + 600 * n[1])])
        hit = ray.intersection(cav.boundary)
        u = min(Point(q).distance(h) for h in getattr(hit, "geoms", [hit])) \
            if not hit.is_empty else P.RIB_DEPTH_UP
        return min(u, P.RIB_DEPTH_UP)

    def _ribs(self):
        """Рёбра по периметру (шаг RIB_PITCH): сзади — РС на всю высоту, спереди — РН
        под сиденьем. В зоне боковины рёбер нет."""
        z1t, z3, z3t, z4 = P.Z_P1 + T, P.Z_P3, P.Z_P3 + T, P.Z_P4
        wall, front = [], []
        for q, n, s in stations(self.station_curve, P.RIB_PITCH):
            foot = LineString([q, (q[0] + P.RIB_DEPTH_LOW * n[0], q[1] + P.RIB_DEPTH_LOW * n[1])])
            if foot.buffer(P.PLY_RIB / 2 + 2).intersects(self.side_zone):
                continue
            depth, base, u1, c = self._low_depth(q, n, P.RIB_DEPTH_WALL if q[1] > 0
                                                 else P.RIB_DEPTH_LOW)
            if depth < 30:
                continue
            center = abs(q[0]) < 1
            if q[1] > 0:
                # ---- ребро спинки на всю высоту
                inner = [(depth, z1t - 1), (depth, z3)]
                inner += [(self._cavity_depth(q, n, z), z) for z in np.linspace(z3t, z4, 8)]
                inner += [(inner[-1][0], z4 + 1)]
                prof = self._rib_profile(q, n, z1t, z4, inner, base_zone=base)
                # «паз в паз» с П3: ребро сохраняет наружную часть до u = a
                u_in = min(depth, inner[2][0])
                a = float(np.clip(0.5 * u_in, 38, 55))
                prof = largest(prof.difference(notch(a, z3, z3t)))
                sides = [(q, n)] if center else [(q, n), ((-q[0], q[1]), (-n[0], n[1]))]
                for qq, nn in sides:
                    self.mortises["П3"].append(open_slot(qq, nn, -60, a, P.PLY_RIB))
                # шип-лапа вниз в открытый паз П1 (ребро заводится снаружи, по радиусу)
                if u1 is not None:
                    ta = u1 + c + 4
                    tb = min(ta + TENW, depth - 8)
                    if tb - ta >= 20:
                        prof = prof.union(tenon(ta, tb, z1t, False, T))
                        for qq, nn in sides:
                            self.mortises["П1"].append(open_slot(qq, nn, u1 - 40, tb, P.PLY_RIB))
                # шип вверх в П4
                prof = self._add_rib_tenons(prof, z1t, z4, 0, T, top_pos=0.5, origin=q,
                                            direction=n, top_plate=self.p4)
                k = len(wall) + 1
                wall.append(Part(f"РС{k}", "Ребро спинки (лекало на всю высоту)", prof, "rib",
                                 **RIB_KW, qty=1 if center else 2, origin=q, direction=n,
                                 note="лекало по сечению модели; «паз в паз» с П3, лапа в "
                                      "открытый паз П1, шип в П4" + ("" if center else "; пара")))
            else:
                # ---- нижнее ребро фасада (под сиденьем)
                prof = self._rib_profile(q, n, z1t, z3, [(depth, z1t - 1), (depth, z3 + 1)],
                                         base_zone=base)
                if prof.is_empty or prof.area < 3000:
                    continue
                prof = self._add_rib_tenons(prof, z1t, z3, bottom_depth=T if base else 0,
                                            top_depth=T / 2, top_pos=0.8, origin=q, direction=n,
                                            bottom_plate=self.p1, top_plate=self.p3)
                k = len(front) + 1
                front.append(Part(f"РН{k}", "Ребро фасада (нижний короб)", prof, "rib", **RIB_KW,
                                  qty=1 if center else 2, origin=q, direction=n,
                                  note="лекало по сечению модели" + ("" if center else "; пара")))
        self.wall_ribs, self.front_ribs = wall, front
        for r in wall + front:
            for sx in ((1,) if r.qty == 1 else (1, -1)):
                q = (sx * r.origin[0], r.origin[1])
                d = (sx * r.direction[0], r.direction[1])
                rr = Part(r.code, "", r.shape, "rib", origin=q, direction=d, thickness=r.thickness)
                self._add_mortises(rr, r.shape, plates=("П4",) if r.code.startswith("РС") else ("П1", "П3"))

    # ---------------------------------------------------------- соединения боковины
    def _side_joints(self):
        side = self.side
        z3, z3t = P.Z_P3, P.Z_P3 + T
        # П3 — шипы сквозь боковину (перёд царги, середина полки, зад)
        tabs = []
        for yc in (0.5 * (self.front_rail_in + min(y for x, y in self.p3.exterior.coords
                                                  if x > X_IN - 10)), -20.0,
                   0.5 * (P.SEAT_OPEN_BACK + max(y for x, y in self.p3.exterior.coords
                                                  if x > X_IN - 10))):
            if not self.side_has(yc - TENW / 2, yc + TENW / 2, z3, z3t, margin=6):
                continue
            tabs.append(yc)
            for sx in (-1, 1):
                x0 = X_IN - 0.01 if sx > 0 else -X_OUT
                self.p3 = self.p3.union(box(x0, yc - TENW / 2, x0 + P.SIDE_T + 0.01,
                                            yc + TENW / 2))
            self.side_holes.append(dogbone_slot(self.side_u(yc), z3 + T / 2, TENW, T, 0))
        self.p3_tabs = tabs
        # П4 — только спинка и углы: концы лежат на уступах боковин (y ≥ y4j)
        self.p4 = largest(self.p4.intersection(box(-2000, self.y4j + P.FIT / 2, 2000, 2000)))
        y_end = max(b for z, f, b in self.side_rows if z >= P.Z_P4)
        self.p4_holes = []
        for yc in (self.y4j + 25, 0.5 * (self.y4j + y_end)):
            for sx in (-1, 1):
                self.p4_holes.append((sx * P.SIDE_X, yc, 4.5))
        self.p4_holes += [(sx * P.SIDE_X, self.y4j + 0.75 * P.P4_LAP - 12, 8.0) for sx in (-1, 1)]
        holes = unary_union(self.side_holes)
        # облегчающие окна — ровная сетка 2×2: вертикальные перемычки по осям перегородок
        # ПГ1, ПГ2 и посередине, горизонтальная — по полосе П3 (все пазы лежат в перемычках);
        # наружная сторона окон повторяет контур боковины с полем SIDE_WEB, углы R25.
        # Окна выше П3 со стороны сиденья закрываются картоном («внутри закрыть картоном»).
        web, col = P.SIDE_WEB, 30.0
        uf, ub = self.side_u(self.part_axes["yf"]), self.side_u(self.part_axes["yb"])
        um = 0.5 * (uf + ub)
        field = self.side_nostep.buffer(-web, quad_segs=16)
        wins = []
        for za, zb in ((0, z3 - 24), (z3t + 24, P.Z_P4 - web)):
            for ua, ub_ in ((ub + col, um - col), (um + col, uf - col)):
                w = field.intersection(box(ua, za, ub_, zb))
                w = largest(w.buffer(-25, quad_segs=12).buffer(25, quad_segs=12)) if not w.is_empty else w
                if not w.is_empty and w.area > 8000 and not w.intersects(holes.buffer(15)):
                    wins.append(w)
        side.shape = side.shape.difference(holes)
        for w in wins:
            side.shape = side.shape.difference(w)
        self.side_windows = wins

    def _edge_tenons(self, part, z_edge, up, depth, plate, pitch=170):
        """Несколько шипов вдоль кромки z_edge продольного лекала — в пределах плиты."""
        prof = part.shape
        edge = prof.intersection(box(-3000, z_edge - 0.5, 3000, z_edge + 0.5))
        if edge.is_empty:
            return prof
        u0, _, u1, _ = edge.bounds
        ivs = plate_interval(plate, part.origin, part.direction, margin=part.thickness / 2 + 6)
        out = prof
        for c, d in ivs:
            a, b = max(u0 + 12, c), min(u1 - 12, d)
            if b - a < TENW:
                continue
            n = max(1, int((b - a) // pitch) + 1)
            for um in np.linspace(a + TENW / 2, b - TENW / 2, n):
                out = out.union(tenon(um - TENW / 2, um + TENW / 2, z_edge, up, depth))
        return out

    def _add_rib_tenons(self, prof, zlo, zhi, bottom_depth, top_depth,
                        bottom_pos=0.5, top_pos=0.5, origin=None, direction=None,
                        bottom_plate=None, top_plate=None):
        """Шипы на нижней/верхней кромке ребра.
        pos — положение в допустимом пролёте (0 — у наружной кромки, 1 — у внутренней).
        Допустимый пролёт = кромка ребра ∩ плита (с полем 6 мм вокруг паза), чтобы паз
        не выходил на край плиты."""
        out = prof
        for z_edge, depth, up, pos, plate in ((zlo, bottom_depth, False, bottom_pos, bottom_plate),
                                              (zhi, top_depth, True, top_pos, top_plate)):
            if depth <= 0:
                continue
            edge = prof.intersection(box(-1000, z_edge - 0.5, 3000, z_edge + 0.5))
            if edge.is_empty:
                continue
            u0, _, u1, _ = edge.bounds
            a, b = u0 + 8, u1 - 8
            if plate is not None and origin is not None:
                iv = plate_interval(plate, origin, direction)
                best = max(((max(a, c), min(b, d)) for c, d in iv), key=lambda t: t[1] - t[0],
                           default=(0, -1))
                a, b = best
            span = b - a
            if span < 12:
                continue
            w = min(TENW, span)
            um = a + w / 2 + (span - w) * pos
            out = out.union(tenon(um - w / 2, um + w / 2, z_edge, up, depth))
        return out

    # ---------------------------------------------------------- сборка
    def _build(self):
        self._plates()
        self.station_curve = half_curve(self.p3_outer.buffer(-2))
        self._side()
        self._partitions()
        self._ribs()
        self._side_joints()
        m1 = unary_union(self.mortises["П1"])
        m3 = unary_union(self.mortises["П3"])
        m4 = unary_union(self.mortises["П4"])
        # дно с подмеханизменной плитой
        self.parts.append(Part("П1", "Дно корпуса", largest(self.p1.difference(m1)), z0=P.Z_P1,
                               note="снизу крепится верхняя пластина механизма"))
        h = P.SWIVEL_HOLE_PITCH / 2
        swivel_holes = [(sx * h, sy * h) for sx in (-1, 1) for sy in (-1, 1)]
        a = P.SWIVEL_SIZE / 2
        swivel_mark = [[(-a, -a), (a, -a), (a, a), (-a, a), (-a, -a)]]
        self.parts[0].holes = [(x, y, P.SWIVEL_HOLE_D) for x, y in swivel_holes]
        self.parts[0].marks = swivel_mark
        board = rounded_rect(-180, -180, 180, 180, 20)
        self.parts.append(Part("П2", "Плита под механизм", board, z0=P.Z_P1 + T,
                               holes=[(x, y, 8.0) for x, y in swivel_holes],
                               marks=swivel_mark,
                               note="клей + саморезы 4×30 к П1; в отверстия Ø8 — футорки М6 "
                                    "(вкручиваются сверху до сборки короба)"))
        self.parts.append(Part("П3", "Плита уровня сиденья", largest(self.p3.difference(m3)),
                               z0=P.Z_P3, note="передняя царга и опора стенки; шипы сквозь "
                                               "боковины, пазы «в паз» под рёбра спинки"))
        self.parts.append(Part("П4", "Верхняя обвязка спинки",
                               largest(self.p4.difference(m4)), z0=P.Z_P4,
                               holes=self.p4_holes,
                               note="надевается последней на шипы РС; концы — на уступы боковин: "
                                    "клей + саморезы 4×50 (Ø4,5) + шкант 8×40 (Ø8)"))
        self.parts += [self.side] + self.partitions + self.wall_ribs + self.front_ribs
        self.ribs = self.wall_ribs + self.front_ribs


TENW = P.TENON_W
