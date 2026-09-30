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
from .frame import S, X_IN, X_OUT, back_belt_y  # noqa: E402

A3 = (420, 297)
MM = 1 / 25.4
INK = "#1d2126"
WOOD = "#d9b884"
WOOD_CUT = "#c49a5c"
STEEL = "#3a3f45"
BELT = "#4a5a3a"
FOAM = {"seat": "#f3d27a", "back": "#eeb3a3", "arm": "#f5e3a3", "top": "#b9cfdc",
        "outer": "#dfe3e8", "wrap": "#f4f5f7", "side": "#cfd8c4"}
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
        outer_band = sec.buffer(-(WRAP + 40), quad_segs=8)
        for sx in (-1, 1):
            a = sx * (X_IN - soft.arm_t)
            b = sx * X_IN
            arm = box(min(a, b), P.Z_P3 + P.PLY, max(a, b), P.Z_P4 + P.PLY).intersection(inner)
            fill_region(ax, arm, FOAM["arm"], z=1)
            zones.append(arm)
            # Н3 — между наружной пластью боковины и Н1
            a, b = sx * X_OUT, sx * 600
            n3 = box(min(a, b), 0, max(a, b), P.Z_P4 + P.PLY).intersection(outer_band)
            n3 = n3.intersection(box(-2000, 70, 2000, 2000))
            fill_region(ax, n3, FOAM["side"], z=1)
            zones.append(n3)
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
    ys = -20.0                    # через средний шип П3 в боковине
    axB = sh.view(222, 116, 186, 158, (-465, -20, 465, 770), 5, f"Разрез Б–Б (y = {ys:.0f}, по боковинам)")
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
    rc1 = frame.wall_ribs[0]
    oy = rc1.origin[1]
    u480 = min(u for u, z in rc1.shape.exterior.coords if abs(z - 480) < 40)
    posA = [  # (номер, точка, сторона, высота выноски)
        (1, (-150, 350), xl, 360), (2, (-250, 445), xl, 450), (3, (-396, 380), xl, 405),
        (4, (-362, 200), xl, 215), (5, (-120, zt + 1.5), xl, 305), (6, (-236, 140), xl, 150),
        (7, (-120, 55), xl, 75), (8, (-240, 7), xl, 20), (9, (40, 22), xl, -8),
        (10, (255, 313), xr, 325), (11, (322, 420), xr, 205), (12, (408, 280), xr, 265),
        (13, (oy - u480 + 3, 480), xr, 470), (14, (220, 530), xr, 540), (15, (265, 470), xr, 415),
        (16, (300, 619), xr, 610), (17, (320, 680), xr, 690), (18, (190, 260), xr, 150),
    ]
    for num, pt, x, z in posA:
        callout(axA, pt, (x, z), num)
    dim(axA, (soft.info["seat"]["front"], 0), (P.BACK_BELT_Y0, 0), -35,
        f"поролон сиденья {P.BACK_BELT_Y0 - soft.info['seat']['front']:.0f}")
    posB = [(19, (-262, 480), xl, 520), (20, (-300, 560), xl, 600), (21, (-328, 200), xl, 240),
            (22, (-300, 313), xl, 330), (23, (372, 420), xr, 470), (24, (100, 400), xr, 380),
            (25, (395, 520), xr, 560)]
    for num, pt, x, z in posB:
        callout(axB, pt, (x, z), num)
    names = [
        "С1 — основа сиденья, EL 3542, 80 мм по опоре",
        "С2 — комфортный клин сиденья, HR 3530",
        "С3 — завёртка валика сиденья, ST 2536, 20 мм",
        "Н2 — наружная стенка фасада, ST 2536, 40 мм",
        "ремни сиденья 50 мм (5 продольных + 2 поперечных)",
        "ПГ1 — перегородка передняя (шипы сквозь боковины)",
        "П1 — дно + П2 — плита под механизм (футорки М6)",
        f"диск основания Ø{P.DISC_D}×{P.DISC_T}, сталь, на накладках",
        f"поворотный механизм {P.SWIVEL_SIZE}×{P.SWIVEL_SIZE}×{P.SWIVEL_H}",
        "П3 — плита уровня сиденья (царга, «паз в паз» с РС)",
        "РС1 — лекало спинки на всю высоту (П1…П4)",
        "Н1 — наружная стенка спинки и боков, ST 2536, 40 мм",
        "обшивка спинки снаружи — фанера 3 мм по рёбрам",
        "Сп1 HR 3530 50 мм + Сп2 HR 2520 профильный",
        "ремни спинки 50 мм, 7 шт. (от П3 к П4)",
        "П4 — верхняя обвязка спинки (концы — на боковины)",
        "В1 EL 2540 50 + В2 HR 3530 50 — верхний валик",
        "ПГ2 — задняя перегородка, опора ремней сиденья",
        f"Пл1 — поролон подлокотника изнутри, HR 3530, {soft.arm_t:.0f} мм",
        f"Б — боковина, фанера {P.SIDE_T} мм (одна на сторону)",
        "Н3 — выравнивающий слой на боковине, ST 2536 ≤40",
        "шип П3 сквозь боковину (клей + саморез 4×50)",
        "Н1 поверх Н3 — бок кресла",
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
             (FOAM["top"], "валик"), (FOAM["outer"], "наружные стенки"), (FOAM["side"], "Н3 на боковине"),
             (FOAM["wrap"], "синтепон+ткань"),
             (WOOD_CUT, "фанера в разрезе"), (WOOD, "ребро в плоскости"), (BELT, "ремни"), (STEEL, "сталь")]
    for i, (c, t) in enumerate(items):
        x = 24 + (i % 6) * 34
        y = 51 - (i // 6) * 6.5
        sh.ax.add_patch(Rectangle((x, y - 2), 5, 4, fc=c, ec=INK, lw=0.3,
                                  hatch="////" if c == WOOD_CUT else None))
        sh.text(x + 7, y, t, va="center", fontsize=6.2)
    sh.text(24, 33, f"Толщины мягких слоёв без обёртки: сиденье {si['seat']['t_front']:.0f} → "
                    f"{si['seat']['t_mid']:.0f} → {si['seat']['t_back']:.0f}; спинка "
                    f"{si['back']['t_min']:.0f}–{si['back']['t_max']:.0f}; подлокотники {soft.arm_t:.0f}; валик "
                    f"{si['top']['height']:.0f}; стенки 40, бок 40 + Н3 до 40.", fontsize=6.4)
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
    dim(ax, (b[0], min(b[1], 0)), (b[2], min(b[1], 0)), -45)
    dim(ax, (b[2], b[1]), (b[2], b[3]), 45)
    dim(ax, (b[0], 0), (0, 0), 0, f"{-b[0]:.0f}")
    if b[1] < 0:
        dim(ax, (0, b[1]), (0, 0), 0, f"{-b[1]:.0f}")
        dim(ax, (0, 0), (0, b[3]), 0, f"{b[3]:.0f}")
    else:                                   # деталь целиком за осью (П4)
        dim(ax, (b[0], 0), (b[0], b[1]), 30, f"{b[1]:.0f}")
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


def rib_notch_u(shape, z):
    """Наибольшее u ребра на высоте z (глубина до выреза «паз в паз»)."""
    hit = LineString([(-500, z), (2000, z)]).intersection(shape)
    xs = [c[0] for g in getattr(hit, "geoms", [hit]) if not g.is_empty for c in g.coords]
    return max(xs) if xs else None


def sheet_ribs(pdf, frame, n, N):
    sh = Sheet(pdf, "Рёбра (лекала) и перегородки", n, N, "1:5, 1:10",
               material=f"Фанера ФК {P.PLY_RIB} мм (рёбра), {P.PLY} мм (перегородки)")
    x = 24.0
    z3 = P.Z_P3 + P.PLY / 2
    for r in frame.wall_ribs + frame.front_ribs:
        b = r.shape.bounds
        w = (b[2] - b[0] + 70) / 5
        ax = sh.view(x, 136 if r.code.startswith("РС") else 150, w, 136 if r.code.startswith("РС") else 60,
                     (b[0] - 35, b[1] - 20, b[2] + 35, b[3] + 20) if r.code.startswith("РС") else
                     (b[0] - 35, b[1] - 20, b[2] + 35, b[3] + 20), 5)
        draw_poly(ax, r.shape, fc=WOOD, ec=INK, lw=0.6)
        dim(ax, (b[0], b[1]), (b[2], b[1]), -12)
        dim(ax, (b[2], b[1]), (b[2], b[3]), 14)
        top = 136 + 136 if r.code.startswith("РС") else 150 + 60
        sh.text(x + w / 2, top + 2.5, f"{r.code} · {r.qty} шт.", ha="center", fontsize=7.5, weight="bold")
        if r.code.startswith("РС"):
            a = rib_notch_u(r.shape, z3)
            if a is not None:
                dim(ax, (b[0], P.Z_P3 + P.PLY + 1), (a, P.Z_P3 + P.PLY + 1), 10, f"{a - b[0]:.0f}", fs=5.5)
                ax.text(b[2] + 4, z3, "← П3", fontsize=5.5, va="center")
        sh.text(x + w / 2, (136 if r.code.startswith("РС") else 150) - 4,
                f"z {b[1]:.0f}…{b[3]:.0f}", ha="center", fontsize=5.5, color="#5b6571")
        x += w + 4
    x = 24.0
    for p in frame.partitions:
        b_ = p.shape.bounds
        w = (b_[2] - b_[0] + 60) / 10
        ax = sh.view(x, 62, w, 50, (b_[0] - 30, b_[1] - 20, b_[2] + 30, b_[3] + 20), 10)
        draw_poly(ax, p.shape, fc=WOOD, ec=INK, lw=0.5)
        dim(ax, (b_[0], b_[1]), (b_[2], b_[1]), -14)
        dim(ax, (b_[2], b_[1]), (b_[2], b_[3]), 14)
        sh.text(x + w / 2, 115, f"{p.code} — {p.name.split(' (')[0].lower()} · {p.qty} шт. (1:10)",
                ha="center", fontsize=6.5, weight="bold")
        x += w + 10
    notes = [
        f"РС — рёбра спинки на всю высоту (П1…П4), фанера {P.PLY_RIB} мм: вырез «паз в паз» под П3, лапа в открытый паз П1, "
        "шип в П4. Ребро заводится снаружи по радиусу, затем запирается П4.",
        f"РН — рёбра фасада под сиденьем (П1…П3), {P.PLY_RIB} мм; ПГ1, ПГ2 — перегородки короба {P.PLY} мм, "
        "сквозные шипы 30×18 в боковины.",
        "Наружная кромка каждого ребра — эквидистанта поверхности модели на 50 мм (ППУ 40 + обшивка 3 + синтепон/ткань).",
        "«2 шт.» — зеркальная пара (правое и левое), вырезаются одинаковыми. Пазы — с «косточками» под фрезу Ø6.",
        "Сборка: клей ПВА D3 в пазы + скобы 90-й серии 32 мм или саморезы 4×40 через плиту в торец ребра.",
    ]
    for i, s_ in enumerate(notes):
        sh.text(24, 50 - i * 4.4, s_, fontsize=6.3)
    sh.save()


def sheet_side(pdf, frame, soft, n, N):
    """Боковина Б: рабочий чертёж и сечение подлокотника."""
    from shapely import affinity
    side = frame.side
    sh = Sheet(pdf, "Боковина Б — лекало подлокотника", n, N, "1:5, 1:4",
               material=f"Фанера берёзовая ФК {P.SIDE_T} мм")
    yr = frame.side_y_ref
    g = affinity.affine_transform(side.shape, [-1, 0, 0, 1, yr, 0])        # (y, z)
    b = g.bounds
    ax = sh.view(24, 100, 205, 172, (b[0] - 70, -20, b[2] + 70, b[3] + 60), 5,
                 f"Б — вид снаружи на правую боковину, {side.qty} шт. (левая — такая же)")
    sec = S.section(0, P.SIDE_X)
    draw_poly(ax, sec, ec="#c0392b", lw=0.4, ls=(0, (4, 2)), z=1)
    draw_poly(ax, g, fc=WOOD, ec=INK, lw=0.7, z=2)
    ax.plot([b[0] - 60, b[2] + 60], [0, 0], lw=0.6, c=INK)
    centerline(ax, (0, -15), (0, b[3] + 40))
    ax.text(4, b[3] + 30, "ось поворота", fontsize=5.5)
    dim(ax, (b[0], b[1]), (b[2], b[1]), -45)
    dim(ax, (b[0], 0), (0, 0), -18, f"{-b[0]:.0f}")
    dim(ax, (0, 0), (b[2], 0), -18, f"{b[2]:.0f}")
    dim(ax, (b[2], 0), (b[2], b[3]), 40, f"{b[3]:.0f}")
    dim(ax, (b[2], 0), (b[2], b[1]), 22, f"{b[1]:.0f}")
    # уступ под П4
    y4e = frame.y4j + P.P4_LAP
    dim(ax, (frame.y4j, P.Z_P4), (y4e, P.Z_P4), 30, f"уступ {P.P4_LAP} под П4", fs=5.5)
    level(ax, b[0] - 55, P.Z_P3, f"+{P.Z_P3}", fs=5.5)
    level(ax, b[0] - 55, P.Z_P4, f"+{P.Z_P4}", fs=5.5)
    level(ax, b[0] - 55, P.Z_P4 + P.PLY, f"+{P.Z_P4 + P.PLY}", fs=5.5)
    for yc in frame.p3_tabs:
        ax.text(yc, P.Z_P3 + P.PLY + 12, f"{yc:+.0f}", ha="center", fontsize=5, color="#5b6571")
    yf, yb = frame.part_axes["yf"], frame.part_axes["yb"]
    label(ax, (frame.p3_tabs[0], P.Z_P3 + P.PLY / 2), (b[0] - 40, 420), "пазы 30×18 под шипы П3 (3 шт.)", fs=6)
    label(ax, (yf, 200), (b[0] - 40, 150), "пазы под шипы ПГ1", fs=6)
    label(ax, (yb, 200), (b[2] - 60, -60 + 5), "пазы под шипы ПГ2", fs=6)
    win = max(frame.side_windows, key=lambda w: w.area)
    wc = affinity.affine_transform(win, [-1, 0, 0, 1, yr, 0]).representative_point()
    label(ax, (wc.x, wc.y), (b[0] - 40, 560), "облегчающие окна, перемычки ≥ 50", fs=6)
    ax.text(b[0], b[3] + 45, "пунктир — контур обивки в плоскости x = ±300", fontsize=5.5, color="#c0392b")
    # сечение подлокотника
    ax2 = sh.view(245, 100, 165, 172, (170, 250, 440, 745), 4, "Сечение подлокотника y = −20")
    section_drawing(ax2, frame, soft, 1, -20.0)
    zt = P.Z_P3 + P.PLY
    xa = X_IN - soft.arm_t / 2
    label(ax2, (P.SIDE_X, 480), (430, 470), f"Б — боковина {P.SIDE_T}", fs=6)
    label(ax2, (xa, 500), (185, 560), f"Пл1 HR 3530 {soft.arm_t:.0f}", fs=6)
    label(ax2, (X_IN - 1, 440), (185, 430), "картон 2 мм на окнах", fs=6)
    label(ax2, (X_OUT + 18, 330), (430, 330), "Н3 ≤ 40", fs=6)
    label(ax2, (380, 250 + 150), (430, 400), "Н1 ST 2536 40", fs=6)
    label(ax2, (P.SIDE_X, P.Z_P4 + P.PLY + 30), (185, 690), "В1 + В2 (валик)", fs=6)
    label(ax2, (270, zt - 9), (185, 290), "шип П3 сквозь Б", fs=6)
    notes = [
        f"Одна боковина на сторону — цельное лекало {P.SIDE_T} мм посередине толщины подлокотника (x = ±{P.SIDE_X}): от низа",
        "корпуса до валика, от торца до угла спинки. Контур — сечение модели этой плоскостью, эквидистанта 50 мм (у скругления",
        f"низа — {P.SIDE_BOTTOM_R} мм). Боковина — и стенка короба сиденья: в неё входят сквозные шипы П3 (3 шт.), ПГ1 и ПГ2 (по 2).",
        f"Сверху над подлокотником — кромка на уровне +{P.Z_P4 + P.PLY} (валик В1/В2 на кромку); сзади — уступ {P.P4_LAP} мм, на него ложится",
        "конец П4: клей + 2 самореза 4×50 + шкант 8×40 (отверстия в П4 по DXF).",
        "Установка: после короба (П1 + ПГ1/ПГ2 + П3) боковина надевается сбоку на шипы, клей ПВА D3 в пазы, саморез 4×50",
        "рядом с каждым шипом. Затем рёбра спинки РС, сверху П4.",
        f"Поролон с обеих сторон: изнутри Пл1 HR 3530 {soft.arm_t:.0f} мм (окна выше П3 закрыть картоном 2 мм — «внутри закрыть",
        "картоном»), снаружи Н3 (выравнивающий, до 40 мм) + Н1 40 мм. Торец — Пл2 40 мм на всю высоту.",
        f"Масса одной боковины ≈{side.mass_kg / side.qty:.1f} кг; площадь окон {sum(w.area for w in frame.side_windows) / 1e4:.1f} дм².",
    ]
    for i, s_ in enumerate(notes):
        sh.text(24, 90 - i * 4.4, s_, fontsize=6.4)
    sh.save()


# ------------------------------------------------------------------ разнесённый вид
PART_FILL = {"plate": "#e3c996", "rib": "#d7b27b", "side": "#c8955a", "part": "#cfa46c"}


def _shade(c, k):
    c = matplotlib.colors.to_rgb(c)
    return tuple(min(1, v * k) for v in c)


def explode_offset(part, origin=None, direction=None):
    if part.kind == "plate":
        return np.array({"П1": (0, 0, -170), "П2": (0, 0, -110), "П3": (0, 0, 70),
                         "П4": (0, 0, 300)}.get(part.code, (0, 0, 0)), float)
    if part.code == "Б":
        return np.array((np.sign(origin[0]) * 260, 0, 40), float)
    if part.code.startswith("ПГ"):
        return np.array((0, -40 if part.code == "ПГ1" else 40, -30), float)
    dx, dy = direction
    k = 190 if part.code.startswith("РС") else 150
    return np.array((-dx * k, -dy * k, 40 if part.code.startswith("РС") else -30), float)


def world_faces(part):
    """[(экземпляр, [(кольца грани 0), (кольца грани 1)], смещение разнесения)]."""
    from .export_3d import placements
    g = part.shape.simplify(1.0, preserve_topology=True)
    rings = [np.array(g.exterior.coords)] + [np.array(r.coords) for r in g.interiors]
    out = []
    for k, pl in enumerate(placements(part)):
        faces = []
        if pl is None:
            for z in (part.z0, part.z0 + part.thickness):
                faces.append([np.c_[r, np.full(len(r), z)] for r in rings])
            off = explode_offset(part)
        else:
            (ox, oy), (dx, dy), _ = pl
            nx, ny = -dy, dx
            for s_ in (-part.thickness / 2, part.thickness / 2):
                faces.append([np.c_[ox + r[:, 0] * dx + s_ * nx, oy + r[:, 0] * dy + s_ * ny, r[:, 1]]
                              for r in rings])
            off = explode_offset(part, (ox, oy), (dx, dy))
        out.append((k, faces, off))
    return out


def draw_exploded(ax, frame, cam=(-0.95, -1.25, 0.95), explode=True):
    from matplotlib.collections import PolyCollection
    from matplotlib.path import Path as MPath
    from matplotlib.patches import PathPatch
    c = np.array(cam, float)
    f = -c / np.linalg.norm(c)
    right = np.cross(f, [0, 0, 1.0])
    right /= np.linalg.norm(right)
    up = np.cross(right, f)

    def proj(p):
        return np.c_[p @ right, p @ up]
    items = []
    for part in frame.parts:
        key = "plate" if part.kind == "plate" else ("side" if part.code == "Б" else
                                                    ("part" if part.code.startswith("ПГ") else "rib"))
        for k, faces, off in world_faces(part):
            off = off if explode else off * 0
            cen = faces[0][0].mean(0) + off
            items.append((float(cen @ f), part, k, faces, off, key))
    items.sort(key=lambda t: -t[0])
    anchors = {}
    for depth, part, k, faces, off, key in items:
        fill = PART_FILL[key]
        d = [float(((fr[0] + off) @ f).mean()) for fr in faces]
        far, near = (faces[0], faces[1]) if d[0] > d[1] else (faces[1], faces[0])
        # дальняя грань, боковины кромок, ближняя грань
        polys = []
        a, b = far[0] + off, near[0] + off
        for i in range(len(a) - 1):
            q = np.array([a[i], a[i + 1], b[i + 1], b[i]])
            polys.append((float((q @ f).mean()), proj(q)))
        for fr, col in ((far, _shade(fill, 0.8)),):
            verts, codes = [], []
            for r in fr:
                pr = proj(r + off)
                verts += pr.tolist()
                codes += [MPath.MOVETO] + [MPath.LINETO] * (len(pr) - 2) + [MPath.CLOSEPOLY]
            ax.add_patch(PathPatch(MPath(verts, codes), fc=col, ec=INK, lw=0.15, zorder=2))
        polys.sort(key=lambda t: -t[0])
        ax.add_collection(PolyCollection([p for _, p in polys], facecolors=[_shade(fill, 0.72)],
                                         edgecolors=[_shade(fill, 0.55)], linewidths=0.1, zorder=2))
        verts, codes = [], []
        for r in near:
            pr = proj(r + off)
            verts += pr.tolist()
            codes += [MPath.MOVETO] + [MPath.LINETO] * (len(pr) - 2) + [MPath.CLOSEPOLY]
        ax.add_patch(PathPatch(MPath(verts, codes), fc=fill, ec=INK, lw=0.3, zorder=2))
        if part.code not in anchors or k == 0:
            pts2 = proj(near[0] + off)
            poly = Polygon(pts2).buffer(0)
            rp = poly.representative_point() if not poly.is_empty else Polygon(pts2).centroid
            anchors.setdefault(part.code, (rp.x, rp.y, part, off, near))
    # стрелки направления установки
    for code, (x, y, part, off, near) in anchors.items():
        if not explode or np.linalg.norm(off) < 1:
            continue
        p0 = near[0].mean(0) + off
        p1 = near[0].mean(0) + off * 0.35
        a0, a1 = proj(np.array([p0]))[0], proj(np.array([p1]))[0]
        ax.annotate("", a1, a0, arrowprops=dict(arrowstyle="-|>", lw=0.6, color="#b03a2e",
                                                 mutation_scale=7), zorder=7)
    return anchors, proj


def sheet_exploded(pdf, frame, soft, n, N):
    sh = Sheet(pdf, "Каркас: разнесённый вид и спецификация деталей", n, N, "—")
    # спецификация (как в ЧПУ-проектах: поз., обозначение, ЧПУ, длина, ширина, кол-во)
    head = ("Поз", "Код", "Наименование", "Ф, мм", "Обраб.", "Длина", "Ширина", "Кол-во")
    xs = [24, 33, 45, 124, 136, 150, 164, 180]
    rows, pos = [], {}
    for i, p in enumerate(frame.parts, 1):
        x0, y0, x1, y1 = p.shape.bounds
        L, W = sorted((x1 - x0, y1 - y0), reverse=True)
        pos[p.code] = i
        nm = p.name.split(" (")[0]
        rows.append((i, p.code, nm, f"{p.thickness:.0f}", "ЧПУ", f"{L:.0f}", f"{W:.0f}", p.qty))
    k = len(rows)
    sk = soft.info["skin"]
    rows += [
        (k + 1, "—", "Обшивка спинки снаружи", "3", "—", f"{sk['back'] + 60:.0f}", f"{sk['h_up'] + 20:.0f}", 1),
        (k + 2, "—", "Полосы обшивки низа", "3", "—", f"{(sk['back'] + sk['front']) / 2 + 60:.0f}", "60", 6),
        (k + 3, "—", "Картон на окна боковин", "2", "—", "по месту", "", 2),
        (k + 4, "—", "Бобышки 30×30 (углы короба)", "—", "—", "150", "30", 8),
    ]
    y = 282
    for x, s_ in zip(xs, head):
        sh.text(x, y, s_, fontsize=6.6, weight="bold", va="center")
    sh.ax.plot([22, 196], [y - 2.8, y - 2.8], lw=0.5, c=INK)
    for i, r in enumerate(rows):
        yy = y - 6.2 - i * 5.4
        for x, s_ in zip(xs, r):
            sh.text(x, yy, str(s_), fontsize=6.3, va="center")
        sh.ax.plot([22, 196], [yy - 2.7, yy - 2.7], lw=0.2, c="#9aa3ad")
    for x in [22, 31, 43, 122, 134, 148, 162, 178, 196]:
        sh.ax.plot([x, x], [y + 3, yy - 2.7], lw=0.3, c=INK)
    yb = yy - 10
    t18 = sum(p.mass_kg for p in frame.parts if p.thickness == 18)
    t15 = sum(p.mass_kg for p in frame.parts if p.thickness == 15)
    notes = [
        f"Фанера ФК 18 мм — {t18:.1f} кг, 15 мм — {t15:.1f} кг; всего деталей {sum(p.qty for p in frame.parts)}.",
        "Соединения: шип–паз на клею ПВА D3 + скобы 32 мм / саморезы 4×40;",
        "рёбра спинки РС — «паз в паз» с П3 и лапой в открытый паз П1.",
        "Порядок: П1+П2 → ПГ1, ПГ2, РН → П3 → Б (сбоку) → РС (снаружи",
        "по радиусу) → П4 сверху (запирает рёбра) → бобышки, обшивка.",
        "Красные стрелки — направление установки детали.",
    ]
    for i, s_ in enumerate(notes):
        sh.text(24, yb - i * 4.6, s_, fontsize=6.4)
    # каркас в сборе (малый вид)
    axs = sh.fig.add_axes([24 / 420, 10 / 297, 170 / 420, (yb - 48) / 297])
    axs.set_aspect("equal")
    axs.axis("off")
    draw_exploded(axs, frame, explode=False)
    axs.autoscale_view()
    sh.text(24, yb - 31, "Каркас в сборе", fontsize=7.5, weight="bold")
    # разнесённый вид
    ax = sh.fig.add_axes([202 / 420, 48 / 297, 212 / 420, 240 / 297])
    ax.set_aspect("equal")
    ax.axis("off")
    anchors, proj = draw_exploded(ax, frame)
    ax.autoscale_view()
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    R = max(x1 - x0, y1 - y0) * 0.56
    for code, (x, y, part, off, near) in anchors.items():
        v = np.array([x - cx, y - cy])
        v = v / (np.linalg.norm(v) + 1e-9)
        tp = (x + v[0] * R * 0.22, y + v[1] * R * 0.22)
        callout(ax, (x, y), tp, pos[code])
    ax.set_xlim(cx - R, cx + R)
    ax.set_ylim(cy - R * 240 / 212, cy + R * 240 / 212)
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
        "Порядок оклейки: ремни → спанбонд → картон на окна боковин → Пл1 (изнутри) → Сп1, Сп2 (спинка) → С1, С2",
        "(сиденье) → Н3 на боковины → Н1, Н2 (наружные стенки, от шва по центру спинки) → Пл2 (торцы) → В1, В2 → С3 → синтепон.",
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
    sh.text(24, 74, "Зазор между деталями 10 мм (фреза Ø6), поле листа 10 мм. Мелкие детали уложены в проёмы "
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


def sheet_assembly(pdf, n, N, img_dir, arm_t=60):
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
        f"1. Раскроить фанеру по DXF (18 мм — плиты, боковины, перегородки; 15 мм — рёбра). Тугой шип подшлифовать, кромки пазов — фаска 1 мм.",
        "2. Кромки, по которым идут ремни (царга П3, верх ПГ2, наружная кромка П4), скруглить фрезой R5.",
        "3. П2 приклеить к П1 (ПВА + саморезы 4×30), вкрутить 4 футорки М6 в П2 сверху.",
        "4. Короб: ПГ1, ПГ2 и рёбра фасада РН — шипами в пазы П1; сверху П3 на их шипы. Клей ПВА D3 + скобы 32 мм. Диагонали!",
        "5. Боковины Б — сбоку на сквозные шипы П3, ПГ1, ПГ2 (по 3 + 2 + 2); у каждого шипа саморез 4×50 через боковину.",
        "6. Рёбра спинки РС — снаружи по радиусу: вырез ребра на П3, открытый паз П1 на лапу ребра («паз в паз»), клей.",
        "7. П4 сверху: пазы на шипы РС, концы на уступы боковин (клей + 2 самореза 4×50 + шкант 8×40). П4 запирает РС.",
        "8. Бобышки 30×30 в углы короба (П1/ПГ/Б) на клей + саморезы. Обшивка спинки снаружи — фанера 3 мм по рёбрам,",
        "   низ — полосы 3×60 (3 ряда); окна боковин выше П3 изнутри закрыть картоном 2 мм. Клей + скобы 10–14 мм.",
        "9. Ремни: сиденье — 5 продольных от царги П3 к ПГ2 (натяг 5–8 %) + 2 поперечных вплести; спинка — 7 вертикальных",
        "   от П3 к П4 с заворотом через кромку П4. Поверх ремней — спанбонд.",
        "",
        "Поролон и обивка",
        f"10. Пл1 ({arm_t:.0f} мм) на внутренние пласти боковин → Сп1, Сп2 на ремни спинки → С1, С2 на ремни сиденья.",
        "11. Н3 на наружные пласти боковин, затем Н1 (2 половины от шва по центру спинки) и Н2; снизу — под дно на 30 мм.",
        "12. Пл2 на торцы боковин (на всю высоту), В1 и В2 на П4 и кромки боковин — скруглить валик; С3 — валик сиденья.",
        "13. Синтепон 200 г/м² (сиденье и спинка — 2 слоя), ткань по швам модели: кант по верху спинки и по краю",
        "    сиденья, вертикальные швы от торцов подлокотников до пола, шов по центру спинки.",
        "14. Пылезащитная ткань на дно, затем механизм и диск — лист «Основание».",
    ]
    tech = [
        "Выбранная технология",
        "Каркас из берёзовой фанеры по лекалам (ЧПУ), как в",
        "лекальных каркасах диванов: цельная боковина на сторону,",
        "рёбра спинки на всю высоту, горизонтальные обвязки П1, П3,",
        "П4 «паз в паз» с рёбрами; шип–паз на клею + скобы/саморезы.",
        "Боковина — и стенка короба: в неё входят шипы П3 и ПГ.",
        "Снаружи — фанера 3 мм по рёбрам, изнутри окна — картон.",
        "18 мм — несущие детали, 15 мм — рёбра. Объём — листовой ППУ.",
        "",
        "Альтернативы",
        "• Стальной каркас + формованный (литьевой) ППУ — серийное",
        "  производство (Moroso и др.); нужна пресс-форма.",
        "• Пружинная змейка вместо ремней сиденья — жёстче и дольше",
        "  держит форму; нужны металлические крепления на царгах.",
        "• ДВП 3,2 вместо фанеры 3 мм для обшивки — дешевле, но",
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
    N = 11 + n_bom
    with PdfPages(path) as pdf:
        sheet_general(pdf, frame, soft, summ, 1, N, img_dir)
        sheet_sections(pdf, frame, soft, summ, 2, N)
        sheet_exploded(pdf, frame, soft, 3, N)
        sheet_base(pdf, frame, 4, N, summ["stability"])
        sheet_plates(pdf, frame, 5, N, ("П1", "П2"), "Плиты П1 и П2 (дно)")
        sheet_plates(pdf, frame, 6, N, ("П3", "П4"), "Плиты П3 и П4")
        sheet_side(pdf, frame, soft, 7, N)
        sheet_ribs(pdf, frame, 8, N)
        sheet_foam(pdf, soft, 9, N)
        sheet_nesting(pdf, frame, placed, sheets, 10, N)
        sheet_bom(pdf, rows, 11, N)
        sheet_assembly(pdf, 11 + n_bom, N, img_dir, soft.arm_t)
        d = pdf.infodict()
        d["Title"] = "Кресло SPIN поворотное — каркас и поролон"
        d["Subject"] = "Рабочие чертежи"
