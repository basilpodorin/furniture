"""Мягкие элементы: поролон (ППУ), синтепон, ремни, обшивка, спанбонд.

Толщины считаются по 3D-модели: зазор между каркасом (ремнями, обшивкой)
и поверхностью обивки минус завёртка (синтепон + ткань).
"""
from dataclasses import dataclass

import numpy as np
from shapely.geometry import LineString, Polygon, box

import params as P
from .frame import S, back_belt_y, largest, plan_env

WRAP = 10          # синтепон 200 г/м² + ткань в сжатом виде, мм

# марки ППУ (обозначение по ГОСТ 32405 / принятое у производителей: тип, плотность, жёсткость)
GRADES = {
    "EL 3542": dict(rho=35, kpa=4.2, desc="повышенной жёсткости — основа сиденья"),
    "HR 3530": dict(rho=35, kpa=3.0, desc="высокоэластичный — комфортные слои"),
    "HR 2520": dict(rho=25, kpa=2.0, desc="высокоэластичный мягкий — верх спинки"),
    "EL 2540": dict(rho=25, kpa=4.0, desc="повышенной жёсткости — стенки, валик"),
    "ST 2536": dict(rho=25, kpa=3.6, desc="стандартный — наружные стенки, скругления"),
}


@dataclass
class Foam:
    code: str
    name: str
    grade: str
    thickness: float           # толщина листа, из которого режется деталь
    pattern: Polygon           # развёртка / контур раскроя, мм
    qty: int = 1
    note: str = ""
    profile: Polygon = None    # боковой шаблон для фигурной резки (если есть)
    zone: str = ""
    volume_m3: float = 0.0     # фактический объём (для фигурных — по шаблону)

    @property
    def rho(self):
        return GRADES[self.grade]["rho"]

    @property
    def mass_kg(self):
        v = self.volume_m3 or self.pattern.area * self.thickness / 1e9
        return v * self.rho * self.qty


# ------------------------------------------------------------------ профили модели
def x0_section():
    return S.section(0, 0.0)


def vertical_cuts(region, y):
    inter = region.boundary.intersection(LineString([(y, -10), (y, 2000)]))
    return sorted(p.y for p in getattr(inter, "geoms", [inter]) if p.geom_type == "Point")


def horizontal_cuts(region, z):
    inter = region.boundary.intersection(LineString([(-2000, z), (2000, z)]))
    return sorted(p.x for p in getattr(inter, "geoms", [inter]) if p.geom_type == "Point")


class Soft:
    def __init__(self, frame):
        self.F = frame
        self.pieces = []
        self.belts = []
        self.sheet_goods = []
        self.info = {}
        self._seat()
        self._back()
        self._arms()
        self._top_roll()
        self._outer()
        self._belts()
        self._sheets()

    # ---------------------------------------------------------- сиденье
    def deck_line(self):
        """Опора сиденья в разрезе x=0: царга П3 → ремни → задняя перегородка → П3."""
        F = self.F
        zt = P.Z_P3 + P.PLY
        y_rail_front = min(y for x, y in F.p3_outer.exterior.coords if abs(x) < 40)
        front_foam = y_rail_front - 4 - 40          # наружный поролон фасада под валиком
        yb = P.BACK_PART_Y + P.PLY / 2
        return [(front_foam, zt), (F.front_rail_in, zt), (yb, P.Z_SEAT_BACK),
                (P.SEAT_OPEN_BACK, P.Z_SEAT_BACK), (P.SEAT_OPEN_BACK, zt),
                (P.BACK_BELT_Y0 - 4, zt)]

    def _seat(self):
        sec = x0_section()
        deck = self.deck_line()
        y0, y1 = deck[0][0], deck[-1][0]
        # верх: поверхность сиденья − завёртка; за стыком со спинкой — горизонталь
        y_join = 165.0
        z_under_back = 400.0 - WRAP
        above = Polygon([*deck, (y1, 800), (y0 - 60, 800), (y0 - 60, deck[0][1])])
        body = sec.buffer(-WRAP, quad_segs=8)
        prof = largest(body.intersection(above).intersection(box(y0 - 60, 0, y1, 800)))
        prof = prof.difference(box(y_join, z_under_back, y1 + 1, 900))
        prof = largest(prof.buffer(3).buffer(-3))
        self.seat_profile = prof
        half_w = P.ARM_SKIN_X - 4 - 40            # между внутренними поролонами подлокотников
        self.seat_half_w = half_w
        # С1 — основа 80 мм, параллельно опоре
        base = largest(prof.intersection(self._band_above(deck, 80)))
        comfort = largest(prof.difference(base).buffer(0))
        # С3 — завёртка валика ST 2536 20 мм: верх от y=−150, фасад до шва (z=322)
        roll_len = self._roll_length(prof, y_from=-150)
        W = 2 * half_w
        base_pattern = box(0, 0, W, y1 - y0)
        self.pieces.append(Foam(
            "С1", "Сиденье — основа", "EL 3542", 80, base_pattern, zone="сиденье",
            note="на ремни через спанбонд; задняя кромка ступенькой по шаблону",
            profile=base, volume_m3=base.area * W / 1e9))
        self.pieces.append(Foam(
            "С2", "Сиденье — комфортный слой (клин)", "HR 3530", 80,
            box(0, 0, W, comfort.bounds[2] - comfort.bounds[0]), zone="сиденье",
            note="режется из листа 80 мм по боковому шаблону (клин спереди толще); "
                 "передняя верхняя кромка — скругление",
            profile=comfort, volume_m3=comfort.area * W / 1e9))
        self.pieces.append(Foam(
            "С3", "Сиденье — завёртка валика", "ST 2536", 20, box(0, 0, W + 40, roll_len),
            zone="сиденье", note="от середины сиденья через фасад до канта (z≈320); "
                                 "формирует округлый валик"))
        self.info["seat"] = dict(front=prof.bounds[0], back=y1, width=W,
                                 t_front=self._thick_at(prof, -250),
                                 t_mid=self._thick_at(prof, 0), t_back=self._thick_at(prof, 150))

    @staticmethod
    def _band_above(deck, h):
        pts = list(deck)
        top = [(y, z + h) for y, z in reversed(pts)]
        return Polygon(pts + top).buffer(0)

    @staticmethod
    def _thick_at(prof, y):
        c = vertical_cuts(prof, y)
        return (c[-1] - c[0]) if len(c) >= 2 else 0.0

    @staticmethod
    def _roll_length(prof, y_from):
        """Длина завёртки валика: по верху от y_from, через фасад до опоры (z=322)."""
        zt = P.Z_P3 + P.PLY
        c = np.array([y_from, zt])
        pts = np.array([(y, z) for y, z in prof.exterior.coords
                         if y < y_from and z > zt + 2])
        if len(pts) < 2:
            return 300.0
        d = pts - c
        ang = np.arctan2(d[:, 1], d[:, 0])        # от верха (≈90°) к фасаду (≈180°)
        top_edge = d[:, 1] > 0
        pts = pts[top_edge][np.argsort(ang[top_edge])]
        return float(LineString(pts).length) + 40

    # ---------------------------------------------------------- спинка
    def _back(self):
        sec = x0_section()
        z0, z1 = 400.0, P.Z_P4 + P.PLY
        rows = []
        z0 = 440.0                     # ниже — стык с сиденьем (спинка лежит на С1/С2)
        for z in np.arange(z0, z1 + 1, 10):
            ys = horizontal_cuts(sec, z)
            inner = [y for y in ys if 100 < y < 330]
            if not inner:
                continue
            t = back_belt_y(z) - 2 - inner[0] - WRAP
            rows.append((z, t))
        rows = np.array(rows)
        self.back_rows = rows
        t_max, t_min = rows[:, 1].max(), rows[:, 1].min()
        # развёртка: ширина по линии ремней (углы R) × наклонная высота
        from .geom import rounded_rect
        cav = rounded_rect(-P.ARM_SKIN_X, -2000, P.ARM_SKIN_X, back_belt_y(500), P.CAVITY_R)
        ring = LineString(cav.exterior.coords).intersection(box(-2000, back_belt_y(500) - P.CAVITY_R - 30, 2000, 2000))
        width = ring.length if ring.geom_type == "LineString" else sum(g.length for g in ring.geoms)
        zb = 400.0                     # низ спинки опирается на сиденье
        dy = back_belt_y(z1) - back_belt_y(zb)
        height = float(np.hypot(z1 - zb, dy))
        self.info["back"] = dict(t_min=float(t_min), t_max=float(t_max), width=width, height=height)
        # профиль спинки в разрезе x=0 (для 3D и чертежей)
        belt = Polygon([(back_belt_y(z) - 2, z) for z in (zb, z1)] + [(-500, z1), (-500, zb)])
        bp = sec.buffer(-WRAP, quad_segs=8).intersection(belt).intersection(box(120, zb, 400, z1))
        self.back_profile = largest(bp)
        b1 = 50
        self.pieces.append(Foam(
            "Сп1", "Спинка внутренняя — основа", "HR 3530", b1, box(0, 0, width, height),
            zone="спинка", note="на ремни спинки через спанбонд, огибает задние углы"))
        prof = Polygon([(0, 0)] + [(float(t - b1), float(z - z0)) for z, t in rows] +
                       [(0, float(rows[-1, 0] - z0))]).buffer(0)
        self.pieces.append(Foam(
            "Сп2", "Спинка внутренняя — мягкий слой (профильный)", "HR 2520",
            float(max(np.ceil((t_max - b1) / 10) * 10, 20)), box(0, 0, width, height), zone="спинка",
            note=f"толщина {max(t_min - b1, 0):.0f}–{t_max - b1:.0f} мм по высоте (шаблон), "
                 "максимум в зоне поясницы", profile=prof,
            volume_m3=prof.area * width / 1e9))

    # ---------------------------------------------------------- подлокотники внутри
    def _arms(self):
        z0, z1 = P.Z_P3 + P.PLY, P.Z_P4 + P.PLY
        y_front = self.F.arm_tip_y - 40
        y_back = back_belt_y(450) - P.CAVITY_R + 20
        L, H = y_back - y_front, z1 - z0
        fs = S.section(1, 0.0)
        th = []
        for z in (450, 500, 550, 600, 628):
            xs = [x for x in horizontal_cuts(fs, z) if 150 < x < P.ARM_SKIN_X]
            if xs:
                th.append(P.ARM_SKIN_X - 4 - xs[0] - WRAP)
        self.info["arm"] = dict(t=[round(t) for t in th], length=L, height=H)
        self.pieces.append(Foam(
            "Пл1", "Подлокотник — внутренняя сторона", "HR 3530", 40, box(0, 0, L, H), qty=2,
            zone="подлокотники", note="на обшивку подлокотника; спереди заходит на торец стойки, "
                                      "верхнюю кромку снять на ус под валик"))
        # торец подлокотника (перед стойкой), от П3 до П4
        self.pieces.append(Foam(
            "Пл2", "Торец подлокотника", "ST 2536", 40, box(0, 0, 120, H), qty=2,
            zone="подлокотники", note="на переднюю грань стойки РС и концы полос; скруглить"))

    # ---------------------------------------------------------- верхний валик
    def _top_roll(self):
        z_top = P.Z_P4 + P.PLY
        lay = []
        for k, (zc, grade) in enumerate(((z_top + 25, "EL 2540"), (z_top + 70, "HR 3530"))):
            sec = S.plan(zc)
            U = largest(sec.buffer(-WRAP, quad_segs=8))
            U = largest(U.buffer(3).buffer(-3))
            lay.append(U)
            self.pieces.append(Foam(
                f"В{k + 1}", "Верхний валик — " + ("нижний слой" if k == 0 else "верхний слой"),
                grade, 50, U, zone="валик",
                note="П-образная деталь по контуру; кромки скруглить R≈40 (срезать и зашлифовать)"
                if k else "клеится на П4 и торцы стенок"))
        self.info["top"] = dict(height=727 - z_top)

    # ---------------------------------------------------------- наружные стенки
    def _outer(self):
        F = self.F
        mid = 4 + 20
        u_line = largest(plan_env(470)).convex_hull.buffer(mid)
        ring = LineString(u_line.exterior.coords)
        tip = F.arm_tip_y
        back_part = ring.intersection(box(-2000, tip, 2000, 2000))
        L_u = back_part.length if back_part.geom_type == "LineString" else \
            sum(g.length for g in back_part.geoms)
        low = largest(plan_env(200)).buffer(mid)
        L_low = LineString(low.exterior.coords).length
        front = LineString(low.exterior.coords).intersection(box(-2000, -2000, 2000, tip))
        L_front = front.length if front.geom_type == "LineString" else sum(g.length for g in front.geoms)
        # высота по профилю наружной кромки центрального ребра спинки + завёртка под дно
        back_rib = next(r for r in F.lower_ribs if abs(r.origin[0]) < 1)
        h_low = self._outer_edge_len(back_rib.shape) + 30
        h_up = P.Z_P4 + P.PLY - (P.Z_P3 + P.PLY)
        self.info["outer"] = dict(L_u=L_u, L_low=L_low, L_front=L_front, h_low=h_low, h_up=h_up)
        self.pieces.append(Foam(
            "Н1", "Наружная стенка: спинка + боковины (половина)", "ST 2536", 40,
            box(0, 0, L_u / 2 + 20, h_low + h_up), qty=2, zone="наружные стенки",
            note="от торца подлокотника до шва по центру спинки; снизу заворачивается под дно "
                 "на 30 мм; одна цельная полоса по высоте"))
        self.pieces.append(Foam(
            "Н2", "Наружная стенка: фасад под сиденьем", "ST 2536", 40,
            box(0, 0, L_front + 40, h_low), zone="наружные стенки",
            note="между торцами подлокотников, до канта сиденья (z≈320); снизу под дно 30 мм"))

    @staticmethod
    def _outer_edge_len(prof):
        pts = [(u, z) for u, z in prof.exterior.coords]
        u_min = min(u for u, z in pts)
        edge = sorted([(u, z) for u, z in pts if u < u_min + 60], key=lambda p: p[1])
        return float(LineString(edge).length) if len(edge) > 1 else 250.0

    # ---------------------------------------------------------- ремни
    def _belts(self):
        F = self.F
        zt = P.Z_P3 + P.PLY
        yb = P.BACK_PART_Y
        tail = 50
        # сиденье: продольные (перед → зад)
        xs = np.arange(-200, 201, 100)
        L = float(np.hypot(yb - F.front_rail_in, zt - P.Z_SEAT_BACK)) + 60
        for x in xs:
            self.belts.append(dict(zone="сиденье, продольный", x=float(x), length=L + 2 * tail,
                                   stretch=0.08))
        # поперечные — вплетаются
        Lx = 2 * P.SEAT_OPEN_X + 2 * 40
        for y in (-150, -20):
            self.belts.append(dict(zone="сиденье, поперечный", y=float(y), length=Lx + 2 * tail,
                                   stretch=0.05))
        # спинка: вертикальные по линии ремней, шаг 100
        from .geom import rounded_rect
        yb0 = P.BACK_BELT_Y0
        cav = rounded_rect(-P.ARM_SKIN_X, -2000, P.ARM_SKIN_X, yb0, P.CAVITY_R)
        ring = LineString(cav.exterior.coords).intersection(box(-2000, yb0 - P.CAVITY_R - 20, 2000, 2000))
        back_len = ring.length if ring.geom_type == "LineString" else sum(g.length for g in ring.geoms)
        n = int(back_len // 100) + 1
        H = float(np.hypot(P.Z_P4 + P.PLY - zt, P.BACK_BELT_Y1 - P.BACK_BELT_Y0))
        for k in range(n):
            self.belts.append(dict(zone="спинка, вертикальный", s=float(k * 100), length=H + 2 * 40,
                                   stretch=0.05))
        self.info["belts"] = dict(seat_long=len(xs), seat_cross=2, back=n)

    # ---------------------------------------------------------- листовые материалы
    def _sheets(self):
        area = self.surface_area()
        info = self.info
        arm_skin = (info["arm"]["length"], info["arm"]["height"])
        strips_low = 3 * info["outer"]["L_low"]
        strips_up = 4 * info["outer"]["L_u"]
        self.sheet_goods = [
            dict(name="Обшивка подлокотника изнутри", material="Фанера 4 мм (или ДВП 3,2)",
                 size=f"{arm_skin[0]:.0f}×{arm_skin[1]:.0f}", qty=2),
            dict(name="Полосы обшивки стенок, ширина 60", material="Гибкая фанера 4 мм",
                 size=f"суммарно {(strips_low + strips_up) / 1000:.1f} м.п.",
                 qty=1, note="низ — 3 ряда (z≈100/180/260), стенка — 4 ряда (z≈370/450/530/600)"),
            dict(name="Спанбонд 80 г/м² по ремням сиденья и спинки", material="Спанбонд 80",
                 size="≈0,6 м²", qty=1),
            dict(name="Пылезащитная ткань на дно (вырез 200×200 под механизм)",
                 material="Спанбонд 60", size="≈0,4 м²", qty=1),
            dict(name="Синтепон 200 г/м² — обёртка всего кресла (сиденье и спинка в 2 слоя)",
                 material="Синтепон клееный 200 г/м²", size=f"≈{area * 1.35:.1f} м²", qty=1),
        ]
        self.info["surface_m2"] = area

    @staticmethod
    def surface_area():
        V, Tt = S.V, S.T
        a = np.cross(V[Tt[:, 1]] - V[Tt[:, 0]], V[Tt[:, 2]] - V[Tt[:, 0]])
        return float(np.linalg.norm(a, axis=1).sum() / 2 / 1e6)

    # ---------------------------------------------------------- сводка по листам
    def purchase(self, sheet=(2000, 1000), waste=0.2):
        groups = {}
        for f in self.pieces:
            k = (f.grade, f.thickness)
            groups.setdefault(k, 0.0)
            groups[k] += f.pattern.area * f.qty / 1e6
        out = []
        for (g, t), a in sorted(groups.items()):
            need = a * (1 + waste)
            n = need / (sheet[0] * sheet[1] / 1e6)
            out.append(dict(grade=g, thickness=t, area=a, sheets=n))
        return out
