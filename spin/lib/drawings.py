"""Комплект чертежей А3 (PDF): общий вид, разрезы, основание, плиты, рёбра,
поролон, раскрой, спецификация, порядок сборки."""
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.backends.backend_pdf import PdfPages  # noqa: E402
from matplotlib.patches import Polygon as MPoly, Rectangle, Circle  # noqa: E402
from shapely.geometry import LineString, Polygon, box  # noqa: E402
from shapely.ops import unary_union  # noqa: E402

import params as P  # noqa: E402
from .foam import WRAP, GRADES  # noqa: E402
from .frame import S, back_belt_y  # noqa: E402

A3 = (420, 297)
MM = 1 / 25.4
INK = "#1d2126"
WOOD = "#d9b884"
WOOD_CUT = "#c49a5c"
STEEL = "#3a3f45"
BELT = "#4a5a3a"
FOAM = {"seat": "#f3d27a", "back": "#eeb3a3", "arm": "#f5e3a3", "top": "#b9cfdc",
        "outer": "#dfe3e8", "wrap": "#f4f5f7"}
SCALES = [1, 2, 2.5, 4, 5, 10, 15, 20]
TODAY = date(2026, 9, 30).strftime("%d.%m.%Y")
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 7, "hatch.linewidth": 0.4,
                     "pdf.fonttype": 42})


# ------------------------------------------------------------------ лист
class Sheet:
    def __init__(self, pdf, title, num, total, scale_note="", material=""):
        self.pdf = pdf
        self.fig = plt.figure(figsize=(A3[0] * MM, A3[1] * MM))
        ax = self.fig.add_axes([0, 0, 1, 1])
        ax.set_xlim(0, A3[0])
        ax.set_ylim(0, A3[1])
        ax.axis("off")
        self.ax = ax
        ax.add_patch(Rectangle((20, 5), 395, 287, fill=False, lw=0.9, ec=INK))
        # штамп 185×40
        x0, y0 = 230, 5
        ax.add_patch(Rectangle((x0, y0), 185, 40, fill=False, lw=0.9, ec=INK))
        for yy in (15, 25, 35):
            ax.plot([x0, x0 + 185], [y0 + yy] * 2, lw=0.4, c=INK)
        ax.plot([x0 + 120, x0 + 120], [y0, y0 + 40], lw=0.4, c=INK)
        ax.plot([x0 + 150, x0 + 150], [y0, y0 + 25], lw=0.4, c=INK)
        ax.text(x0 + 4, y0 + 37.5, "Кресло SPIN поворотное · каркас и поролон", va="center", fontsize=9,
                weight="bold")
        ax.text(x0 + 4, y0 + 30, title, va="center", fontsize=10)
        ax.text(x0 + 4, y0 + 20, material or "Фанера берёзовая ФК 18 мм; ППУ; сталь", va="center",
                fontsize=7)
        ax.text(x0 + 4, y0 + 10, f"Разработано по 3D-модели SK-00033861 · {TODAY}", va="center",
                fontsize=6.5)
        ax.text(x0 + 4, y0 + 3.5, "Размеры в мм. Контуры деталей для ЧПУ — файлы DXF (out/cnc).",
                va="center", fontsize=6)
        ax.text(x0 + 124, y0 + 30, "Масштаб", va="center", fontsize=6.5)
        ax.text(x0 + 124, y0 + 20, scale_note or "—", va="center", fontsize=8)
        ax.text(x0 + 153, y0 + 20, f"Лист {num}", va="center", fontsize=8)
        ax.text(x0 + 153, y0 + 10, f"Листов {total}", va="center", fontsize=8)

    def view(self, x, y, w, h, bounds, scale=None, title=None):
        """Вид в прямоугольнике листа (мм). Масштаб — стандартный, наибольший помещающийся."""
        bx0, by0, bx1, by1 = bounds
        bw, bh = bx1 - bx0, by1 - by0
        if scale is None:
            scale = next(k for k in SCALES if bw / k <= w and bh / k <= h)
        cx, cy = (bx0 + bx1) / 2, (by0 + by1) / 2
        ax = self.fig.add_axes([x / A3[0], y / A3[1], w / A3[0], h / A3[1]])
        ax.set_xlim(cx - w * scale / 2, cx + w * scale / 2)
        ax.set_ylim(cy - h * scale / 2, cy + h * scale / 2)
        ax.set_aspect("equal")
        ax.axis("off")
        ax._k = scale
        if title:
            self.ax.text(x + w / 2, y + h + 2.5, f"{title}  (М 1:{scale:g})", ha="center", fontsize=8.5,
                         weight="bold")
        return ax

    def text(self, x, y, s, **kw):
        self.ax.text(x, y, s, **kw)

    def save(self):
        self.pdf.savefig(self.fig)
        plt.close(self.fig)


# ------------------------------------------------------------------ примитивы
def draw_poly(ax, g, fc="none", ec=INK, lw=0.6, hatch=None, z=2, ls="-", alpha=1.0):
    for p in getattr(g, "geoms", [g]):
        if p.is_empty or p.geom_type != "Polygon":
            continue
        ax.add_patch(MPoly(np.array(p.exterior.coords), closed=True, fc=fc, ec=ec, lw=lw, hatch=hatch,
                           zorder=z, ls=ls, alpha=alpha))
        for r in p.interiors:
            ax.add_patch(MPoly(np.array(r.coords), closed=True, fc="white" if fc != "none" else "none",
                               ec=ec, lw=lw, zorder=z + 0.1, ls=ls))


def fill_region(ax, g, fc, ec=None, lw=0.3, z=1, hatch=None):
    """Заливка области с отверстиями (через path)."""
    from matplotlib.path import Path as MPath
    from matplotlib.patches import PathPatch
    for p in getattr(g, "geoms", [g]):
        if p.is_empty or p.geom_type != "Polygon":
            continue
        verts, codes = [], []
        for ring in [p.exterior, *p.interiors]:
            c = np.array(ring.coords)
            verts += c.tolist()
            codes += [MPath.MOVETO] + [MPath.LINETO] * (len(c) - 2) + [MPath.CLOSEPOLY]
        ax.add_patch(PathPatch(MPath(verts, codes), fc=fc, ec=ec or fc, lw=lw, zorder=z, hatch=hatch))


def dim(ax, p1, p2, off, text=None, fs=6.5, flip=False):
    """Линейный размер между p1 и p2 с выносом off (в мм детали)."""
    p1, p2 = np.array(p1, float), np.array(p2, float)
    d = p2 - p1
    L = np.linalg.norm(d)
    if L < 1e-6:
        return
    t = d / L
    n = np.array([-t[1], t[0]])
    a, b = p1 + n * off, p2 + n * off
    k = ax._k
    ext = 1.5 * k
    if off:
        ax.plot([p1[0], a[0] + n[0] * ext * np.sign(off)], [p1[1], a[1] + n[1] * ext * np.sign(off)],
                lw=0.3, c=INK, zorder=5, clip_on=False)
        ax.plot([p2[0], b[0] + n[0] * ext * np.sign(off)], [p2[1], b[1] + n[1] * ext * np.sign(off)],
                lw=0.3, c=INK, zorder=5, clip_on=False)
    an = ax.annotate("", a, b, arrowprops=dict(arrowstyle="<|-|>", lw=0.4, color=INK, mutation_scale=5,
                                               shrinkA=0, shrinkB=0), zorder=5, annotation_clip=False)
    an.arrow_patch.set_clip_on(False)
    ang = np.degrees(np.arctan2(t[1], t[0]))
    if ang > 90.5 or ang < -89.5:
        ang += 180
    m = (a + b) / 2 + n * np.sign(off if off else 1) * (1.2 * k) * (-1 if flip else 1)
    ax.text(m[0], m[1], text if text is not None else f"{L:.0f}", ha="center", va="center",
            rotation=ang, fontsize=fs, zorder=6, clip_on=False,
            bbox=dict(fc="white", ec="none", pad=0.3, alpha=0.9))


def label(ax, p, tp, s, fs=6.5, ha="left"):
    an = ax.annotate(s, xy=p, xytext=tp, fontsize=fs, ha=ha, va="center", zorder=8,
                     arrowprops=dict(arrowstyle="-", lw=0.35, color=INK, shrinkA=0, shrinkB=0),
                     bbox=dict(fc="white", ec="none", pad=0.4, alpha=0.95), annotation_clip=False)
    an.set_clip_on(False)
    an.arrow_patch.set_clip_on(False)
    ax.plot(*p, "o", ms=1.4, c=INK, zorder=8, clip_on=False)


def callout(ax, p, tp, num):
    """Позиция: номер в кружке с выноской."""
    an = ax.annotate(str(num), xy=p, xytext=tp, fontsize=6.3, ha="center", va="center", zorder=9,
                     arrowprops=dict(arrowstyle="-", lw=0.35, color=INK, shrinkA=4, shrinkB=0),
                     bbox=dict(boxstyle="circle,pad=0.25", fc="white", ec=INK, lw=0.5),
                     annotation_clip=False)
    an.set_clip_on(False)
    an.arrow_patch.set_clip_on(False)
    ax.plot(*p, "o", ms=1.4, c=INK, zorder=9, clip_on=False)


def level(ax, x, z, s, fs=6.5):
    k = ax._k
    ax.plot([x - 3 * k, x + 18 * k], [z, z], lw=0.3, c=INK, zorder=5, clip_on=False)
    ax.add_patch(MPoly([[x, z], [x + 1.4 * k, z + 1.6 * k], [x - 1.4 * k, z + 1.6 * k]], closed=True,
                       fc=INK, ec=INK, zorder=5, clip_on=False))
    ax.text(x + 2.5 * k, z + 0.9 * k, s, fontsize=fs, va="bottom", zorder=6, clip_on=False)


def centerline(ax, a, b):
    ax.plot([a[0], b[0]], [a[1], b[1]], lw=0.3, c="#7a8591", ls=(0, (8, 2, 1, 2)), zorder=1)


# ------------------------------------------------------------------ геометрия разрезов
def rib_world_xy(part, sx=1):
    ox, oy = part.origin
    dx, dy = part.direction
    return (sx * ox, oy), (sx * dx, dy)


def plate_cut(part, axis, value):
    """Сечение горизонтальной плиты плоскостью x=value (axis=0) или y=value (axis=1) →
    прямоугольники в координатах разреза (s, z)."""
    if axis == 0:
        line = LineString([(value, -2000), (value, 2000)])
    else:
        line = LineString([(-2000, value), (2000, value)])
    hit = line.intersection(part.shape)
    out = []
    for g in getattr(hit, "geoms", [hit]):
        if g.is_empty or g.geom_type != "LineString":
            continue
        c = np.array(g.coords)
        s = c[:, 1] if axis == 0 else c[:, 0]
        out.append(box(s.min(), part.z0, s.max(), part.z0 + part.thickness))
    return out


def rib_cut(part, axis, value, sx=1):
    """Ребро/перегородка, пересекаемые плоскостью поперёк: вертикальные полосы."""
    (ox, oy), (dx, dy) = rib_world_xy(part, sx)
    t = part.thickness
    # плоскость x=value: u = (value-ox)/dx
    if axis == 0:
        if abs(dx) < 0.5:
            return []
        u = (value - ox) / dx
        c = oy + u * dy
    else:
        if abs(dy) < 0.5:
            return []
        u = (value - oy) / dy
        c = ox + u * dx
    hit = LineString([(u, -10), (u, 2000)]).intersection(part.shape)
    out = []
    for g in getattr(hit, "geoms", [hit]):
        if g.is_empty or g.geom_type != "LineString":
            continue
        zs = np.array(g.coords)[:, 1]
        out.append(box(c - t / 2, zs.min(), c + t / 2, zs.max()))
    return out


def rib_in_plane(part, axis, value, sx=1, tol=12):
    """Профиль ребра, лежащего в плоскости разреза (или почти) → полигон (s, z)."""
    (ox, oy), (dx, dy) = rib_world_xy(part, sx)
    if axis == 0 and abs(ox - value) < tol and abs(dx) < 0.15:
        return Polygon([(oy + u * dy, z) for u, z in part.shape.exterior.coords]).buffer(0)
    if axis == 1 and abs(oy - value) < tol and abs(dy) < 0.2:
        return Polygon([(ox + u * dx, z) for u, z in part.shape.exterior.coords]).buffer(0)
    return None


# ------------------------------------------------------------------ разрезы
def section_drawing(ax, frame, soft, axis, value):
    sec = S.section(axis, value)
    inner = sec.buffer(-WRAP, quad_segs=8)
    fill_region(ax, sec.difference(inner), FOAM["wrap"], ec="#c9ced4", lw=0.2, z=0.5)
    zones = []
    # поролон
    if axis == 0:
        seat = soft.seat_profile
        back = soft.back_profile
        fill_region(ax, seat, FOAM["seat"], z=1)
        fill_region(ax, back, FOAM["back"], z=1)
        zones += [seat, back]
        # граница С1/С2 и С3
        deck = soft.deck_line()
        base_top = LineString([(y, z + 80) for y, z in deck]).intersection(seat)
        for g in getattr(base_top, "geoms", [base_top]):
            if g.geom_type == "LineString":
                ax.plot(*np.array(g.coords).T, lw=0.4, c="#8a6a1a", ls="--", zorder=3)
        roll = seat.difference(seat.buffer(-20)).intersection(box(-1000, P.Z_P3 + P.PLY + 2, -150, 1000))
        fill_region(ax, roll, "#e9b94a", z=1.2)
        sp_line = LineString([(back_belt_y(z) - 2 - 50, z) for z in (380, 700)]).intersection(back)
        if sp_line.geom_type == "LineString":
            ax.plot(*np.array(sp_line.coords).T, lw=0.4, c="#9a4a3a", ls="--", zorder=3)
    else:
        # сиденье: блок между подлокотниками
        seat_x = soft.seat_half_w
        cuts = LineString([(value, 0), (value, 2000)]).intersection(soft.seat_profile)
        zs = [np.array(g.coords)[:, 1] for g in getattr(cuts, "geoms", [cuts])
              if g.geom_type == "LineString"]
        if zs:
            zmin, zmax = min(z.min() for z in zs), max(z.max() for z in zs)
            seat = box(-seat_x, zmin, seat_x, zmax).intersection(inner)
            fill_region(ax, seat, FOAM["seat"], z=1)
            zones.append(seat)
        for sx in (-1, 1):
            a = sx * (P.ARM_SKIN_X - 4 - 40)
            b = sx * (P.ARM_SKIN_X - 4)
            arm = box(min(a, b), P.Z_P3 + P.PLY, max(a, b), P.Z_P4 + P.PLY).intersection(inner)
            fill_region(ax, arm, FOAM["arm"], z=1)
            zones.append(arm)
    # верхний валик
    for f in soft.pieces:
        if f.code in ("В1", "В2"):
            z0 = P.Z_P4 + P.PLY + (0 if f.code == "В1" else 50)
            if axis == 0:
                line = LineString([(value, -2000), (value, 2000)])
            else:
                line = LineString([(-2000, value), (2000, value)])
            hit = line.intersection(f.pattern)
            for g in getattr(hit, "geoms", [hit]):
                if g.geom_type != "LineString":
                    continue
                c = np.array(g.coords)
                s = c[:, 1] if axis == 0 else c[:, 0]
                r = box(s.min(), z0, s.max(), z0 + 50).intersection(inner)
                fill_region(ax, r, FOAM["top"], z=1)
                zones.append(r)
                ax.plot([s.min(), s.max()], [z0, z0], lw=0.3, c="#5b7a8c", zorder=3)
    # наружный поролон: полоса 40 мм у поверхности вне остальных зон
    band = inner.difference(sec.buffer(-(WRAP + 40), quad_segs=8))
    band = band.difference(unary_union([z.buffer(0.5) for z in zones]))
    band = unary_union([g for g in getattr(band, "geoms", [band]) if g.area > 800])
    fill_region(ax, band, FOAM["outer"], z=1)
    draw_poly(ax, sec, lw=0.9, z=4)
    # каркас
    cut_hatch = "////"
    for part in frame.parts:
        if part.kind == "plate":
            for r in plate_cut(part, axis, value):
                fill_region(ax, r, WOOD_CUT, ec=INK, lw=0.4, z=5, hatch=cut_hatch)
            continue
        from .export_3d import placements
        for origin, direction, _ in placements(part):
            q = part.__class__(part.code, part.name, part.shape, "rib", thickness=part.thickness,
                               origin=origin, direction=direction)
            prof = rib_in_plane(q, axis, value)
            if prof is not None and not prof.is_empty:
                fill_region(ax, prof, WOOD, ec=INK, lw=0.4, z=4.5)
                continue
            for r in rib_cut(q, axis, value):
                fill_region(ax, r, WOOD_CUT, ec=INK, lw=0.4, z=5, hatch=cut_hatch)
    # ремни
    zt = P.Z_P3 + P.PLY
    if axis == 0:
        deck = [(frame.front_rail_in - 50, zt + 1.5), (frame.front_rail_in, zt + 1.5),
                (P.BACK_PART_Y, P.Z_SEAT_BACK + 1.5), (P.BACK_PART_Y, P.Z_SEAT_BACK - 25)]
        ax.plot(*np.array(deck).T, lw=1.3, c=BELT, zorder=6, solid_capstyle="butt")
        bl = [(P.SEAT_OPEN_BACK + 8, zt + 1.5), (P.BACK_BELT_Y0, zt + 1.5),
              (P.BACK_BELT_Y1, P.Z_P4 + P.PLY + 1.5), (P.BACK_BELT_Y1 + 40, P.Z_P4 + P.PLY + 1.5)]
        ax.plot(*np.array(bl).T, lw=1.3, c=BELT, zorder=6)
    else:
        yb = frame.front_rail_in
        t = np.clip((value - yb) / (P.BACK_PART_Y - yb), 0, 1)
        zb = zt + t * (P.Z_SEAT_BACK - zt)
        for x in np.arange(-200, 201, 100):
            ax.add_patch(Rectangle((x - 25, zb), 50, 2.5, fc=BELT, ec=BELT, zorder=6))
    # основание и механизм
    r = P.DISC_D / 2
    ax.add_patch(Rectangle((-r, P.PAD_H), 2 * r, P.DISC_T, fc=STEEL, ec=INK, lw=0.4, zorder=5))
    for s in (-P.DISC_PAD_R, P.DISC_PAD_R):
        ax.add_patch(Rectangle((s - 15, 0), 30, P.PAD_H, fc="#8b8f94", ec=INK, lw=0.3, zorder=5))
    a = P.SWIVEL_SIZE / 2
    z1 = P.PAD_H + P.DISC_T
    ax.add_patch(Rectangle((-a, z1), 2 * a, 3, fc=STEEL, ec=INK, lw=0.3, zorder=5))
    ax.add_patch(Rectangle((-a, P.Z_P1 - 3), 2 * a, 3, fc=STEEL, ec=INK, lw=0.3, zorder=5))
    ax.add_patch(Rectangle((-a * 0.42, z1 + 3), a * 0.84, P.SWIVEL_H - 6, fc="#5d636a", ec=INK, lw=0.3,
                           zorder=5))
    ax.plot([-1000, 1000], [0, 0], lw=0.6, c=INK, zorder=3)
    centerline(ax, (0, -15), (0, 770))
    return sec


# ------------------------------------------------------------------ листы
def sheet_general(pdf, frame, soft, summ, n, N, img_dir):
    sh = Sheet(pdf, "Общий вид", n, N, "1:5, 1:10")
    fronts = unary_union([S.section(1, y) for y in np.arange(-395, 416, 12)])
    sides = unary_union([S.section(0, x) for x in np.arange(-395, 396, 12)])
    tops = unary_union([S.section(2, z).convex_hull for z in np.arange(40, 726, 12)])
    axf = sh.view(32, 122, 168, 152, (-410, -15, 410, 740), 5, "Вид спереди")
    axs = sh.view(224, 122, 172, 152, (-410, -15, 430, 740), 5, "Вид сбоку")
    axt = sh.view(32, 14, 88, 88, (-420, -420, 420, 440), 10, "Вид сверху")
    for ax, sil, axis in ((axf, fronts, 1), (axs, sides, 0)):
        fill_region(ax, sil, "#eef1f4", ec=INK, lw=0.9, z=1)
        ax.plot([-430, 430], [0, 0], lw=0.6, c=INK)
        r = P.DISC_D / 2
        ax.add_patch(Rectangle((-r, P.PAD_H), 2 * r, P.DISC_T, fc=STEEL, ec=INK, lw=0.3, zorder=3))
        # скрытые кромки каркаса
        for p in frame.parts:
            if p.kind == "plate":
                x0, y0, x1, y1 = p.shape.bounds
                s0, s1 = (x0, x1) if axis == 1 else (y0, y1)
                ax.add_patch(Rectangle((s0, p.z0), s1 - s0, p.thickness, fill=False, ec="#8a6a3a",
                                       lw=0.35, ls=(0, (3, 2)), zorder=2))
        centerline(ax, (0, -15), (0, 770))
    b = fronts.bounds
    dim(axf, (b[0], 0), (b[2], 0), -30, f"{b[2] - b[0]:.0f}")
    dim(axf, (b[2], 0), (b[2], b[3]), 35)
    dim(axf, (b[0], 0), (b[0], summ["seat_top"]), -35, f"{summ['seat_top']:.0f}")
    dim(axf, (-300, 0), (-300, P.Z_P1), 0, f"{P.Z_P1}")
    b = sides.bounds
    dim(axs, (b[0], 0), (b[2], 0), -30, f"{b[2] - b[0]:.0f}")
    dim(axs, (b[2], 0), (b[2], b[3]), 35)
    fill_region(axt, tops, "#eef1f4", ec=INK, lw=0.9, z=1)
    axt.add_patch(Circle((0, 0), P.DISC_D / 2, fill=False, ec=STEEL, lw=0.4, ls=(0, (3, 2))))
    centerline(axt, (-450, 0), (450, 0))
    centerline(axt, (0, -450), (0, 460))
    bt = tops.bounds
    dim(axt, (bt[0], bt[1]), (bt[2], bt[1]), -40)
    dim(axt, (bt[2], bt[1]), (bt[2], bt[3]), 40)
    dim(axt, (bt[0], 0), (0, 0), 0, "")
    axt.text(12, -30, "ось\nповорота", fontsize=6)
    img = Path(img_dir) / "obivka_iso.png"
    if img.exists():
        a = sh.fig.add_axes([132 / 420, 10 / 297, 92 / 420, 100 / 297])
        a.imshow(plt.imread(img))
        a.axis("off")
    lines = [
        "Характеристики", "",
        f"Габарит {tops.bounds[2] - tops.bounds[0]:.0f} × {tops.bounds[3] - tops.bounds[1]:.0f} × "
        f"{summ['top']:.0f} мм, по канту {fronts.bounds[3]:.0f} (каталог: 800 × 820 × 720)",
        f"Высота сиденья у фасада ≈{summ['seat_top']:.0f} мм; зазор до пола {P.Z_P1} мм",
        f"Поворот 360° на механизме {P.SWIVEL_SIZE}×{P.SWIVEL_SIZE}×{P.SWIVEL_H}",
        f"Основание — стальной диск Ø{P.DISC_D}×{P.DISC_T} на {P.DISC_PADS} накладках",
        f"Ось поворота на {abs(P.MODEL_AXIS_Y * P.MODEL_XY_SCALE):.0f} мм впереди центра габарита",
        "",
        f"Фанера {summ['mass']['ply']:.1f} кг · поролон {summ['mass']['foam']:.1f} кг · "
        f"диск {summ['mass']['steel']:.1f} кг",
        f"Масса кресла ≈{sum(summ['mass'].values()):.0f} кг (SKDESIGN: 40 кг)",
    ]
    for i, s in enumerate(lines):
        sh.text(232, 104 - i * 5.2, s, fontsize=8 if i else 9, weight="bold" if i == 0 else "normal")
    sh.save()


def sheet_sections(pdf, frame, soft, summ, n, N):
    sh = Sheet(pdf, "Разрезы А–А и Б–Б", n, N, "1:5")
    axA = sh.view(24, 116, 186, 158, (-465, -20, 465, 770), 5, "Разрез А–А (по оси кресла, x = 0)")
    section_drawing(axA, frame, soft, 0, 0.0)
    ys = next(r.origin[1] for r in frame.upper_ribs if r.origin[0] > 300 and abs(r.origin[1]) < 80)
    axB = sh.view(222, 116, 186, 158, (-465, -20, 465, 770), 5, f"Разрез Б–Б (y = {ys:.0f}, по рёбрам)")
    section_drawing(axB, frame, soft, 1, ys)
    for z, s_ in ((0, "±0"), (P.PAD_H + P.DISC_T, f"+{P.PAD_H + P.DISC_T}"), (P.Z_P1, f"+{P.Z_P1}"),
                  (P.Z_P1 + 2 * P.PLY, f"+{P.Z_P1 + 2 * P.PLY}"), (P.Z_P3, f"+{P.Z_P3}"),
                  (P.Z_P3 + P.PLY, f"+{P.Z_P3 + P.PLY}"), (round(summ["seat_top"]), f"+{summ['seat_top']:.0f}"),
                  (P.Z_P4, f"+{P.Z_P4}"), (P.Z_P4 + P.PLY, f"+{P.Z_P4 + P.PLY}"),
                  (round(summ["top"]), f"+{summ['top']:.0f}")):
        level(axA, 470, z, s_, fs=5.5)
    si = soft.info
    zt = P.Z_P3 + P.PLY
    xl, xr = -450, 455
    posA = [  # (номер, точка, сторона, высота выноски)
        (1, (-150, 350), xl, 360), (2, (-250, 445), xl, 450), (3, (-396, 380), xl, 405),
        (4, (-362, 200), xl, 215), (5, (-120, zt + 1.5), xl, 305), (6, (-236, 140), xl, 150),
        (7, (-120, 55), xl, 75), (8, (-240, 7), xl, 20), (9, (40, 22), xl, -8),
        (10, (330, 313), xr, 325), (11, (300, 190), xr, 205), (12, (408, 280), xr, 265),
        (13, (320, 480), xr, 470), (14, (220, 530), xr, 540), (15, (265, 470), xr, 415),
        (16, (300, 619), xr, 610), (17, (320, 680), xr, 690), (18, (190, 260), xr, 150),
    ]
    for num, pt, x, z in posA:
        callout(axA, pt, (x, z), num)
    dim(axA, (soft.info["seat"]["front"], 0), (P.BACK_BELT_Y0, 0), -35,
        f"поролон сиденья {P.BACK_BELT_Y0 - soft.info['seat']['front']:.0f}")
    posB = [(19, (-248, 480), xl, 520), (20, (-270, 560), xl, 600), (21, (-267, 150), xl, 170),
            (22, (-330, 150), xl, 90), (23, (340, 470), xr, 480), (24, (100, 400), xr, 380),
            (25, (395, 520), xr, 560)]
    for num, pt, x, z in posB:
        callout(axB, pt, (x, z), num)
    names = [
        "С1 — основа сиденья, EL 3542, 80 мм по опоре",
        "С2 — комфортный клин сиденья, HR 3530",
        "С3 — завёртка валика сиденья, ST 2536, 20 мм",
        "Н2 — наружная стенка фасада, ST 2536, 40 мм",
        "ремни сиденья 50 мм (5 продольных + 2 поперечных)",
        "ПГ2 — перегородка передняя",
        "П1 — дно + П2 — плита под механизм (футорки М6)",
        f"диск основания Ø{P.DISC_D}×{P.DISC_T}, сталь, на накладках",
        f"поворотный механизм {P.SWIVEL_SIZE}×{P.SWIVEL_SIZE}×{P.SWIVEL_H}",
        "П3 — плита уровня сиденья (передняя царга, опора стенки)",
        "РН1 — ребро нижнего короба спинки (лекало)",
        "Н1 — наружная стенка спинки и боков, ST 2536, 40 мм",
        "РВ1 — ребро стенки спинки (лекало)",
        "Сп1 HR 3530 50 мм + Сп2 HR 2520 профильный",
        "ремни спинки 50 мм, 7 шт. (от П3 к П4)",
        "П4 — верхний шаблон спинки и подлокотников",
        "В1 EL 2540 50 + В2 HR 3530 50 — верхний валик",
        "ПГ3 — задняя перегородка, опора ремней сиденья",
        "Пл1 — поролон подлокотника изнутри, HR 3530, 40 мм",
        "ОП — обшивка подлокотника изнутри, фанера 4 мм",
        "ПГ1 — перегородка боковая",
        "РН — ребро нижнего короба, боковое (лекало)",
        "РВ — ребро подлокотника (лекало) + полосы гибкой фанеры 4×60",
        f"блок сиденья С1+С2: {si['seat']['t_front']:.0f}/{si['seat']['t_mid']:.0f}/"
        f"{si['seat']['t_back']:.0f} мм (перед/центр/зад)",
        "синтепон 200 г/м² + ткань (≈10 мм)",
    ]
    col_w = 128
    for i, t in enumerate(names):
        c, r = divmod(i, 9)
        x = 24 + c * col_w
        y = 102 - r * 5.1
        sh.ax.add_patch(Circle((x + 2, y), 1.9, fc="white", ec=INK, lw=0.4))
        sh.text(x + 2, y, str(i + 1), ha="center", va="center", fontsize=5.3)
        sh.text(x + 5.5, y, t, va="center", fontsize=6.2)
    items = [(FOAM["seat"], "сиденье"), (FOAM["back"], "спинка"), (FOAM["arm"], "подлокотники"),
             (FOAM["top"], "валик"), (FOAM["outer"], "наружные стенки"), (FOAM["wrap"], "синтепон+ткань"),
             (WOOD_CUT, "фанера в разрезе"), (WOOD, "ребро в плоскости"), (BELT, "ремни"), (STEEL, "сталь")]
    for i, (c, t) in enumerate(items):
        x = 24 + (i % 5) * 41
        y = 51 - (i // 5) * 6.5
        sh.ax.add_patch(Rectangle((x, y - 2), 5, 4, fc=c, ec=INK, lw=0.3,
                                  hatch="////" if c == WOOD_CUT else None))
        sh.text(x + 7, y, t, va="center", fontsize=6.2)
    sh.text(24, 33, f"Толщины мягких слоёв без обёртки: сиденье {si['seat']['t_front']:.0f} → "
                    f"{si['seat']['t_mid']:.0f} → {si['seat']['t_back']:.0f}; спинка "
                    f"{si['back']['t_min']:.0f}–{si['back']['t_max']:.0f}; подлокотники 40; валик "
                    f"{si['top']['height']:.0f}; стенки 40.", fontsize=6.4)
    sh.text(24, 28, "Кромки каркаса — эквидистанта поверхности модели на 50 мм; проверка — "
                    "out/proverka_zazorov.txt.", fontsize=6.4)
    sh.save()


def sheet_base(pdf, frame, n, N, stab):
    sh = Sheet(pdf, "Основание и поворотный механизм", n, N, "1:5, 1:2.5, 1:1",
               material="Сталь Ст3 6 мм, порошковая покраска; механизм 195×195")
    ax = sh.view(25, 120, 140, 150, (-310, -310, 310, 310), 5, "Диск основания (вид сверху)")
    ax.add_patch(Circle((0, 0), P.DISC_D / 2, fc="#e6e8ea", ec=INK, lw=0.8))
    h = P.SWIVEL_HOLE_PITCH / 2
    a = P.SWIVEL_SIZE / 2
    ax.add_patch(Rectangle((-a, -a), 2 * a, 2 * a, fill=False, ec="#5b6571", lw=0.4, ls=(0, (3, 2))))
    for sx in (-1, 1):
        for sy in (-1, 1):
            ax.add_patch(Circle((sx * h, sy * h), P.SWIVEL_HOLE_D / 2, fc="white", ec=INK, lw=0.5))
    ra = P.SWIVEL_HOLE_PITCH / np.sqrt(2)
    ax.add_patch(Circle((ra, 0), P.ACCESS_HOLE_D / 2, fc="white", ec=INK, lw=0.6))
    for ang in np.radians(22.5 + 45 * np.arange(P.DISC_PADS)):
        ax.add_patch(Circle((P.DISC_PAD_R * np.cos(ang), P.DISC_PAD_R * np.sin(ang)), 15, fill=False,
                            ec="#5b6571", lw=0.4, ls=(0, (2, 1.5))))
    centerline(ax, (-320, 0), (320, 0))
    centerline(ax, (0, -320), (0, 320))
    dim(ax, (-P.DISC_D / 2, 0), (P.DISC_D / 2, 0), -300, f"Ø{P.DISC_D}")
    dim(ax, (-h, h), (h, h), 150, f"{P.SWIVEL_HOLE_PITCH}")
    dim(ax, (h, -h), (h, h), 150, f"{P.SWIVEL_HOLE_PITCH}")
    dim(ax, (0, 0), (ra, 0), -40, f"{ra:.1f}")
    label(ax, (ra, 0), (250, -120), f"Ø{P.ACCESS_HOLE_D} технологическое", fs=6)
    label(ax, (h, -h), (120, -230), f"4 отв. Ø{P.SWIVEL_HOLE_D}, зенковка снизу под М6", fs=6)
    label(ax, (P.DISC_PAD_R * np.cos(np.radians(22.5)), P.DISC_PAD_R * np.sin(np.radians(22.5))),
          (250, 250), f"{P.DISC_PADS} накладок Ø30 на R{P.DISC_PAD_R}", fs=6)
    # узел по высоте
    ax2 = sh.view(180, 150, 225, 120, (-200, -10, 200, 110), 2, "Узел крепления (разрез по оси)")
    ax2.plot([-250, 250], [0, 0], lw=0.8, c=INK)
    ax2.add_patch(Rectangle((-300, P.PAD_H), 600, P.DISC_T, fc=STEEL, ec=INK, lw=0.4))
    z1 = P.PAD_H + P.DISC_T
    ax2.add_patch(Rectangle((-a, z1), 2 * a, 3, fc="#5d636a", ec=INK, lw=0.4))
    ax2.add_patch(Rectangle((-a, P.Z_P1 - 3), 2 * a, 3, fc="#5d636a", ec=INK, lw=0.4))
    ax2.add_patch(Rectangle((-a * 0.42, z1 + 3), a * 0.84, P.SWIVEL_H - 6, fc="#7d838a", ec=INK, lw=0.4))
    ax2.add_patch(Rectangle((-300, P.Z_P1), 600, P.PLY, fc=WOOD_CUT, ec=INK, lw=0.4, hatch="////"))
    ax2.add_patch(Rectangle((-180, P.Z_P1 + P.PLY), 360, P.PLY, fc=WOOD, ec=INK, lw=0.4, hatch="\\\\\\\\"))
    for s in (-h, h):
        ax2.add_patch(Rectangle((s - 3, P.Z_P1 - 3), 6, 33, fc="#b0b5bb", ec=INK, lw=0.3))    # болт М6
        ax2.add_patch(Rectangle((s - 6.5, P.Z_P1 - 7), 13, 4, fc="#b0b5bb", ec=INK, lw=0.3))  # головка
        ax2.add_patch(Rectangle((s - 4, P.Z_P1 + P.PLY + 5), 8, 13, fc="#e0c070", ec=INK, lw=0.3))  # футорка
    ax2.add_patch(Rectangle((ra - P.ACCESS_HOLE_D / 2, P.PAD_H), P.ACCESS_HOLE_D, P.DISC_T, fc="white",
                            ec=INK, lw=0.3))
    for z, s in ((0, "0"), (P.PAD_H, f"{P.PAD_H}"), (z1, f"{z1}"), (P.Z_P1, f"{P.Z_P1}"),
                 (P.Z_P1 + P.PLY, f"{P.Z_P1 + P.PLY}"), (P.Z_P1 + 2 * P.PLY, f"{P.Z_P1 + 2 * P.PLY}")):
        level(ax2, 205, z, s, fs=6)
    label(ax2, (-150, P.Z_P1 + 9), (-230, 90), "П1 дно, фанера 18", fs=6)
    label(ax2, (-120, P.Z_P1 + P.PLY + 9), (-230, 100), "П2 плита под механизм 360×360", fs=6)
    label(ax2, (h, P.Z_P1 + P.PLY + 12), (60, 100), "футорка М6 (вкручивается сверху в П2)", fs=6)
    label(ax2, (-h, P.Z_P1 - 5), (-230, 55), "болт М6×30 + шайба", fs=6)
    label(ax2, (0, z1 + 12), (-230, 40), "механизм 195×195×25", fs=6)
    label(ax2, (-175, P.PAD_H + 3), (-230, 25), f"диск Ø{P.DISC_D}×{P.DISC_T}", fs=6)
    label(ax2, (ra, P.PAD_H + 3), (150, 55), "доступ к болтам снизу", fs=6)
    r, e, m = P.DISC_PAD_R, stab["edge"], stab["mass"]
    steps = [
        "Установка механизма",
        "1. Замерить механизм: шаг и Ø отверстий обеих пластин. Если отличаются от 170/Ø7 —",
        "   изменить SWIVEL_HOLE_PITCH / SWIVEL_HOLE_D в params.py и пересобрать DXF (python build.py).",
        "2. До сборки короба вкрутить 4 футорки М6 в П2 сверху; П2 приклеить к П1 (ПВА + саморезы 4×30),",
        "   отверстия Ø7 в П1 и Ø8 в П2 совпадают.",
        "3. Нижнюю пластину механизма прикрутить к диску винтами М6×16 (потай снизу) + гайки с нейлоном.",
        "   Верхнюю пластину при этом повернуть на 45° — угловые отверстия нижней открыты.",
        "4. Кресло положить на бок. Диск с механизмом приложить к П1 (квадрат механизма размечен на П1).",
        "   Поворачивая диск, совмещать каждое отверстие верхней пластины с технологическим",
        f"   отверстием Ø{P.ACCESS_HOLE_D} и вворачивать болт М6×30 через него в футорку. 4 болта — 4 положения.",
        "5. Пылезащитная ткань на дно — с вырезом 200×200 под механизм.",
        "",
        f"Устойчивость (накладки по R{r}: до края опоры {e:.0f} мм; масса кресла ≈{m:.0f} кг)",
    ] + [f"  {c['name']}: запас {c['sf']:.2f} (с фанерным диском {c['sf_ply']:.2f})"
         for c in stab["cases"]] + [
        "Запас = восстанавливающий момент / опрокидывающий; > 1 — не опрокидывается. С фанерным диском 18 мм",
        f"(кресло ≈{stab['mass_ply']:.0f} кг) запас не ниже {min(c['sf_ply'] for c in stab['cases']):.2f}, "
        f"со стальным — не ниже {min(c['sf'] for c in stab['cases']):.2f}: стальной диск надёжнее.",
        "Ось поворота смещена вперёд — это увеличивает запас при посадке на передний край.",
    ]
    for i, s in enumerate(steps):
        bold = s == "Установка механизма" or s.startswith("Устойчивость")
        sh.text(24, 108 - i * 4.6, s, fontsize=7.5 if bold else 6.8, weight="bold" if bold else "normal")
    sh.save()


def plate_drawing(ax, part, extra=None):
    draw_poly(ax, part.shape, fc=WOOD, ec=INK, lw=0.7)
    for x, y, d in part.holes:
        ax.add_patch(Circle((x, y), d / 2, fc="white", ec=INK, lw=0.5, zorder=4))
    for m in part.marks:
        ax.plot(*np.array(m).T, lw=0.4, c="#3d6ea8", ls=(0, (3, 2)), zorder=4)
    b = part.shape.bounds
    centerline(ax, (b[0] - 30, 0), (b[2] + 30, 0))
    centerline(ax, (0, b[1] - 30), (0, b[3] + 30))
    dim(ax, (b[0], b[1]), (b[2], b[1]), -45)
    dim(ax, (b[2], b[1]), (b[2], b[3]), 45)
    dim(ax, (b[0], 0), (0, 0), 0, f"{-b[0]:.0f}")
    dim(ax, (0, b[1]), (0, 0), 0, f"{-b[1]:.0f}")
    dim(ax, (0, 0), (0, b[3]), 0, f"{b[3]:.0f}")


def sheet_plates(pdf, frame, n, N, codes, title):
    sh = Sheet(pdf, title, n, N, "1:5")
    parts = [p for p in frame.parts if p.code in codes]
    slots = [(22, 60, 190, 215), (218, 60, 192, 215)]
    for (x, y, w, h), p in zip(slots, parts):
        b = p.shape.bounds
        ax = sh.view(x, y, w, h, (b[0] - 60, b[1] - 60, b[2] + 60, b[3] + 60), 5,
                     f"{p.code} — {p.name}, {p.thickness:.0f} мм, {p.qty} шт.")
        plate_drawing(ax, p)
        if p.code == "П3":
            op = [i for i in p.shape.interiors if Polygon(i).area > 50000]
            if op:
                ob = Polygon(op[0]).bounds
                dim(ax, (ob[0], ob[3]), (ob[2], ob[3]), 20, f"проём {ob[2] - ob[0]:.0f}")
                dim(ax, (ob[0], ob[1]), (ob[0], ob[3]), 20, f"{ob[3] - ob[1]:.0f}")
        if p.code == "П1":
            hh = P.SWIVEL_HOLE_PITCH / 2
            dim(ax, (-hh, -hh), (hh, -hh), -25, f"{P.SWIVEL_HOLE_PITCH}")
            label(ax, (hh, hh), (200, 250), f"4 отв. Ø{P.SWIVEL_HOLE_D} — болты механизма", fs=6)
            label(ax, (-97, 97), (-250, 250), "разметка механизма 195×195 (снизу)", fs=6)
        if p.code == "П2":
            label(ax, (85, 85), (150, 230), "4 отв. Ø8 под футорки М6", fs=6)
        sh.text(x + 2, y - 6, "Начало координат — ось поворота. Прямоугольные пазы — под шипы рёбер "
                              "и перегородок (сквозные, с «косточками» под фрезу Ø6).", fontsize=6.3)
    sh.text(24, 44, p_note(parts), fontsize=6.5)
    sh.save()


def p_note(parts):
    return "\n".join(f"{p.code}: {p.note}" for p in parts if p.note)


def sheet_ribs(pdf, frame, n, N):
    sh = Sheet(pdf, "Рёбра (лекала) и перегородки", n, N, "1:5, 1:10",
               material=f"Фанера ФК {P.PLY_RIB} мм (рёбра), {P.PLY} мм (перегородки)")
    ribs = frame.lower_ribs + frame.upper_ribs
    per_row = 10
    cw, chh = 39, 78
    for i, r in enumerate(ribs):
        row, col = divmod(i, per_row)
        x = 22 + col * cw
        y = 205 - row * (chh + 12)
        b = r.shape.bounds
        ax = sh.view(x, y, cw - 2, chh, (b[0] - 25, b[1] - 20, b[2] + 25, b[3] + 20), 5)
        draw_poly(ax, r.shape, fc=WOOD, ec=INK, lw=0.6)
        dim(ax, (b[0], b[1]), (b[2], b[1]), -12)
        dim(ax, (b[2], b[1]), (b[2], b[3]), 12)
        sh.text(x + (cw - 2) / 2, y + chh + 2, f"{r.code} · {r.qty} шт.", ha="center", fontsize=7,
                weight="bold")
        sh.text(x + (cw - 2) / 2, y - 3, f"z {b[1]:.0f}…{b[3]:.0f}", ha="center", fontsize=5.5,
                color="#5b6571")
    parts = frame.partitions + frame.skins
    x = 22.0
    for p in parts:
        b_ = p.shape.bounds
        w = max((b_[2] - b_[0] + 40) / 10, 16)
        ax = sh.view(x, 44, w, 58, (b_[0] - 20, b_[1] - 15, b_[2] + 20, b_[3] + 15), 10)
        draw_poly(ax, p.shape, fc=WOOD, ec=INK, lw=0.5)
        dim(ax, (b_[0], b_[1]), (b_[2], b_[1]), -12)
        dim(ax, (b_[2], b_[1]), (b_[2], b_[3]), 12)
        sh.text(x + w / 2, 105, f"{p.code} · {p.qty} шт. (1:10)", ha="center", fontsize=6.5, weight="bold")
        x += w + 6
    notes = [
        f"Рёбра — фанера {P.PLY_RIB} мм: РН — нижний короб (П1…П3), РВ — стенка спинки и подлокотников (П3…П4); перегородки — {P.PLY} мм, обшивка ОП — {P.SKIN_T} мм.",
        "Наружная кромка каждого ребра — эквидистанта поверхности модели на 50 мм (ППУ 40 + полосы 4 + синтепон/ткань).",
        "Рёбра с пометкой «2 шт.» — зеркальная пара (правое и левое), вырезаются одинаковыми и ставятся в симметричные пазы.",
        "Шипы входят в сквозные пазы плит: в П1 и П4 — на всю толщину, в П3 — по 9 мм снизу (РН) и сверху (РВ).",
        "Торец боковины — одно продольное лекало в плоскости x = ±297: ТН (от низа до П3) и ТП (от П3 до П4), кромка — по профилю торца.",
        "Сборка: клей ПВА D3 в пазы + скобы 90-й серии 32 мм (пневмостеплер) или саморезы 4×40 через плиту в торец ребра.",
    ]
    for i, s_ in enumerate(notes):
        sh.text(24, 38 - i * 4.4, s_, fontsize=6.3)
    sh.save()


def sheet_foam(pdf, soft, n, N):
    sh = Sheet(pdf, "Поролон: слои, выкройки, шаблоны", n, N, "1:10, 1:5", material="ППУ по ГОСТ 32405")
    rows = [("Код", "Деталь", "Марка", "Лист", "Размер заготовки", "Шт.")]
    for f in soft.pieces:
        b = f.pattern.bounds
        rows.append((f.code, f.name, f.grade, f"{f.thickness:.0f}", f"{b[2] - b[0]:.0f} × {b[3] - b[1]:.0f}",
                     f"{f.qty}"))
    xs = [24, 38, 118, 140, 152, 182]
    for i, r in enumerate(rows):
        y = 282 - i * 5.2
        for x, s in zip(xs, r):
            sh.text(x, y, s, fontsize=6.6, weight="bold" if i == 0 else "normal", va="center")
        if i == 0:
            sh.ax.plot([22, 190], [y - 2.6, y - 2.6], lw=0.4, c=INK)
    y = 282 - len(rows) * 5.2 - 4
    sh.text(24, y, "Марки ППУ:", fontsize=7, weight="bold")
    for i, (g, d) in enumerate(GRADES.items()):
        sh.text(24, y - 5 * (i + 1), f"{g} — плотность {d['rho']} кг/м³, жёсткость {d['kpa']} кПа; {d['desc']}",
                fontsize=6.3)
    y2 = y - 5 * (len(GRADES) + 2)
    buy = soft.purchase()
    sh.text(24, y2, "Закупка (листы 2000×1000, запас 20 %):", fontsize=7, weight="bold")
    for i, b in enumerate(buy):
        sh.text(24, y2 - 5 * (i + 1), f"{b['grade']} {b['thickness']:.0f} мм — {b['area']:.2f} м² "
                                      f"→ {max(b['sheets'], 0.25):.2f} листа", fontsize=6.3)
    # шаблон сиденья (разрез по оси)
    sp = soft.seat_profile
    b = sp.bounds
    ax = sh.view(200, 185, 210, 95, (b[0] - 40, b[1] - 30, b[2] + 40, b[3] + 30), 5,
                 "Шаблон сиденья С1+С2 (боковой профиль)")
    base = [p for p in soft.pieces if p.code == "С1"][0].profile
    comf = [p for p in soft.pieces if p.code == "С2"][0].profile
    fill_region(ax, base, "#d8dde3", ec=INK, lw=0.5)
    fill_region(ax, comf, FOAM["seat"], ec=INK, lw=0.5)
    for yy in (-300, -200, -100, 0, 100, 150, 200):
        cut = LineString([(yy, 0), (yy, 1000)]).intersection(sp)
        if cut.is_empty or cut.geom_type != "LineString":
            continue
        zz = np.array(cut.coords)[:, 1]
        ax.plot([yy, yy], [zz.min(), zz.max()], lw=0.3, c="#5b6571", ls=":")
        ax.text(yy, zz.max() + 8, f"{zz.max() - zz.min():.0f}", ha="center", fontsize=5.5)
        ax.text(yy, zz.min() - 14, f"{yy:+.0f}", ha="center", fontsize=5, color="#5b6571")
    dim(ax, (b[0], b[1]), (b[2], b[1]), -30)
    ax.text(b[0], b[3] + 22, "С1 серым (EL 3542, 80 по опоре), С2 жёлтым (HR 3530, клин). "
                            "Цифры сверху — полная толщина, снизу — координата y от оси.",
            fontsize=5.5)
    # шаблон спинки
    spr = [p for p in soft.pieces if p.code == "Сп2"][0].profile
    if spr is not None:
        bb = spr.bounds
        ax = sh.view(200, 105, 60, 65, (bb[0] - 20, bb[1] - 20, bb[2] + 60, bb[3] + 20), 5,
                     "Сп2 толщина по высоте")
        fill_region(ax, spr, FOAM["back"], ec=INK, lw=0.5)
        dim(ax, (bb[0], bb[1]), (bb[0], bb[3]), -10)
        dim(ax, (bb[0], bb[3]), (bb[2], bb[3]), 10, f"до {bb[2]:.0f}")
        ax.text(bb[2] + 5, bb[1] + 20, "низ спинки\n(z=440)", fontsize=5)
    # верхний валик
    v1 = [p for p in soft.pieces if p.code == "В1"][0].pattern
    bb = v1.bounds
    ax = sh.view(270, 60, 140, 110, (bb[0] - 60, bb[1] - 60, bb[2] + 60, bb[3] + 60), 10,
                 "В1 / В2 — П-образный валик (контур В1)")
    fill_region(ax, v1, FOAM["top"], ec=INK, lw=0.5)
    v2 = [p for p in soft.pieces if p.code == "В2"][0].pattern
    draw_poly(ax, v2, ec="#3d5a6c", lw=0.4, ls=(0, (3, 2)))
    dim(ax, (bb[0], bb[1]), (bb[2], bb[1]), -35)
    dim(ax, (bb[2], bb[1]), (bb[2], bb[3]), 35)
    centerline(ax, (0, bb[1] - 40), (0, bb[3] + 40))
    ax.text(0, (bb[1] + bb[3]) / 2, "пунктир — В2\n(верхний слой)", ha="center", fontsize=5.5)
    txt = [
        "Порядок оклейки: ремни → спанбонд → Пл1 (подлокотники) → Сп1, Сп2 (спинка) → С1, С2 (сиденье)",
        "→ Н1, Н2 (наружные стенки, от шва по центру спинки) → Пл2 (торцы) → В1, В2 (валик) → С3 → синтепон.",
        "Все стыки — встык на клей для ППУ; скругления валика и кромок — срезать и зашлифовать.",
        "Размеры заготовок — с припуском; окончательно подрезать по месту по каркасу.",
    ]
    for i, s in enumerate(txt):
        sh.text(24, 58 - i * 4.4, s, fontsize=6.3)
    sh.save()


def sheet_nesting(pdf, frame, placed, sheets, n, N):
    sh = Sheet(pdf, "Раскрой фанеры 1525×1525", n, N, "1:10" if len(sheets) <= 2 else "1:15",
               material="Фанера берёзовая ФК " + ", ".join(f"{t:.0f}" for t in sorted(set(sheets), reverse=True)) + " мм")
    from shapely import affinity
    k = 10 if len(sheets) <= 2 else 15
    w = 1525 / k + 8
    for si, t in enumerate(sheets):
        x = 22 + si * (w + 6)
        ax = sh.view(x, 90, w, w, (0, 0, 1525, 1525), k,
                     f"Лист {si + 1}: {t:.0f} мм")
        ax.add_patch(Rectangle((0, 0), 1525, 1525, fill=False, ec=INK, lw=0.8))
        for s_, p, px, py, rot in placed:
            if s_ != si:
                continue
            x0, y0, _, _ = p.shape.bounds
            g = affinity.translate(p.shape, -x0, -y0)
            if rot:
                g = affinity.rotate(g, 90, origin=(0, 0))
                mx, my, _, _ = g.bounds
                g = affinity.translate(g, -mx, -my)
            g = affinity.translate(g, px, py)
            draw_poly(ax, g, fc=WOOD, ec=INK, lw=0.35)
            c = g.representative_point()
            ax.text(c.x, c.y, p.code, fontsize=4.2, ha="center", va="center")
    sh.text(24, 80, f"Листов: {len(sheets)} (" + ", ".join(f"{sheets.count(t)} × {t:.0f} мм" for t in
                                                     sorted(set(sheets), reverse=True)) +
            "). Файлы раскроя — out/cnc/raskroy_<толщина>mm_list_<N>.dxf, слои CUT_OUT, CUT_IN, DRILL, MARK, TEXT.",
            fontsize=6.8)
    sh.text(24, 74, "Зазор между деталями 14 мм (фреза Ø6), поле листа 12 мм. Мелкие детали уложены в проёмы "
                    "крупных плит. Перед резкой замерить фактическую толщину фанеры: ширина пазов = толщина + "
                    f"{P.FIT} мм.", fontsize=6.8)
    sh.save()


def sheet_bom(pdf, rows, n, N):
    chunks = [rows[1:][i:i + 46] for i in range(0, len(rows) - 1, 46)]
    for ci, chunk in enumerate(chunks):
        sh = Sheet(pdf, "Спецификация" + (" (продолжение)" if ci else ""), n + ci, N)
        xs = [24, 44, 58, 150, 238, 268, 280]
        head = rows[0]
        for x, s in zip(xs, head):
            sh.text(x, 284, s, fontsize=6.5, weight="bold", va="center")
        sh.ax.plot([22, 413], [281, 281], lw=0.4, c=INK)
        for i, r in enumerate(chunk):
            y = 277 - i * 5.0
            for j, (x, s) in enumerate(zip(xs, r)):
                s = str(s)
                lim = [12, 6, 50, 48, 18, 6, 72][j]
                if len(s) > lim:
                    s = s[:lim - 1] + "…"
                sh.text(x, y, s, fontsize=5.8, va="center")
        sh.save()
    return len(chunks)


def sheet_assembly(pdf, n, N, img_dir):
    sh = Sheet(pdf, "Порядок сборки каркаса и обивки", n, N)
    imgs = [("karkas_iso.png", "Каркас"), ("karkas_remni_iso.png", "Каркас с ремнями"),
            ("razrez_iso.png", "Разрез: поролон и каркас")]
    for i, (f, t) in enumerate(imgs):
        pth = Path(img_dir) / f
        if pth.exists():
            a = sh.fig.add_axes([(24 + i * 130) / 420, 150 / 297, 120 / 420, 125 / 297])
            a.imshow(plt.imread(pth))
            a.axis("off")
            sh.text(24 + i * 130 + 60, 147, t, ha="center", fontsize=7.5, weight="bold")
    steps = [
        "Каркас",
        "1. Раскроить фанеру по DXF (18 мм — плиты и перегородки, 15 мм — рёбра и торцы, 4 мм — обшивка ОП). Тугой шип подшлифовать.",
        "2. Кромки, по которым идут ремни (передняя царга П3, верх ПГ3, внутренняя кромка П4), скруглить фрезой R5.",
        "3. П2 приклеить к П1 (ПВА + саморезы 4×30), вкрутить 4 футорки М6 в П2 сверху.",
        "4. Перегородки ПГ1 (2 шт.), ПГ2, ПГ3 вставить шипами в пазы П1, стянуть конфирматами 7×50; в углах — бобышки 30×30.",
        "5. Нижние рёбра РН и нижние торцы ТН — в пазы П1 по номерам (пара — справа и слева), торцом к перегородкам.",
        "6. Надеть П3 на шипы РН, ТН и перегородок; клей ПВА D3 + скобы 32 мм или саморезы 4×40. Проверить диагонали.",
        "7. Рёбра стенки РВ и торцы подлокотников ТП — в пазы П3 (ТП над ТН, в одной плоскости), сверху П4; клей + скобы.",
        "8. Полосы гибкой фанеры 4×60 — по кромкам рёбер и торцов (низ 3 ряда, стенка 4 ряда), изнутри подлокотников —",
        "   обшивка ОП (фанера 4 мм по DXF, спереди по профилю торца). Клей + скобы 10–14 мм.",
        "9. Ремни: сиденье — 5 продольных от царги П3 к ПГ3 (натяг 5–8 %) + 2 поперечных вплести; спинка — 7 вертикальных",
        "   от П3 к П4 с заворотом через кромку П4. Поверх ремней — спанбонд.",
        "",
        "Поролон и обивка",
        "10. Пл1 на обшивку подлокотников → Сп1, Сп2 на ремни спинки → С1, С2 на ремни сиденья (клей по периметру).",
        "11. Н1 (2 половины от шва по центру спинки) и Н2 на полосы; снизу завернуть под дно на 30 мм.",
        "12. Пл2 на торцы, В1 и В2 на П4 — скруглить валик; С3 завернуть валиком фасад сиденья.",
        "13. Синтепон 200 г/м² (сиденье и спинка — 2 слоя), ткань по швам модели: кант по верху спинки и по краю",
        "    сиденья, вертикальные швы от торцов подлокотников до пола, шов по центру спинки.",
        "14. Пылезащитная ткань на дно, затем механизм и диск — лист «Основание».",
    ]
    tech = [
        "Выбранная технология",
        "Каркас из берёзовой фанеры по лекалам, раскрой на ЧПУ, соединения",
        "шип–паз на клею со скобами/саморезами. Стенка — радиальные",
        "рёбра-лекала по сечениям модели, торец боковины — продольное",
        "лекало по профилю торца (ТН + ТП в одной плоскости).",
        "18 мм — несущие детали, 15 мм — лекала. Объём — листовой ППУ",
        "поверх обшивки и ремней (так же у SKDESIGN: «каркас — фанера",
        "берёзовая, поролон, ткань»).",
        "",
        "Альтернативы",
        "• Стальной каркас + формованный (литьевой) ППУ — серийное",
        "  производство (Moroso и др.); нужна пресс-форма.",
        "• Пружинная змейка вместо ремней сиденья — жёстче и дольше",
        "  держит форму; нужны металлические крепления на царгах.",
        "• ДВП 3,2 вместо гибкой фанеры для полос — дешевле, но",
        "  хуже держит изгиб на скруглениях R < 100.",
    ]
    for i, s_ in enumerate(tech):
        bold = s_ in ("Выбранная технология", "Альтернативы")
        sh.text(300, 138 - i * 4.7, s_, fontsize=7.8 if bold else 6.8, weight="bold" if bold else "normal")
    for i, s in enumerate(steps):
        bold = s in ("Каркас", "Поролон и обивка")
        sh.text(24, 138 - i * 4.7, s, fontsize=7.8 if bold else 6.8, weight="bold" if bold else "normal")
    sh.save()


# ------------------------------------------------------------------ сборка PDF
def make_pdf(frame, soft, summ, placed, sheets, path: Path, img_dir=None):
    img_dir = img_dir or Path(__file__).resolve().parents[1] / "docs" / "img"
    import csv
    bom_path = Path(path).parent / "specifikaciya.csv"
    with open(bom_path, encoding="utf-8-sig") as f:
        rows = list(csv.reader(f, delimiter=";"))
    n_bom = (len(rows) - 2) // 46 + 1
    N = 9 + n_bom
    with PdfPages(path) as pdf:
        sheet_general(pdf, frame, soft, summ, 1, N, img_dir)
        sheet_sections(pdf, frame, soft, summ, 2, N)
        sheet_base(pdf, frame, 3, N, summ["stability"])
        sheet_plates(pdf, frame, 4, N, ("П1", "П2"), "Плиты П1 и П2 (дно)")
        sheet_plates(pdf, frame, 5, N, ("П3", "П4"), "Плиты П3 и П4")
        sheet_ribs(pdf, frame, 6, N)
        sheet_foam(pdf, soft, 7, N)
        sheet_nesting(pdf, frame, placed, sheets, 8, N)
        sheet_bom(pdf, rows, 9, N)
        sheet_assembly(pdf, 9 + n_bom, N, img_dir)
        d = pdf.infodict()
        d["Title"] = "Кресло SPIN поворотное — каркас и поролон"
        d["Subject"] = "Рабочие чертежи"
