"""Построение деталей каркаса кресла SPIN по поверхности 3D-модели.

Принцип: кромки каркаса — эквидистанта поверхности обивки внутрь на толщину
мягких слоёв. Горизонтальные плиты (П1, П3, П4) строятся по сечениям в плане,
вертикальные рёбра — по сечениям модели в плоскости каждого ребра («лекала»).
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


# ------------------------------------------------------------------ шипы / пазы
def tenon(u0, u1, z_edge, up, depth):
    """Шип на кромке ребра: прямоугольник по u∈[u0,u1], выступ depth вверх/вниз."""
    if up:
        return box(u0, z_edge - 0.01, u1, z_edge + depth)
    return box(u0, z_edge - depth, u1, z_edge + 0.01)


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
    mx = np.array([u[max(0, i - half):i + half + 1].max() for i in range(n)])
    cl = np.array([mx[max(0, i - half):i + half + 1].min() for i in range(n)])
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


# ------------------------------------------------------------------ сборка каркаса
class Frame:
    def __init__(self):
        self.parts = []
        self.mortises = {"П1": [], "П3": [], "П4": []}
        self.info = {}
        self._build()

    # ---------------------------------------------------------- плиты
    def _plates(self):
        z1t = P.Z_P1 + T
        # П1 — дно: сечение у низа, отступ под завёртку ткани
        p1 = plan_env(z1t + 25, 25).intersection(S.plan(P.Z_P1 + 12).buffer(-P.BOTTOM_MARGIN))
        p1 = Polygon(largest(p1).exterior)
        self.p1 = largest(p1.buffer(-40, quad_segs=16).buffer(40, quad_segs=16))
        # П3 — плита уровня сиденья
        # открытие R60 — скругляет углы контура (под гибкие полосы обшивки)
        p3o = largest(largest(plate_env(P.Z_P3)).buffer(-60, quad_segs=16).buffer(60, quad_segs=16))
        front_y = min(y for x, y in p3o.exterior.coords if abs(x) < 40)
        self.front_rail_in = front_y + P.FRONT_RAIL_W
        opening = rounded_rect(-P.SEAT_OPEN_X, self.front_rail_in, P.SEAT_OPEN_X,
                               P.SEAT_OPEN_BACK, 30)
        self.p3_outer = p3o
        self.p3 = p3o.difference(opening)
        # П4 — верхний шаблон (П-образный)
        zt = P.Z_P4 + T
        p4 = plate_env(P.Z_P4).difference(cavity(zt))
        p4 = smooth(largest(p4), 6)
        self.p4 = p4

    # ---------------------------------------------------------- перегородки
    def _partitions(self):
        z0, z1 = P.Z_P1 + T, P.Z_P3
        xs = P.SEAT_OPEN_X + T / 2 + 3          # ось боковых перегородок
        yf = self.front_rail_in - T / 2 - 6       # ось передней
        yb = P.BACK_PART_Y + T / 2                # ось задней
        self.part_axes = dict(xs=xs, yf=yf, yb=yb)
        L_side = (yb + T / 2) - (yf - T / 2)
        parts = []
        # боковые: вдоль Y, от передней до задней (сквозные), u — вдоль +Y
        prof = box(0, z0, L_side, z1)
        for u0 in (25, L_side / 2 - TENW / 2, L_side - 25 - TENW):
            prof = prof.union(tenon(u0, u0 + TENW, z0, False, T))
            prof = prof.union(tenon(u0, u0 + TENW, z1, True, T / 2))
        side = Part("ПГ1", "Перегородка боковая", prof, "rib", qty=2,
                    origin=(xs, yf - T / 2), direction=(0, 1),
                    note="пара; ставится по пазам в П1 и П3")
        parts.append(side)
        # передняя: вдоль X между боковыми
        L_fr = 2 * (xs - T / 2)
        prof = box(0, z0, L_fr, z1)
        for u0 in (L_fr * 0.25 - TENW / 2, L_fr * 0.75 - TENW / 2):
            prof = prof.union(tenon(u0, u0 + TENW, z0, False, T))
            prof = prof.union(tenon(u0, u0 + TENW, z1, True, T / 2))
        parts.append(Part("ПГ2", "Перегородка передняя", prof, "rib",
                          origin=(-(xs - T / 2), yf), direction=(1, 0)))
        # задняя: верх = задняя опора ремней сиденья
        prof = box(0, z0, L_fr, P.Z_SEAT_BACK)
        for u0 in (L_fr * 0.25 - TENW / 2, L_fr * 0.75 - TENW / 2):
            prof = prof.union(tenon(u0, u0 + TENW, z0, False, T))
        parts.append(Part("ПГ3", "Перегородка задняя (опора ремней сиденья)", prof, "rib",
                          origin=(-(xs - T / 2), yb), direction=(1, 0),
                          note="верхняя кромка скруглить R5 — по ней идут ремни"))
        # облегчающие окна (поле 45 мм по контуру)
        for p in parts:
            u0, z0_, u1, z1_ = p.shape.intersection(box(-1e4, z0, 1e4, z1)).bounds
            n = 2 if (u1 - u0) > 300 else 1
            w = (u1 - u0 - 45 * (n + 1)) / n
            if w > 60 and (z1_ - z0_) > 150:
                for k in range(n):
                    a = u0 + 45 + k * (w + 45)
                    win = rounded_rect(a, z0 + 45, a + w, min(z1_, P.Z_SEAT_BACK) - 45, 25)
                    p.shape = p.shape.difference(win)
        self.partitions = parts
        # пазы в П1/П3
        for p in parts:
            if p.code == "ПГ1":
                for sx in (-1, 1):
                    q = Part(p.code, p.name, p.shape, "rib", origin=(sx * xs, yf - T / 2),
                             direction=(0, 1))
                    self._add_mortises(q, p.shape)
            else:
                self._add_mortises(p, p.shape)
        # «запретные» зоны для рёбер — внешние грани перегородок
        self.part_block = unary_union([
            box(-xs - T / 2, yf - T / 2, xs + T / 2, yb + T / 2)])

    def _add_mortises(self, rib, prof):
        """Найти шипы ребра (выступы за z0/z1) и добавить пазы в плиты."""
        levels = {"П1": (P.Z_P1, P.Z_P1 + T), "П3": (P.Z_P3, P.Z_P3 + T),
                  "П4": (P.Z_P4, P.Z_P4 + T)}
        for plate, (za, zb) in levels.items():
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
        env = reg.buffer(-offset, quad_segs=8)
        if base_zone is not None:
            env = env.union(base_zone)
        inner = Polygon([(-500, zlo - 1), *u_inner_pts, (-500, zhi + 1)])
        prof = env.intersection(inner).intersection(box(-500, zlo, 2000, zhi))
        return smooth(largest(prof), 3)

    def _lower_ribs(self):
        zlo, zhi = P.Z_P1 + T, P.Z_P3
        curve = self.station_curve
        ribs = []
        blk = self.part_block
        for i, (q, n, s) in enumerate(stations(curve, P.RIB_PITCH)):
            # глубина: не дальше перегородок
            ray = LineString([q, (q[0] + 400 * n[0], q[1] + 400 * n[1])])
            depth = P.RIB_DEPTH_LOW
            hit = ray.intersection(blk.buffer(0.5))
            if not hit.is_empty:
                depth = min(depth, Point(q).distance(hit) - 0.5)
            if depth < 30:
                continue
            # часть ребра над дном П1 опускается до П1
            hit1 = ray.intersection(self.p1)
            base = None
            if not hit1.is_empty:
                u1 = Point(q).distance(hit1) + 3
                if u1 < depth - 25:
                    c = min(22, depth - u1 - 12)   # фаска у скругления низа корпуса
                    base = Polygon([(u1 + c, zlo), (depth, zlo), (depth, zhi), (u1, zhi),
                                    (u1, zlo + c)])
            prof = self._rib_profile(q, n, zlo, zhi, [(depth, zlo - 1), (depth, zhi + 1)],
                                     base_zone=base)
            if prof.is_empty or prof.area < 3000:
                continue
            prof = self._add_rib_tenons(prof, zlo, zhi, bottom_depth=T if base else 0,
                                        top_depth=T / 2, top_pos=0.8, origin=q, direction=n,
                                        bottom_plate=self.p1, top_plate=self.p3)
            code = f"РН{i + 1}"
            center = abs(q[0]) < 1
            ribs.append(Part(code, "Ребро нижнего короба", prof, "rib", **RIB_KW,
                             qty=1 if center else 2, origin=q, direction=n,
                             note="лекало по сечению модели" + ("" if center else "; пара")))
        self.lower_ribs = ribs

    def _upper_ribs(self):
        zlo, zhi = P.Z_P3 + T, P.Z_P4
        curve = self.station_curve
        # конец П-образной стенки — передний торец подлокотника (по П4)
        tip_y = min(y for x, y in self.p4.exterior.coords if x > P.ARM_SKIN_X - 1)
        self.arm_tip_y = tip_y
        pts = [curve.interpolate(s) for s in np.linspace(0, curve.length, 400)]
        end = next(s for s, p in zip(np.linspace(0, curve.length, 400), pts) if p.y < tip_y + 60)
        ribs = []
        for i, (q, n, s) in enumerate(stations(curve, P.RIB_PITCH, 0, end)):
            inner = []
            for z in np.linspace(zlo, zhi, 8):
                cav = cavity(z, extra_back=back_gap(z))
                ray = LineString([q, (q[0] + 600 * n[0], q[1] + 600 * n[1])])
                hit = ray.intersection(cav.boundary)
                u = min(Point(q).distance(h) for h in getattr(hit, "geoms", [hit])) \
                    if not hit.is_empty else P.RIB_DEPTH_UP
                inner.append((min(u, P.RIB_DEPTH_UP), z))
            inner = [(inner[0][0], zlo - 1)] + inner + [(inner[-1][0], zhi + 1)]
            prof = self._rib_profile(q, n, zlo, zhi, inner)
            if prof.is_empty or prof.area < 3000:
                continue
            prof = self._add_rib_tenons(prof, zlo, zhi, bottom_depth=T / 2, top_depth=T,
                                        bottom_pos=0.1, origin=q, direction=n,
                                        bottom_plate=self.p3, top_plate=self.p4)
            center = abs(q[0]) < 1
            ribs.append(Part(f"РВ{i + 1}", "Ребро стенки (спинка/подлокотник)", prof, "rib",
                             **RIB_KW, qty=1 if center else 2, origin=q, direction=n,
                             note="лекало по сечению модели" + ("" if center else "; пара")))
        self.upper_ribs = ribs

    # ---------------------------------------------------------- торец боковины
    def _arm_front(self):
        """Торец боковины: одно продольное лекало в плоскости x = ARM_FRONT_X на всю высоту,
        разделённое плитой П3 (как все рёбра): ТН — от низа до П3, ТП — от П3 до П4.
        Передняя кромка повторяет профиль торца подлокотника и бока корпуса по модели."""
        xc, t = P.ARM_FRONT_X, P.PLY_RIB

        def ramp(z):                     # у низа отступ меньше (скругление, ткань под дно)
            return float(np.clip((z - 90) / 60, 0, 1))

        def front_rows(zlo, zhi, y_back, offset):
            pts = []
            for z in np.unique(np.append(np.arange(zlo, zhi, 5.0), zhi)):
                env = plan_env(z, round(offset(z)))
                ys = [front_y(env, xc - t / 2), front_y(env, xc + t / 2)]
                if None in ys or y_back - max(ys) < 25:
                    continue
                pts.append((y_back - max(ys), z))
            if pts and pts[0][1] - zlo <= 20:
                pts.insert(0, (pts[0][0], zlo))
            return close_profile(pts)

        def first_rib_face(ribs):
            ys = [face_y_at(r, xc) for r in ribs if r.origin[0] > 200]
            ys = [y for y in ys if y is not None and y < 0]
            return min(ys)

        parts = []
        # верхний: от П3 до П4, задней кромкой к первому ребру стенки
        zlo, zhi = P.Z_P3 + T, P.Z_P4
        yb = first_rib_face(self.upper_ribs) - 2
        up = front_rows(zlo, zhi, yb, lambda z: P.OUT_OFFSET)
        # нижний: от П3 вниз по скруглению низа, задней кромкой к первому боковому ребру
        zlo2, zhi2 = P.Z_P1 + T, P.Z_P3
        yb2 = first_rib_face(self.lower_ribs) - 2
        lo = front_rows(zlo2, zhi2, yb2,
                        lambda z: 30 + (P.OUT_OFFSET - 30) * ramp(z))
        for code, name, pts, y_back, z0, z1, top_plate, bot_plate, bd, td in (
                ("ТН", "Торец боковины нижний", lo, yb2, zlo2, zhi2, self.p3, self.p1, T, T / 2),
                ("ТП", "Торец подлокотника", up, yb, zlo, zhi, self.p4, self.p3, T / 2, T)):
            prof = Polygon([(0, pts[0][1])] + [(max(u, 20), z) for u, z in pts] + [(0, pts[-1][1])])
            prof = smooth(largest(prof.buffer(0).intersection(box(0, z0, 400, z1))), 3)
            q, n = (xc, y_back), (0.0, -1.0)
            if prof.bounds[1] > z0 + 1:
                bd = 0                                   # низ не доходит до П1 — висит на П3
            prof = self._add_rib_tenons(prof, z0, z1, bottom_depth=bd, top_depth=td,
                                        origin=q, direction=n, bottom_plate=bot_plate,
                                        top_plate=top_plate)
            parts.append(Part(code, name, prof, "rib", qty=2, **RIB_KW, origin=q, direction=n,
                              note="пара; передняя кромка — профиль торца по модели; ТН и ТП "
                                   "в одной плоскости образуют торец боковины от низа до верха"))
        tn, tp = parts
        self.lower_ribs.append(tn)
        self.upper_ribs.append(tp)
        fronts = {z: yb - u for u, z in up}
        self.arm_front_y = min(min(fronts.values()), min(yb2 - u for u, z in lo))
        # обшивка подлокотника изнутри — фанера 4 мм, спереди по профилю торца
        xs = P.ARM_SKIN_X - P.SKIN_T / 2
        zt4 = P.Z_P4 + T
        y_rear = P.BACK_BELT_Y0 - P.CAVITY_R
        zc = sorted(fronts)
        pts, y_last = [], None
        for z in np.arange(zlo, zt4 + 0.1, 5.0):
            # у скруглённого переднего угла подлокотника изнутри допускаем 32 мм до обивки
            y = front_y(plan_env(z, 32), P.ARM_SKIN_X - P.SKIN_T)
            y = y_last if y is None else y            # у валика обшивка идёт вертикально до П4
            if y is None:
                continue
            y = max(y, fronts[min(zc, key=lambda k: abs(k - z))] - 5)   # не дальше торца ТП
            y_last = y
            pts.append((y_rear - y, z))
        pts = smooth_down(close_profile(pts))
        self.skin_front = [(y_rear - u, z) for u, z in pts]
        skin = Polygon([(0, zlo)] + pts + [(0, zt4)])
        skin = smooth(largest(skin.buffer(0).intersection(box(0, zlo, 900, zt4))), 3)
        self.skins = [Part("ОП", "Обшивка подлокотника изнутри", skin, "rib", qty=2,
                           thickness=P.SKIN_T, material=f"Фанера {P.SKIN_T} мм (или ДВП 3,2)",
                           origin=(xs, y_rear), direction=(0.0, -1.0),
                           note="пара; скобы к кромкам рёбер, П3, П4 и ТП; спереди — по профилю торца")]

    def _add_rib_tenons(self, prof, zlo, zhi, bottom_depth, top_depth,
                        bottom_pos=0.5, top_pos=0.5, origin=None, direction=None,
                        bottom_plate=None, top_plate=None):
        """Шипы на нижней/верхней кромке ребра.
        pos — положение в допустимом пролёте (0 — у наружной кромки, 1 — у внутренней).
        Допустимый пролёт = кромка ребра ∩ плита (с полем 6 мм вокруг паза), чтобы паз
        не выходил на край плиты. Нижние рёбра ставят шип в П3 ближе к середине,
        верхние — ближе к наружной кромке: пазы соосных рёбер не пересекаются."""
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
        self._partitions()
        self._lower_ribs()
        self._upper_ribs()
        self._arm_front()
        for r in self.lower_ribs + self.upper_ribs:
            for sx in ((1,) if r.qty == 1 else (1, -1)):
                q = (sx * r.origin[0], r.origin[1])
                d = (sx * r.direction[0], r.direction[1])
                self._add_mortises(Part(r.code, "", r.shape, "rib", origin=q, direction=d,
                                        thickness=r.thickness), r.shape)
        m1 = unary_union(self.mortises["П1"])
        m3 = unary_union(self.mortises["П3"])
        m4 = unary_union(self.mortises["П4"])
        # дно с подмеханизменной плитой
        self.parts.append(Part("П1", "Дно корпуса", self.p1.difference(m1), z0=P.Z_P1,
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
        self.parts.append(Part("П3", "Плита уровня сиденья", self.p3.difference(m3), z0=P.Z_P3,
                               note="передняя царга и опора стенки"))
        self.parts.append(Part("П4", "Верхний шаблон спинки и подлокотников",
                               self.p4.difference(m4), z0=P.Z_P4))
        self.parts += self.partitions + self.lower_ribs + self.upper_ribs + self.skins


TENW = P.TENON_W
