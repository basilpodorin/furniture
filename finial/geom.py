"""Геометрия наконечника (финиала) штанги изголовья.

Деталь — тело вращения вокруг оси X; на шейке 8 валиков с острыми канавками
(как на штанге), на торце резная розетка.
Система координат детали:
    X — ось наконечника; x = 0 — торец воротника, который прилегает к штанге;
        шип уходит в -X (внутрь штанги), вершина купола — в +X;
    Y, Z — радиальные; Z совпадает с осью Z станка, плоскость Z = 0 — плоскость
        разъёма при двусторонней обработке (переворот заготовки вокруг оси X).

Все размеры в миллиметрах. Все параметры собраны в `Params`.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, fields, replace
from functools import lru_cache

import numpy as np


@dataclass(frozen=True)
class Params:
    # --- сопрягаемая штанга ---
    rod_d: float = 40.0            # ширина (диаметр) штанги
    rod_hole_d: float = 16.0       # отверстие под шип в торце штанги
    rod_hole_depth: float = 30.0
    rod_hole_chamfer: float = 3.5  # фаска 45° на отверстии (под галтель шипа)

    # --- шип ---
    tenon_d: float = 15.8          # под отверстие Ø16 (зазор под клей)
    tenon_l: float = 25.0
    tenon_chamfer: float = 1.0
    tenon_fillet: float = 4.5      # галтель у основания шипа (>= радиуса фрезы)

    # --- воротник (шайба у торца штанги) ---
    collar_d: float = 58.0
    collar_l: float = 15.0
    collar_edge_r: float = 6.0

    # --- шейка ---
    neck_d: float = 26.0           # минимальный диаметр шейки
    neck_rise_r: float = 8.0       # радиус выкружки перед шляпкой

    # --- шляпка ---
    cap_d: float = 50.0
    cap_shoulder_r: float = 8.0
    cap_band: float = 5.0          # цилиндрический поясок на максимальном диаметре
    cap_end_r: float = 6.0
    length: float = 55.0           # видимая длина: от торца штанги до вершины

    # --- каннелюры на шейке ---
    reeds: int = 8                 # кратно 4: гребень в плоскости разъёма
    reed_depth: float = 2.0        # глубина канавки в самом узком месте шейки (валики как на штанге)
    reed_fade: float = 2.0         # длина выхода каннелюр у воротника и шляпки
    flute_tool_r: float = 0.5      # конусная сферическая фреза установки 4: радиус кончика
    flute_tool_angle: float = 10.0 # … и половина угла конуса, градусы
    index_block: float = 40.0      # квадратная делительная оправка (сторона и длина)
    index_pocket: float = 5.0      # глубина гнезда под оправку в ложементе

    # --- розетка на торце (вырезается в купол 3-й установкой, деталь торцом вверх) ---
    rosette: int = 1               # 0 — гладкий купол
    rosette_r: float = 20.0        # радиус резной зоны (дальше — поясок по куполу)
    rosette_depth: float = 2.2     # глубина фона от поверхности купола
    petals: int = 8
    pearls: int = 24
    pearl_d: float = 3.2
    button_d: float = 8.0          # пуговка в центре
    fixture_pitch: float = 80.0    # шаг гнёзд в кондукторе 3-й установки
    fixture_t: float = 32.0        # толщина кондуктора

    # --- обработка на ЧПУ ---
    ball_d: float = 8.0            # чистовая сферическая фреза (мин. вогнутый радиус модели должен быть больше)
    stock_t: float = 60.0          # толщина заготовки (после строжки)
    gap: float = 12.0              # зазор деталь—рамка (>= Ø фрезы + 2..4 мм)
    part_gap: float = 14.0         # зазор между двумя деталями
    frame_w: float = 25.0          # ширина рамки заготовки
    bridge_tip_d: float = 10.0     # перемычка на вершине купола
    pin_d: float = 10.0            # базовый штифт со стороны шипов
    pin2_d: float = 8.0            # второй штифт другого диаметра — защита от переворота не вокруг той оси

    def with_overrides(self, items: list[str]) -> "Params":
        kinds = {f.name: f.type for f in fields(self)}
        upd = {}
        for item in items:
            k, v = item.split("=", 1)
            if k not in kinds:
                raise SystemExit(f"неизвестный параметр: {k}")
            upd[k] = int(v) if kinds[k] in (int, "int") else float(v)
        return replace(self, **upd)


# ----------------------------------------------------------------------------
# Сегменты профиля
# ----------------------------------------------------------------------------
@dataclass(frozen=True)
class Line:
    p0: tuple[float, float]
    p1: tuple[float, float]

    def sample(self, tol: float, max_step: float | None = None) -> np.ndarray:
        n = 1
        if max_step:
            n = max(1, math.ceil(math.dist(self.p0, self.p1) / max_step))
        t = np.linspace(0.0, 1.0, n + 1)[:, None]
        return (1 - t) * np.array(self.p0) + t * np.array(self.p1)


@dataclass(frozen=True)
class Arc:
    c: tuple[float, float]
    r: float
    a0: float      # начальный угол, градусы
    sweep: float   # > 0 — против часовой стрелки

    def at(self, a_deg: float) -> tuple[float, float]:
        a = math.radians(a_deg)
        return (self.c[0] + self.r * math.cos(a), self.c[1] + self.r * math.sin(a))

    @property
    def p0(self):
        return self.at(self.a0)

    @property
    def p1(self):
        return self.at(self.a0 + self.sweep)

    @property
    def mid(self):
        return self.at(self.a0 + self.sweep / 2)

    def sample(self, tol: float, max_step: float | None = None) -> np.ndarray:
        dth = 2 * math.acos(max(-1.0, 1 - tol / self.r))
        if max_step:
            dth = min(dth, max_step / self.r)
        n = max(2, math.ceil(abs(math.radians(self.sweep)) / dth))
        a = np.radians(self.a0 + self.sweep * np.linspace(0, 1, n + 1))
        return np.c_[self.c[0] + self.r * np.cos(a), self.c[1] + self.r * np.sin(a)]


# ----------------------------------------------------------------------------
# Профиль
# ----------------------------------------------------------------------------
@dataclass
class Profile:
    segs: list
    marks: dict          # характерные точки/радиусы для чертежа
    reed_x: tuple        # (x_start, x_end) зоны каннелюр

    def sample(self, tol=0.004, max_step=None) -> np.ndarray:
        pts = [self.segs[0].sample(tol, max_step)]
        for s in self.segs[1:]:
            pts.append(s.sample(tol, max_step)[1:])
        return np.vstack(pts)


def build_profile(P: Params, bridges: bool = False) -> Profile:
    """Полупрофиль (x, r) от оси на конце шипа до оси на вершине купола.

    bridges=True — вариант для ЧПУ: шип продлён до рамки заготовки,
    на вершине купола — перемычка Ø bridge_tip_d до рамки.
    """
    rt = P.tenon_d / 2
    f = P.tenon_fillet
    Rc = P.collar_d / 2
    e = P.collar_edge_r
    face_r = Rc - e
    Lc = P.collar_l
    rn = P.neck_d / 2
    Rcv = face_r - rn                   # радиус выкружки за воротником
    if Rcv <= 0:
        raise ValueError("neck_d должен быть меньше collar_d - 2*collar_edge_r")
    xn = Lc + Rcv                       # положение минимума шейки
    Rr = P.neck_rise_r
    Cr = np.array([xn, rn + Rr])
    Rcap = P.cap_d / 2
    Rs = P.cap_shoulder_r
    ys = Rcap - Rs
    dy = ys - Cr[1]
    if (Rr + Rs) ** 2 <= dy ** 2:
        raise ValueError("не удаётся сопрячь шейку со шляпкой — проверьте cap_d/neck_d/радиусы")
    xs = xn + math.sqrt((Rr + Rs) ** 2 - dy ** 2)
    Cs = np.array([xs, ys])
    Tn = Cr + (Cs - Cr) * Rr / (Rr + Rs)               # точка касания шейка/шляпка
    a_rise = math.degrees(math.atan2(*(Cs - Cr)[::-1]))  # угол на дуге подъёма
    xe = xs + P.cap_band
    Re = P.cap_end_r
    ye = Rcap - Re
    X = P.length
    xd = ((X - Re) ** 2 - xe ** 2 - ye ** 2) / (2 * (X - Re - xe))
    Rd = X - xd
    a_t = math.degrees(math.atan2(ye, xe - xd))

    segs: list = []
    if bridges:
        xb = -P.tenon_l - P.gap
        segs += [Line((xb, 0.0), (xb, rt)), Line((xb, rt), (-f, rt))]
    else:
        c = P.tenon_chamfer
        xt = -P.tenon_l
        segs += [Line((xt, 0.0), (xt, rt - c)), Line((xt, rt - c), (xt + c, rt)),
                 Line((xt + c, rt), (-f, rt))]
    segs += [
        Arc((-f, rt + f), f, -90, 90),                    # галтель шипа
        Line((0.0, rt + f), (0.0, face_r)),               # опорный торец
        Arc((e, face_r), e, 180, -90),                    # воротник
        Line((e, Rc), (Lc - e, Rc)),
        Arc((Lc - e, face_r), e, 90, -90),
        Arc((xn, face_r), Rcv, 180, 90),                  # выкружка шейки
        Arc(tuple(Cr), Rr, -90, a_rise + 90),             # подъём шейки
        Arc(tuple(Cs), Rs, a_rise + 180, 90 - (a_rise + 180)),  # плечо шляпки
        Line((xs, Rcap), (xe, Rcap)),                     # поясок
        Arc((xe, ye), Re, 90, a_t - 90),                  # скругление торца
    ]
    if bridges:
        rb = P.bridge_tip_d / 2
        a_b = math.degrees(math.asin(rb / Rd))
        dome = Arc((xd, 0.0), Rd, a_t, a_b - a_t)
        xw = X + P.gap
        segs += [dome, Line(dome.p1, (xw, rb)), Line((xw, rb), (xw, 0.0))]
    else:
        segs += [Arc((xd, 0.0), Rd, a_t, -a_t)]             # купол

    marks = dict(
        rt=rt, face_r=face_r, Rc=Rc, e=e, Lc=Lc, rn=rn, xn=xn, Rcv=Rcv, Rr=Rr, Cr=tuple(Cr),
        Rcap=Rcap, Rs=Rs, xs=xs, Cs=tuple(Cs), Tn=tuple(Tn), xe=xe, Re=Re, ye=ye,
        xd=xd, Rd=Rd, a_t=a_t, X=X, f=f,
    )
    reed_x = (Lc + 1.0, float(Tn[0]))
    return Profile(segs, marks, reed_x)


def min_concave_radius(P: Params) -> float:
    m = build_profile(P).marks
    return min(P.tenon_fillet, m["Rcv"], m["Rr"])


# ----------------------------------------------------------------------------
# Каннелюры
# ----------------------------------------------------------------------------
def _smooth(t):
    t = np.clip(t, 0.0, 1.0)
    return t * t * t * (t * (6 * t - 15) + 10)


def reed_window(P: Params, prof: Profile, x):
    x0, x1 = prof.reed_x
    return _smooth((np.asarray(x) - x0) / P.reed_fade) * _smooth((x1 - np.asarray(x)) / P.reed_fade)


def reed_q(P: Params) -> float:
    """Относительная глубина канавки (от радиуса гребня)."""
    return P.reed_depth / (P.neck_d / 2)


@lru_cache(maxsize=None)
def _lobe(n: int, q: float):
    """Валик — дуга окружности между двумя острыми канавками (как у штанги).
    Для радиуса гребня 1: центр дуги на расстоянии a от оси, радиус дуги 1 − a;
    a подбирается так, чтобы канавка (угол ±π/n) была на радиусе 1 − q."""
    al = math.pi / n
    f = lambda a: a * math.cos(al) + math.sqrt(max((1 - a) ** 2 - (a * math.sin(al)) ** 2, 0.0))
    lo, hi = 0.0, 1 / (1 + math.sin(al)) - 1e-12
    if f(hi) > 1 - q:
        raise ValueError("reed_depth слишком велика для такого числа каннелюр")
    for _ in range(100):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if f(mid) > 1 - q else (lo, mid)
    return lo, 1 - lo


def _lobe_f(P: Params, phi):
    a, rho = _lobe(P.reeds, round(reed_q(P), 12))
    step = 2 * math.pi / P.reeds
    phi = np.asarray(phi, float)
    dl = _wrap(phi - np.round(phi / step) * step)
    s = np.sqrt(np.clip(rho ** 2 - (a * np.sin(dl)) ** 2, 1e-12, None))
    return a * np.cos(dl) + s, -a * np.sin(dl) - a * a * np.sin(dl) * np.cos(dl) / s


def reed_v(P: Params, phi):
    """Форма каннелюр: 0 на гребне, 1 в канавке. phi — угол от +Z к +Y.
    Гребни на 0°, 45°, 90° …, острые канавки на 22,5° + k·45°."""
    if P.reeds == 0:
        return np.zeros_like(np.asarray(phi, float))
    return (1 - _lobe_f(P, phi)[0]) / reed_q(P)


def reed_dv(P: Params, phi):
    if P.reeds == 0:
        return np.zeros_like(np.asarray(phi, float))
    return -_lobe_f(P, phi)[1] / reed_q(P)


def reed_d(P: Params, prof: Profile, x, R0=None):
    """Абсолютная глубина канавки в сечении x (с плавным выходом на концах)."""
    x = np.asarray(x, float)
    if not P.reeds:
        return np.zeros_like(x)
    if R0 is None:
        R0 = radius_table(prof, x)
    return reed_q(P) * R0 * reed_window(P, prof, x)


# ----------------------------------------------------------------------------
# Сетка (STL)
# ----------------------------------------------------------------------------
def profile_points(P: Params, prof: Profile, reeds: bool, tol=0.004, step=0.5):
    """Точки профиля с прогибом хорд ≤ tol; в зоне каннелюр — ещё и не реже step по x."""
    pts = prof.sample(tol=tol)
    if not (reeds and P.reeds):
        return pts
    x0, x1 = prof.reed_x
    out = [pts[0]]
    for p, q in zip(pts[:-1], pts[1:]):
        if max(p[0], q[0]) >= x0 - 1 and min(p[0], q[0]) <= x1 + 1:
            n = int(math.ceil(math.dist(p, q) / step))
            for t in np.linspace(0, 1, n + 1)[1:]:
                out.append(p + (q - p) * t)
        else:
            out.append(q)
    return np.array(out)


def revolve_mesh(P: Params, prof: Profile, n_phi: int = 240, reeds: bool = True):
    """Тело вращения профиля с каннелюрами. Возвращает (vertices, faces).
    Первая и последняя точки профиля лежат на оси — там полюса."""
    pts = profile_points(P, prof, reeds)
    assert abs(pts[0, 1]) < 1e-9 and abs(pts[-1, 1]) < 1e-9
    ring = pts[1:-1]
    phi = np.linspace(0, 2 * np.pi, n_phi, endpoint=False)
    depth = reed_d(P, prof, ring[:, 0], ring[:, 1]) if (reeds and P.reeds) else np.zeros(len(ring))
    r = ring[:, 1:2] - depth[:, None] * reed_v(P, phi)[None, :]
    X = np.repeat(ring[:, 0:1], n_phi, axis=1)
    Y = r * np.sin(phi)[None, :]
    Z = r * np.cos(phi)[None, :]
    V = np.c_[X.ravel(), Y.ravel(), Z.ravel()]
    V = np.vstack([[pts[0, 0], 0, 0], V, [pts[-1, 0], 0, 0]])
    nr = len(ring)
    idx = lambda i, j: 1 + i * n_phi + (j % n_phi)
    faces = []
    j = np.arange(n_phi)
    # полюс в начале (торец шипа, нормаль -X)
    faces.append(np.c_[np.zeros(n_phi, int), idx(0, j + 1), idx(0, j)])
    for i in range(nr - 1):
        a, b = idx(i, j), idx(i, j + 1)
        c, d = idx(i + 1, j), idx(i + 1, j + 1)
        faces.append(np.c_[a, b, d])
        faces.append(np.c_[a, d, c])
    last = len(V) - 1
    faces.append(np.c_[np.full(n_phi, last), idx(nr - 1, j), idx(nr - 1, j + 1)])
    F = np.vstack(faces)
    return V, F


def orient_outward(V, F):
    """Проверка/исправление ориентации по знаку объёма."""
    a, b, c = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
    vol = np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6
    if vol < 0:
        F = F[:, ::-1]
        vol = -vol
    return F, vol


def write_stl(path, V, F, name="finial"):
    a, b, c = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
    n = np.cross(b - a, c - a)
    ln = np.linalg.norm(n, axis=1, keepdims=True)
    n = np.divide(n, ln, out=np.zeros_like(n), where=ln > 0)
    dt = np.dtype([("n", "<f4", 3), ("a", "<f4", 3), ("b", "<f4", 3), ("c", "<f4", 3), ("attr", "<u2")])
    rec = np.zeros(len(F), dtype=dt)
    rec["n"], rec["a"], rec["b"], rec["c"] = n, a, b, c
    with open(path, "wb") as fh:
        fh.write(name.encode("ascii")[:80].ljust(80, b" "))
        fh.write(np.uint32(len(F)).tobytes())
        fh.write(rec.tobytes())


# ----------------------------------------------------------------------------
# Радиус тела вращения как функция x и карта высот (для проверок)
# ----------------------------------------------------------------------------
def radius_table(prof: Profile, x):
    """Наружный радиус тела вращения (без каннелюр) в сечениях x."""
    x = np.asarray(x, float)
    out = np.zeros_like(x)
    for s in prof.segs:
        p = s.sample(0.001, 0.05)
        if abs(p[-1, 0] - p[0, 0]) < 1e-9:
            m = np.abs(x - p[0, 0]) < 1e-9
            out[m] = np.maximum(out[m], p[:, 1].max())
            continue
        if p[-1, 0] < p[0, 0]:
            p = p[::-1]
        m = (x >= p[0, 0]) & (x <= p[-1, 0])
        out[m] = np.maximum(out[m], np.interp(x[m], p[:, 0], p[:, 1]))
    return out


def index_draft_margin(P: Params, prof: Profile, n_x=600, n_phi=4001):
    """Установка 4 (делительная оправка): сверху режется сектор ±360°/n (±45°).
    Возвращает минимальный запас (град.) между наклоном поверхности и конусом фрезы:
    > 0 — в секторе нет поднутрений и конус не цепляет стенки канавок."""
    x = np.linspace(*prof.reed_x, n_x)
    R0 = radius_table(prof, x)
    d = reed_d(P, prof, x, R0)
    lim = 2 * math.pi / P.reeds
    phi = np.linspace(-lim, lim, n_phi)
    r = R0[:, None] - d[:, None] * reed_v(P, phi)[None, :]
    dr = -d[:, None] * reed_dv(P, phi)[None, :]
    ang = np.degrees(np.abs(phi[None, :] - np.arctan(dr / r)))   # угол нормали от вертикали
    return float((90.0 - P.flute_tool_angle - ang).min())


def heightmap(P: Params, prof: Profile, xs, ys, floor, reeds=False):
    """Верхняя поверхность детали z(x, y) (ось на z = 0), вид сверху по Z.
    reeds=False — гладкая шейка (как после установок 1–2)."""
    R0 = radius_table(prof, xs)
    d = reed_d(P, prof, xs, R0) if reeds else np.zeros_like(xs)
    phi = np.linspace(-np.pi / 2, np.pi / 2, 7201)
    v = reed_v(P, phi)
    Z = np.full((len(ys), len(xs)), floor)
    step = ys[1] - ys[0]
    for i in range(len(xs)):
        if R0[i] <= 0:
            continue
        if d[i] == 0:
            m = np.abs(ys) <= R0[i]
            Z[m, i] = np.sqrt(R0[i] ** 2 - ys[m] ** 2)
            continue
        r = R0[i] - d[i] * v
        yb, zb = r * np.sin(phi), r * np.cos(phi)
        # верхняя огибающая сечения: максимум z в каждой ячейке по y
        k = np.round((yb - ys[0]) / step).astype(int)
        ok = (k >= 0) & (k < len(ys))
        col = np.full(len(ys), -np.inf)
        np.maximum.at(col, k[ok], zb[ok])
        idx = np.nonzero(np.isfinite(col))[0]
        ar = np.arange(len(ys))
        inside = (ar >= idx.min()) & (ar <= idx.max())
        col = np.interp(ar, idx, col[idx])
        Z[inside, i] = col[inside]
    return Z


def simulate_ball(Z, step, R):
    """Обработка сферической фрезой радиуса R сверху по карте высот Z."""
    return simulate_tool(Z, step, lambda d: R - np.sqrt(np.maximum(R * R - d * d, 0.0)), R)


def tapered_ball(R, half_angle_deg):
    """Профиль конусной сферической фрезы: высота поверхности над кончиком на расстоянии d от оси."""
    b = math.radians(half_angle_deg)
    d0, h0 = R * math.cos(b), R - R * math.sin(b)

    def h(d):
        d = np.asarray(d, float)
        return np.where(d <= d0, R - np.sqrt(np.maximum(R * R - d * d, 0.0)), h0 + (d - d0) / math.tan(b))
    return h


def simulate_tool(Z, step, h, rmax):
    """Обработка осесимметричной фрезой с профилем h(d) (d ≤ rmax) сверху по карте высот Z.
    Возвращает высоты фактически обработанной поверхности (без зарезов)."""
    k = int(math.ceil(rmax / step))
    offs = [(i, j) for i in range(-k, k + 1) for j in range(-k, k + 1)
            if (i * step) ** 2 + (j * step) ** 2 <= rmax * rmax]
    H, W = Z.shape
    pad = np.pad(Z, k, constant_values=-1e9)
    C = np.full_like(Z, -1e9)
    hs = [float(h(math.hypot(i * step, j * step))) for i, j in offs]
    for (i, j), hd in zip(offs, hs):
        np.maximum(C, pad[k + i:k + i + H, k + j:k + j + W] - hd, out=C)
    padc = np.pad(C, k, constant_values=1e9)
    S = np.full_like(Z, 1e9)
    for (i, j), hd in zip(offs, hs):
        np.minimum(S, padc[k + i:k + i + H, k + j:k + j + W] + hd, out=S)
    return S


# ----------------------------------------------------------------------------
# Розетка на торце
# ----------------------------------------------------------------------------
def dome_x(prof: Profile, rho):
    m = prof.marks
    return m["xd"] + np.sqrt(np.maximum(m["Rd"] ** 2 - np.asarray(rho) ** 2, 0.0))


def _wrap(a):
    return (a + np.pi) % (2 * np.pi) - np.pi


def _leaf(rho, th, n, phase, u0, u1, wmax, hmax, vein, lanceolate=False):
    """n листьев вдоль лучей θ = phase + k·2π/n с прожилкой по оси.
    Лепесток: остриё у центра, самое широкое место на 60 % длины, скруглённый кончик.
    lanceolate=True — узкий лист, заострённый с обеих сторон."""
    step = 2 * np.pi / n
    dth = _wrap(th - phase - np.round((th - phase) / step) * step)
    u, v = rho * np.cos(dth), rho * np.sin(dth)
    t = np.clip((u - u0) / (u1 - u0), 0.0, 1.0)
    if lanceolate:
        W = wmax * np.sin(np.pi * t) ** 0.7 + 1e-9
    else:
        W = wmax * np.sqrt(np.sin(np.pi * t ** 1.4)) + 1e-9
    q = np.clip(1 - (v / W) ** 2, 0.0, None)
    inside = (u > u0) & (u < u1) & (q > 0)
    h = hmax * np.sqrt(q) * (0.55 + 0.45 * np.sin(np.pi * t))
    h -= vein * np.exp(-(v / 0.8) ** 2) * np.sin(np.pi * t)
    return np.where(inside, np.maximum(h, 0.0), 0.0)


def rosette_h(P: Params, rho, th):
    """Высота рельефа над фоном (0 … rosette_depth) в полярных координатах торца.
    θ отсчитывается от оси Z детали к Y (как φ у каннелюр)."""
    rho = np.asarray(rho, float)
    th = np.asarray(th, float)
    D, R = P.rosette_depth, P.rosette_r
    h = D * _smooth((rho - (R - 1.0)) / 0.8)                        # поясок-обрамление
    rp = P.pearl_d / 2
    rho_p = R - 1.4 - rp                                            # кольцо бусин
    step = 2 * np.pi / P.pearls
    dth = _wrap(th - np.round(th / step) * step)
    d2 = rho ** 2 + rho_p ** 2 - 2 * rho * rho_p * np.cos(dth)
    h = np.maximum(h, 0.72 * D * np.sqrt(np.clip(1 - d2 / rp ** 2, 0.0, None)))
    rb = P.button_d / 2
    u0, u1 = rb + 1.1, rho_p - rp - 1.1
    h = np.maximum(h, _leaf(rho, th, P.petals, 0.0, u0, u1, 3.6, 0.86 * D, 0.32))
    h = np.maximum(h, _leaf(rho, th, P.petals, np.pi / P.petals, u0 + 0.7 * (u1 - u0), u1 + 0.4,
                            1.25, 0.55 * D, 0.15, lanceolate=True))
    h = np.maximum(h, D * np.sqrt(np.clip(1 - (rho / rb) ** 2, 0.0, None)) ** 0.8)   # пуговка
    ring = 0.4 * D * np.sqrt(np.clip(1 - ((rho - rb - 0.8) / 0.55) ** 2, 0.0, None))
    h = np.maximum(h, ring)                                          # валик вокруг пуговки
    return np.clip(h, 0.0, D)


def end_x(P: Params, prof: Profile, rho, th):
    """Поверхность торца x(ρ, θ) с розеткой (не выше исходного купола)."""
    dome = dome_x(prof, rho)
    if not P.rosette:
        return dome
    return np.minimum(dome, dome - P.rosette_depth + rosette_h(P, rho, th))


def finial_mesh(P: Params, prof: Profile, reeds=True, rosette=True, n_phi=240, k_fine=3, d_rho=0.1,
                x_min=None):
    """Готовая деталь: тело вращения с каннелюрами + розетка на торце.
    Розетка — полярная сетка (n_phi·k_fine по кругу), сшитая с телом вращения.
    x_min — отрезать всё, что левее (для файла установки 3 нужна только шляпка)."""
    if not (rosette and P.rosette):
        return revolve_mesh(P, prof, n_phi=n_phi, reeds=reeds)
    rho_a = P.rosette_r + 0.6            # стык тела вращения и розетки (поясок по куполу)
    rho_b = P.rosette_r + 0.4
    pts = profile_points(P, prof, reeds)
    m = prof.marks
    keep = ~((pts[:, 0] > m["xe"]) & (pts[:, 1] < rho_a))
    pts = np.vstack([pts[keep], [[float(dome_x(prof, rho_a)), rho_a]]])
    if x_min is not None:
        r0 = float(radius_table(prof, np.array([x_min]))[0])
        pts = np.vstack([[[x_min, 0.0], [x_min, r0]], pts[pts[:, 0] > x_min + 1e-6]])
    ring = pts[1:]
    phi = np.linspace(0, 2 * np.pi, n_phi, endpoint=False)
    depth = reed_d(P, prof, ring[:, 0], ring[:, 1]) if (reeds and P.reeds) else np.zeros(len(ring))
    r = ring[:, 1:2] - depth[:, None] * reed_v(P, phi)[None, :]
    V1 = np.c_[np.repeat(ring[:, 0], n_phi), (r * np.sin(phi)).ravel(), (r * np.cos(phi)).ravel()]
    nf = n_phi * k_fine
    th = np.linspace(0, 2 * np.pi, nf, endpoint=False)
    rhos = np.linspace(rho_b, 0, int(round(rho_b / d_rho)) + 1)[:-1]
    RR, TT = np.meshgrid(rhos, th, indexing="ij")
    XX = end_x(P, prof, RR, TT)
    V2 = np.c_[XX.ravel(), (RR * np.sin(TT)).ravel(), (RR * np.cos(TT)).ravel()]
    apex = [float(end_x(P, prof, 0.0, 0.0)), 0.0, 0.0]
    V = np.vstack([[pts[0, 0], 0, 0], V1, V2, apex])
    n1, n2 = len(ring), len(rhos)
    o2 = 1 + n1 * n_phi
    A = lambda i, j: 1 + i * n_phi + (j % n_phi)
    B = lambda i, j: o2 + i * nf + (j % nf)
    F = []
    j = np.arange(n_phi)
    F.append(np.c_[np.zeros(n_phi, int), A(0, j + 1), A(0, j)])
    for i in range(n1 - 1):
        F += [np.c_[A(i, j), A(i, j + 1), A(i + 1, j + 1)], np.c_[A(i, j), A(i + 1, j + 1), A(i + 1, j)]]
    # сшивка n_phi -> nf
    i1 = n1 - 1
    for s in range(k_fine):
        F.append(np.c_[A(i1, j), B(0, k_fine * j + s + 1), B(0, k_fine * j + s)])
    F.append(np.c_[A(i1, j), A(i1, j + 1), B(0, k_fine * (j + 1))])
    jf = np.arange(nf)
    for i in range(n2 - 1):
        F += [np.c_[B(i, jf), B(i, jf + 1), B(i + 1, jf + 1)], np.c_[B(i, jf), B(i + 1, jf + 1), B(i + 1, jf)]]
    F.append(np.c_[np.full(nf, len(V) - 1), B(n2 - 1, jf), B(n2 - 1, jf + 1)])
    return V, np.vstack(F)


def end_silhouette(P: Params, prof: Profile, zs, n_y=1201):
    """Силуэт торца на виде сбоку (вдоль Y): max по y от x(ρ, θ) для каждого z."""
    R = P.rosette_r + 0.6
    out = np.empty(len(zs))
    for i, z in enumerate(zs):
        if abs(z) >= R:
            out[i] = float(dome_x(prof, abs(z)))
            continue
        y = np.linspace(-math.sqrt(R * R - z * z), math.sqrt(R * R - z * z), n_y)
        out[i] = end_x(P, prof, np.hypot(y, z), np.arctan2(y, z)).max()
    return out


def end_heightmap(P: Params, prof: Profile, half=25.0, step=0.05):
    """Карта высот торца (вид сверху при установке 3): Z(x, y), ось детали — в центре.
    Строки — от +Y к −Y (как в изображении)."""
    g = np.arange(-half, half + 1e-9, step)
    Xg, Yg = np.meshgrid(g, g[::-1])
    rho = np.hypot(Xg, Yg)
    th = np.arctan2(Xg, Yg)
    m = prof.marks
    Z = end_x(P, prof, rho, th)
    arc = m["xe"] + np.sqrt(np.clip(m["Re"] ** 2 - (rho - m["ye"]) ** 2, 0.0, None))
    tang = m["ye"] + m["Re"] * math.sin(math.radians(m["a_t"]))
    Z = np.where(rho > tang, arc, Z)
    Z = np.where(rho > m["Rcap"], np.nan, Z)
    return g, Z


def fixture_layout(P: Params) -> dict:
    """Кондуктор установки 3: гнёзда под шипы, детали стоят торцом вверх.
    X0Y0 — середина между гнёздами, Z0 — верх кондуктора (на нём лежат опорные торцы)."""
    a = P.fixture_pitch / 2
    return dict(holes=[(-a, 0.0), (a, 0.0)], Lx=P.fixture_pitch + P.collar_d + 20,
                Ly=P.collar_d + 20, T=P.fixture_t, hole_d=P.tenon_d, hole_depth=P.tenon_l + 2,
                zone_r=P.rosette_r + 0.5)


def index_layout(P: Params) -> dict:
    """Установка 4: ложемент на 2 детали, деталь лежит, шип зажат в квадратной оправке.
    X0 — опорный торец детали, Y0 — между деталями, Z0 — верх ложемента."""
    B = P.index_block
    h = B / 2 - P.index_pocket            # высота оси над верхом ложемента
    ys = P.collar_d / 2 + 11.0
    prof = build_profile(P)
    m = prof.marks
    x_a = float(prof.reed_x[1]) - 2.0      # конец зазорного жёлоба / начало опоры шляпки
    return dict(B=B, h=h, stations=(ys, -ys), pocket=P.index_pocket,
                trough_r=m["Rc"] + 0.5, trough_x=(-1.0, x_a),
                cradle_r=m["Rcap"] + 0.15, cradle_x=(x_a, P.length + 3.0),
                x0=-B - 10.0, x1=P.length + 10.0, ly=2 * (ys + B / 2 + 20.0), t=30.0,
                chan_r=P.tenon_d / 2 - 0.1)
