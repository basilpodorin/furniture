"""Экспорт в DXF: детали каркаса по отдельности, раскрой на листы, диск основания,
шаблоны поролона. Масштаб 1:1, мм. Слои:
  CUT_OUT  — наружный контур (фреза снаружи)
  CUT_IN   — внутренние вырезы и пазы (фреза внутри)
  DRILL    — сверления (окружности; диаметр = диаметр сверла)
  MARK     — разметка/гравировка 0,5 мм (положение механизма и т. п.)
  TEXT     — маркировка деталей (не резать)
"""
from pathlib import Path

import ezdxf
import numpy as np
from shapely import affinity
from shapely.geometry import Point, Polygon, box

import params as P

LAYERS = {"CUT_OUT": 7, "CUT_IN": 1, "DRILL": 3, "MARK": 5, "TEXT": 8, "SHEET": 9}


def new_doc():
    doc = ezdxf.new("R2010", setup=True)
    doc.units = ezdxf.units.MM
    for name, color in LAYERS.items():
        doc.layers.add(name, color=color)
    return doc


def add_poly(msp, poly, dx=0.0, dy=0.0):
    geoms = getattr(poly, "geoms", [poly])
    for g in geoms:
        msp.add_lwpolyline([(x + dx, y + dy) for x, y in g.exterior.coords], close=True,
                           dxfattribs={"layer": "CUT_OUT"})
        for ring in g.interiors:
            msp.add_lwpolyline([(x + dx, y + dy) for x, y in ring.coords], close=True,
                               dxfattribs={"layer": "CUT_IN"})


def part_local(part):
    """Контур детали, сдвинутый в первый квадрант; отверстия и разметка тоже."""
    x0, y0, _, _ = part.shape.bounds
    shape = affinity.translate(part.shape, -x0, -y0)
    holes = [(x - x0, y - y0, d) for x, y, d in part.holes]
    marks = [[(x - x0, y - y0) for x, y in m] for m in part.marks]
    return shape, holes, marks


def draw_part(msp, part, dx=0.0, dy=0.0, rot=False, label=True):
    shape, holes, marks = part_local(part)
    if rot:
        shape = affinity.rotate(shape, 90, origin=(0, 0))
        mnx, mny, _, _ = shape.bounds
        shape = affinity.translate(shape, -mnx, -mny)

        def tf(x, y):
            return (-y - mnx, x - mny)
        holes = [(*tf(x, y), d) for x, y, d in holes]
        marks = [[tf(x, y) for x, y in m] for m in marks]
    add_poly(msp, shape, dx, dy)
    for x, y, d in holes:
        msp.add_circle((x + dx, y + dy), d / 2, dxfattribs={"layer": "DRILL"})
    for m in marks:
        msp.add_lwpolyline([(x + dx, y + dy) for x, y in m], dxfattribs={"layer": "MARK"})
    if label:
        c = shape.representative_point()
        h = 10 if min(shape.bounds[2], shape.bounds[3]) > 60 else 6
        msp.add_text(part.code, height=h, dxfattribs={"layer": "TEXT"}).set_placement(
            (c.x + dx, c.y + dy), align=ezdxf.enums.TextEntityAlignment.MIDDLE_CENTER)
    return shape


# ------------------------------------------------------------------ раскрой (MaxRects)
class MaxRects:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.free = [(0.0, 0.0, w, h)]

    def insert(self, w, h):
        best = None
        for fx, fy, fw, fh in self.free:
            for rw, rh, rot in ((w, h, False), (h, w, True)):
                if rw <= fw + 1e-6 and rh <= fh + 1e-6:
                    score = (min(fw - rw, fh - rh), max(fw - rw, fh - rh))
                    if best is None or score < best[0]:
                        best = (score, fx, fy, rw, rh, rot)
        if best is None:
            return None
        _, x, y, rw, rh, rot = best
        self._split(x, y, rw, rh)
        return x, y, rot

    def add_free(self, rect):
        self.free.append(rect)

    def _split(self, x, y, w, h):
        out = []
        for fx, fy, fw, fh in self.free:
            if x >= fx + fw or x + w <= fx or y >= fy + fh or y + h <= fy:
                out.append((fx, fy, fw, fh))
                continue
            if x > fx:
                out.append((fx, fy, x - fx, fh))
            if x + w < fx + fw:
                out.append((x + w, fy, fx + fw - x - w, fh))
            if y > fy:
                out.append((fx, fy, fw, y - fy))
            if y + h < fy + fh:
                out.append((fx, y + h, fw, fy + fh - y - h))
        # убрать вложенные
        self.free = [a for i, a in enumerate(out) if not any(
            j != i and a[0] >= b[0] - 1e-6 and a[1] >= b[1] - 1e-6 and
            a[0] + a[2] <= b[0] + b[2] + 1e-6 and a[1] + a[3] <= b[1] + b[3] + 1e-6 and
            (a != b or j < i) for j, b in enumerate(out))]


def inner_rect(poly_hole, step=10):
    """Грубый вписанный прямоугольник в отверстие (для раскроя мелочи внутри проёма)."""
    hole = Polygon(poly_hole)
    x0, y0, x1, y1 = hole.bounds
    best = None
    for yy0 in np.arange(y0, y1, step):
        for yy1 in np.arange(yy0 + step, y1 + 1, step):
            xs = [x for x in np.arange(x0, x1, step)]
            run = []
            for x in xs:
                if hole.contains(box(x, yy0, x + step, yy1)):
                    run.append(x)
                else:
                    run = []
                if run:
                    w = run[-1] + step - run[0]
                    a = w * (yy1 - yy0)
                    if best is None or a > best[0]:
                        best = (a, (run[0], yy0, w, yy1 - yy0))
    return best[1] if best else None


def nest(parts, sheet=(1525, 1525), margin=12, gap=14):
    """Раскладка деталей по листам. Возвращает [(sheet_idx, part, x, y, rot)]."""
    items = []
    for p in parts:
        for k in range(p.qty):
            x0, y0, x1, y1 = p.shape.bounds
            items.append((p, x1 - x0, y1 - y0))
    items.sort(key=lambda t: -(t[1] * t[2]))
    sheets, placed = [], []
    W, H = sheet[0] - 2 * margin, sheet[1] - 2 * margin
    for p, w, h in items:
        done = False
        for si, mr in enumerate(sheets):
            r = mr.insert(w + gap, h + gap)
            if r:
                placed.append((si, p, r[0] + margin, r[1] + margin, r[2]))
                done = True
                break
        if not done:
            mr = MaxRects(W, H)
            sheets.append(mr)
            r = mr.insert(w + gap, h + gap)
            if r is None:
                raise ValueError(f"деталь {p.code} не помещается на лист")
            placed.append((len(sheets) - 1, p, r[0] + margin, r[1] + margin, r[2]))
        # мелочь — в проёмы крупных плит
        si, _, x, y, rot = placed[-1]
        if not rot and p.shape.interiors and w > 400:
            x0, y0, _, _ = p.shape.bounds
            for ring in p.shape.interiors:
                hole = [(a - x0 + x, b - y0 + y) for a, b in ring.coords]
                if Polygon(hole).area > 60000:
                    ir = inner_rect(hole)
                    if ir:
                        sheets[si].add_free((ir[0] + gap / 2 - margin, ir[1] + gap / 2 - margin,
                                             ir[2] - gap, ir[3] - gap))
    return placed, len(sheets)


def export_frame(frame, out: Path):
    out.mkdir(parents=True, exist_ok=True)
    (out / "parts").mkdir(exist_ok=True)
    for p in frame.parts:
        doc = new_doc()
        msp = doc.modelspace()
        draw_part(msp, p)
        x0, y0, x1, y1 = p.shape.bounds
        msp.add_text(f"{p.code} {p.name}; {p.material}; {p.qty} шт.", height=8,
                     dxfattribs={"layer": "TEXT"}).set_placement((0, -20))
        doc.saveas(out / "parts" / f"{p.code}.dxf")
    # раскрой — отдельно по толщинам фанеры
    placed_all, sheets = [], []
    for t in sorted({p.thickness for p in frame.parts}, reverse=True):
        group = [p for p in frame.parts if p.thickness == t]
        placed, n = nest(group)
        for si in range(n):
            doc = new_doc()
            msp = doc.modelspace()
            msp.add_lwpolyline([(0, 0), (1525, 0), (1525, 1525), (0, 1525)], close=True,
                               dxfattribs={"layer": "SHEET"})
            msp.add_text(f"Фанера ФК {t:.0f} мм, лист {si + 1} из {n}", height=12,
                         dxfattribs={"layer": "TEXT"}).set_placement((0, -25))
            for s_, p, x, y, rot in placed:
                if s_ == si:
                    draw_part(msp, p, x, y, rot)
            doc.saveas(out / f"raskroy_{t:.0f}mm_list_{si + 1}.dxf")
        base = len(sheets)
        placed_all += [(base + s_, p, x, y, rot) for s_, p, x, y, rot in placed]
        sheets += [t] * n
    return placed_all, sheets


def disc_shape():
    """Стальной диск основания с отверстиями."""
    r = P.DISC_D / 2
    h = P.SWIVEL_HOLE_PITCH / 2
    holes = [(sx * h, sy * h, P.SWIVEL_HOLE_D) for sx in (-1, 1) for sy in (-1, 1)]
    ra = P.SWIVEL_HOLE_PITCH / np.sqrt(2)
    holes.append((ra, 0.0, P.ACCESS_HOLE_D))
    pads = [(P.DISC_PAD_R * np.cos(a), P.DISC_PAD_R * np.sin(a))
            for a in np.radians(22.5 + 45 * np.arange(P.DISC_PADS))]
    return Point(0, 0).buffer(r, quad_segs=64), holes, pads


def export_disc(out: Path):
    circle, holes, pads = disc_shape()
    doc = new_doc()
    msp = doc.modelspace()
    msp.add_circle((0, 0), P.DISC_D / 2, dxfattribs={"layer": "CUT_OUT"})
    for x, y, d in holes:
        msp.add_circle((x, y), d / 2, dxfattribs={"layer": "CUT_IN"})
    a = P.SWIVEL_SIZE / 2
    msp.add_lwpolyline([(-a, -a), (a, -a), (a, a), (-a, a)], close=True,
                       dxfattribs={"layer": "MARK"})
    for x, y in pads:
        msp.add_circle((x, y), 15, dxfattribs={"layer": "MARK"})
    msp.add_text(f"Диск основания Ø{P.DISC_D}×{P.DISC_T}, сталь Ст3, порошковая покраска; "
                 f"отв. Ø{P.SWIVEL_HOLE_D} с зенковкой под М6 снизу; Ø{P.ACCESS_HOLE_D} — "
                 "технологическое", height=8, dxfattribs={"layer": "TEXT"}).set_placement(
        (-P.DISC_D / 2, -P.DISC_D / 2 - 25))
    out.mkdir(parents=True, exist_ok=True)
    doc.saveas(out / "disk_osnovaniya.dxf")


def export_foam(soft, out: Path):
    out.mkdir(parents=True, exist_ok=True)
    for f in soft.pieces:
        doc = new_doc()
        msp = doc.modelspace()
        g = f.pattern
        x0, y0, _, _ = g.bounds
        add_poly(msp, affinity.translate(g, -x0, -y0))
        msp.add_text(f"{f.code} {f.name}; {f.grade}, {f.thickness:.0f} мм; {f.qty} шт.", height=10,
                     dxfattribs={"layer": "TEXT"}).set_placement((0, -25))
        if f.profile is not None:
            pr = f.profile
            px0, py0, px1, py1 = pr.bounds
            dx = g.bounds[2] - x0 + 80
            add_poly(msp, affinity.translate(pr, -px0 + dx, -py0))
            msp.add_text("боковой шаблон (разрез)", height=8, dxfattribs={"layer": "TEXT"}
                         ).set_placement((dx, -25))
        doc.saveas(out / f"{f.code}.dxf")
