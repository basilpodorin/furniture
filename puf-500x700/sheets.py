"""Альбом А3: 6 листов для цеха."""
import math

import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from shapely.geometry import LineString, box
from shapely.ops import unary_union

import params as P
import parts as PR
import soft
from drawing import (C_CARD, C_DIM, C_FABRIC, C_FOAM, C_HOLCON, C_LINE, C_PLY,
                     C_PLY_EDGE, Page)
from geom import K90, Contour, rounded_rect

TOTAL = 6


# ====================================================================== лист 1
def soft_profile(w, z0, z1, rb, rt, dome=0.0):
    x0, x1 = -w / 2, w / 2
    bd = 2 * dome / (w - 2 * rt) if dome else 0.0
    return Contour([
        (x0 + rb, z0, 0), (x1 - rb, z0, K90), (x1, z0 + rb, 0), (x1, z1 - rt, K90),
        (x1 - rt, z1, bd), (x0 + rt, z1, K90), (x0, z1 - rt, 0), (x0, z0 + rb, K90),
    ])


def elevation(pg, w, ox, oy, s, leg_pos):
    z = P.z_levels()
    lo = soft_profile(w, P.LEG_H, z["lo_top"], P.EDGE_R, P.EDGE_R)
    up = soft_profile(w, z["lo_top"], z["edge_top"], P.EDGE_R, 35, P.DOME)
    for c in (lo, up):
        pg.contour(c, s, ox + w / 2 / s, oy, fc=C_FABRIC, ec=C_LINE, lw=0.35)
    for lx in leg_pos:
        pg.rect(ox + (w / 2 + lx - P.LEG_D / 2) / s, oy, P.LEG_D / s, P.LEG_H / s, fc="#222", ec="#222")


def sheet_general(pdf, out):
    pg = Page("Общий вид. Разрез А-А. Узел Б", 1, TOTAL, "1:10; 1:5; 1:2,5; 1:1")
    z = P.z_levels()
    lx, ly = P.PL / 2 - P.LEG_INSET, P.PW / 2 - P.LEG_INSET

    # --- фасад и бок, 1:10
    s = 10
    ox, oy = 38, 232
    pg.text(ox - 8, 284, "Вид спереди и сбоку, 1:10", 9, weight="bold")
    elevation(pg, P.L, ox, oy, s, (-lx, lx))
    pg.dim_h(ox, ox + P.L / s, oy, oy - 6, f"{P.L:g}")
    pg.dim_v(oy, oy + P.H / s, ox, ox - 11, f"{P.H:g}")
    pg.dim_v(oy + P.LEG_H / s, oy + z["lo_top"] / s, ox, ox - 5, f"{P.MODULE_H:g}", 5.5)
    pg.dim_v(oy + z["lo_top"] / s, oy + z["edge_top"] / s, ox, ox - 5, f"{P.MODULE_H:g}", 5.5)
    ox2 = ox + P.L / s + 18
    elevation(pg, P.W, ox2, oy, s, (-ly, ly))
    pg.dim_h(ox2, ox2 + P.W / s, oy, oy - 6, f"{P.W:g}")
    pg.text(ox2 + P.W / s + 2, oy + 0.5, f"опоры h{P.LEG_H:g}", 5.8)
    pg.text(ox2 + P.W / s + 2, oy + z["dome_top"] / s - 1.5, f"купол +{P.DOME:g}", 5.8)

    # --- план, 1:5
    s = 5
    ox, oy = 40, 70
    cx, cy = ox + P.L / 2 / s, oy + P.W / 2 / s
    pg.text(ox - 10, 192, "Вид сверху, 1:5 (каркас пунктиром)", 9, weight="bold")
    pg.contour(rounded_rect(P.L, P.W, soft.OUT_R), s, cx, cy, fc="#f1d5cc", ec=C_LINE, lw=0.35)
    pg.contour(rounded_rect(P.PL, P.PW, P.PLATE_R), s, cx, cy, ec=C_PLY_EDGE, lw=0.25, ls="--")
    for sy in (-1, 1):
        pg.rect(cx - P.WALL_LONG / 2 / s, cy + (sy * PR.LONG_Y - P.T / 2) / s, P.WALL_LONG / s, P.T / s,
                ec=C_PLY_EDGE, lw=0.2, ls="--")
    for sx in (-1, 1):
        pg.rect(cx + (sx * PR.SHORT_X - P.T / 2) / s, cy - P.WALL_SHORT / 2 / s, P.T / s, P.WALL_SHORT / s,
                ec=C_PLY_EDGE, lw=0.2, ls="--")
    pg.rect(cx - P.T / 2 / s, cy - P.WALL_SHORT / 2 / s, P.T / s, P.WALL_SHORT / s, ec=C_PLY_EDGE, lw=0.2, ls="--")
    bx, by = P.BOLT_XY
    for sx in (-1, 1):
        for sy in (-1, 1):
            px, py = cx + sx * bx / s, cy + sy * by / s
            pg.line([(px - 1.8, py), (px + 1.8, py)], lw=0.25, color="#b00")
            pg.line([(px, py - 1.8), (px, py + 1.8)], lw=0.25, color="#b00")
            pg.ax.add_patch(plt.Circle((cx + sx * lx / s, cy + sy * ly / s), P.LEG_D / 2 / s,
                                       fc="none", ec="#333", lw=0.5, ls="--"))
    pg.line([(cx, cy - P.W / 2 / s - 4), (cx, cy + P.W / 2 / s + 4)], lw=0.15, ls="-.")
    pg.line([(cx - P.L / 2 / s - 4, cy), (cx + P.L / 2 / s + 4, cy)], lw=0.15, ls="-.")
    xa = cx + 200 / s
    for yy, d in ((cy - P.W / 2 / s - 3, -1), (cy + P.W / 2 / s + 3, 1)):
        pg.line([(xa, yy), (xa, yy + d * 5)], lw=0.7)
        pg.ax.annotate("", xy=(xa + 5, yy + d * 5), xytext=(xa, yy + d * 5),
                       arrowprops=dict(arrowstyle="-|>", lw=0.6, color=C_LINE, mutation_scale=7))
        pg.text(xa + 6.5, yy + d * 5, "А", 8, va="center", weight="bold")
    pg.dim_h(ox, ox + P.L / s, oy, oy - 7, f"{P.L:g}")
    pg.dim_v(oy, oy + P.W / s, ox, ox - 6, f"{P.W:g}")
    pg.dim_h(cx, cx + bx / s, cy + by / s, cy + P.W / 2 / s + 1, f"{bx:g}", 5.5)
    pg.dim_v(cy, cy + by / s, cx + bx / s, cx + P.L / 2 / s + 1, f"{by:g}", 5.5)
    ytxt = oy - 16
    pg.text(ox, ytxt, "+ болты M8 (4)      ○ опоры Ø40 (4), 35 от кромки плиты      - - каркас", 6)

    section_aa(pg, 290, 58)
    bolt_detail(pg, 222, 218)
    pg.save(pdf, out / "sheet_1_general.png")


def section_aa(pg, ox, oy):
    """Полуразрез по x = 200 (через шипы длинных стенок), от оси до края, 1:2,5."""
    s = 2.5
    z = P.z_levels()
    Y = P.PW / 2
    fb, ft = z["lo_frame_bot"], z["lo_frame_top"]
    ub, ut = z["up_frame_bot"], z["up_frame_top"]
    pg.text(ox - 5, 284, "Разрез А-А, 1:2,5 (x = 200, через шипы)", 9, weight="bold")
    tf = lambda pts: [(ox + y / s, oy + zz / s) for y, zz in pts]   # noqa: E731

    ply = {
        "P1B": box(Y - P.RING_BOT, fb, Y, fb + P.T),
        "P1T": box(Y - P.RING_MID, ft - P.T, Y, ft),
        "P2B": box(Y - P.RING_MID, ub, Y, ub + P.T),
        "P2T": box(0, ut - P.T, Y, ut),
    }
    walls = {"W1L": box(PR.LONG_Y - P.T / 2, fb, PR.LONG_Y + P.T / 2, ft),
             "W2L": box(PR.LONG_Y - P.T / 2, ub, PR.LONG_Y + P.T / 2, ut)}
    card = [box(Y, fb, Y + P.CARD, ft), box(Y, ub, Y + P.CARD, ut)]
    f0, f1 = Y + P.CARD, Y + P.CARD + P.FOAM
    r = P.EDGE_R

    def foam_strip(z0, z1, round_bot, round_top):
        c = Contour([(f0, z0, 0), (f1 - (r if round_bot else 0), z0, K90 if round_bot else 0)]
                    + ([(f1, z0 + r, 0)] if round_bot else [])
                    + [(f1, z1 - (r if round_top else 0), K90 if round_top else 0)]
                    + ([(f1 - r, z1, 0)] if round_top else [])
                    + [(f0, z1, 0)])
        return c.polygon(0.3)

    foam_lo = foam_strip(fb, ft, True, True)
    foam_up = foam_strip(ub, ut, True, False)
    seat = Contour([(0, ut, 0), (f1, ut, K90), (f1 - P.FOAM, ut + P.FOAM, 0), (0, ut + P.FOAM, 0)]).polygon(0.3)
    hol = P.HOLCON_SIDE
    hol_lo = foam_lo.buffer(hol).intersection(box(f0, fb, f1 + hol + 1, ft)).difference(foam_lo)
    up_soft = unary_union([foam_up, seat])
    hol_up = up_soft.buffer(hol).intersection(box(0, ub, f1 + hol + 1, ut + P.FOAM + hol)) \
        .difference(up_soft).difference(box(0, 0, f0, ut))
    lo_all = unary_union(list(ply.values())[:2] + [walls["W1L"], card[0], foam_lo, hol_lo])
    up_all = unary_union(list(ply.values())[2:] + [walls["W2L"], card[1], foam_up, seat, hol_up])

    def fill(geom, **kw):
        for g in getattr(geom, "geoms", [geom]):
            if not g.is_empty:
                pg.shape(tf(list(g.exterior.coords)[:-1]),
                         [tf(list(h.coords)[:-1]) for h in g.interiors], **kw)

    for g in ply.values():
        fill(g, fc=C_PLY, ec=C_PLY_EDGE, lw=0.25, hatch="////")
    for g in walls.values():
        fill(g, fc=C_PLY, ec=C_PLY_EDGE, lw=0.25, hatch="\\\\\\\\")
    for g in card:
        fill(g, fc=C_CARD, ec=C_LINE, lw=0.1)
    for g in (foam_lo, foam_up, seat):
        fill(g, fc=C_FOAM, ec="#9b8a3a", lw=0.2)
    for g in (hol_lo, hol_up):
        fill(g, fc=C_HOLCON, ec="#6f8fb0", lw=0.1)
    # ткань: наружный обвод модулей до линии скобы; верх сиденья — куполом
    staple = Y - P.FABRIC_STAPLE_IN
    y_dome = 200.0
    keep = box(staple, -10, 400, 600).difference(box(-1, ut + P.FOAM, y_dome, 600))
    for g in (lo_all, up_all):
        ring = LineString(list(g.buffer(P.FABRIC, join_style=2).exterior.coords))
        seg = ring.intersection(keep)
        for part in getattr(seg, "geoms", [seg]):
            if part.length > 0:
                pg.line(tf(list(part.coords)), lw=0.5, color=C_FABRIC)
    top = z["edge_top"]
    dome = [(y, top + P.DOME * (1 - (y / y_dome) ** 2)) for y in range(0, int(y_dome) + 1, 5)]
    pg.line(tf(dome), lw=0.5, color=C_FABRIC)
    # перегородка — за разрезом
    pg.poly(tf([(0, ub + P.T), (PR.LONG_Y - P.T / 2, ub + P.T), (PR.LONG_Y - P.T / 2, ut - P.T), (0, ut - P.T)]),
            ec="#888", lw=0.2, ls="--")
    # опора — видна за разрезом
    lyy = Y - P.LEG_INSET
    pg.rect(ox + (lyy - P.LEG_D / 2) / s, oy, P.LEG_D / s, P.LEG_H / s, fc="#333", ec="#333")
    pg.line([(ox, oy - 3), (ox, oy + 462 / s)], lw=0.15, ls="-.")
    pg.line([(ox - 3, oy), (ox + 262 / s, oy)], lw=0.35)   # пол

    # размеры справа
    xr = ox + (f1 + hol + P.FABRIC) / s
    pg.dim_v(oy, oy + z["dome_top"] / s, xr, xr + 15, f"{P.H:g}")
    pg.dim_v(oy, oy + P.LEG_H / s, xr, xr + 7, f"{P.LEG_H:g}", 5.5)
    pg.dim_v(oy + fb / s, oy + ft / s, xr, xr + 7, f"{P.HF_LO:g}", 5.5)
    pg.dim_v(oy + ub / s, oy + ut / s, xr, xr + 7, f"{P.HF_UP:g}", 5.5)
    pg.dim_v(oy + ut / s, oy + (ut + P.FOAM) / s, xr, xr + 7, f"{P.FOAM:g}", 5.5)
    yt = oy + 462 / s
    pg.dim_h(ox, ox + Y / s, oy + ut / s, yt + 2, f"{Y:g}", 5.5)
    pg.dim_h(ox, ox + (f1 + hol + P.FABRIC) / s, oy + ut / s, yt + 9, f"{P.W / 2:g}", 5.5)

    # выноски — текст в пустой полости каркаса
    L = [((40, top + 1.5), f"холкон {P.HOLCON_GSM} + ткань"),
         ((110, ut + 18), f"ППУ {P.FOAM_SEAT} 30"),
         ((Y - 40, ut - 7), "P2T ф15 (сплошная)"),
         ((PR.LONG_Y, 350), "W2L ф15"),
         ((f0 + 12, 330), f"ППУ {P.FOAM_SIDE} 30"),
         ((Y + 1.5, 300), "картон 3"),
         ((f1 + 2, 280), f"холкон {P.HOLCON_GSM}"),
         ((Y - 60, ub + 7), f"P2B рамка {P.RING_MID:g}"),
         ((Y - 60, ft - 7), f"P1T рамка {P.RING_MID:g}"),
         ((PR.LONG_Y, 140), "W1L ф15"),
         ((f1 + 3, 60), "ткань, скоба 25 от кромки"),
         ((Y - 30, fb + 7), f"P1B рамка {P.RING_BOT:g}"),
         ((lyy, 8), "опора h15")]
    tx = ox + 4
    zs = [385, 360, 335, 300, 280, 260, 240, 212, 190, 150, 110, 70, 40]
    for ((y, zz), t), tz in zip(L, zs):
        pg.leader((ox + y / s, oy + zz / s), (tx, oy + tz / s), t, 5.6)
    # легенда
    ly0 = oy - 10
    for i, (c, t) in enumerate(((C_PLY, "фанера"), (C_FOAM, "ППУ"), (C_HOLCON, "холкон"),
                                (C_CARD, "картон"), (C_FABRIC, "ткань"))):
        pg.rect(ox - 5 + i * 20, ly0, 4, 3, fc=c, ec=C_LINE, lw=0.1)
        pg.text(ox + i * 20, ly0 + 0.5, t, 5.8)


def bolt_detail(pg, ox, oy):
    """Узел Б: стяжка модулей, 1:1. (ox, oy) — ось болта, низ P1T."""
    pg.text(ox - 10, 284, "Узел Б. Стяжка модулей, 1:1", 9, weight="bold")
    gap = 2 * P.FABRIC
    tf = lambda x, y: (ox + x, oy + y)                       # noqa: E731
    w = 30
    hatch = ("////", "\\\\\\\\")
    for i, (y0, d) in enumerate(((0.0, P.BOLT_HOLE_D), (P.T + gap, P.TNUT_HOLE_D))):
        for sx in (-1, 1):
            xa, xb = sorted((sx * d / 2, sx * w))
            pg.shape([tf(xa, y0), tf(xb, y0), tf(xb, y0 + P.T), tf(xa, y0 + P.T)], fc=C_PLY,
                     ec=C_PLY_EDGE, hatch=hatch[i], lw=0.25)
    for sx in (-1, 1):
        xa, xb = sorted((sx * 5, sx * 15))
        pg.rect(*tf(xa, P.T), xb - xa, gap, fc="#8a6d5a", ec="none")
    top = 2 * P.T + gap
    pg.rect(*tf(-11, top), 22, 1.5, fc="#999", ec=C_LINE, lw=0.2)
    pg.rect(*tf(-P.TNUT_HOLE_D / 2, top - 11), P.TNUT_HOLE_D, 11, fc="#bbb", ec=C_LINE, lw=0.2)
    pg.rect(*tf(-8, -1.6), 16, 1.6, fc="#999", ec=C_LINE, lw=0.2)
    pg.rect(*tf(-6.5, -1.6 - 5.3), 13, 5.3, fc="#777", ec=C_LINE, lw=0.2)
    pg.rect(*tf(-4, -1.6), 8, 40, fc="#cfcfcf", ec=C_LINE, lw=0.2)
    pg.line([tf(0, -12), tf(0, 45)], lw=0.15, ls="-.")
    pg.dim_v(oy, oy + P.T, ox + w, ox + w + 5, f"{P.T:g}", 5.5)
    pg.dim_v(oy + P.T + gap, oy + top, ox + w, ox + w + 5, f"{P.T:g}", 5.5)
    t = [((11, top + 0.8), "футорка M8", top + 8),
         ((w - 4, top - 4), "P2B, отв. Ø10", top - 5),
         ((15, P.T + 1), "прокладка 2 мм", P.T + 1),
         ((w - 4, 5), "P1T, отв. Ø9", 5),
         ((6.5, -4), "болт M8x40 + шайба", -9)]
    for (x, y), txt, ty in t:
        pg.leader(tf(x, y), (ox + w + 12, oy + ty), txt, 5.8)
    pg.notes(ox - 30, oy - 18, "", [
        "Футорка забивается в P2B со стороны стенок до склейки",
        "каркаса. Прокладка 2 мм у каждого болта = два слоя ткани",
        "на кромке рамок: рамки не выгибаются при затяжке.",
        f"Болты: 4 шт в точках (±{P.BOLT_XY[0]:g}; ±{P.BOLT_XY[1]:g}) от центра, снизу",
        f"через окно P1B; ось в {PR.bolt_window_clearance():.0f} мм от края окна — ключ с",
        "головкой 13 проходит вертикально."], 5.8, 3.6)


# ====================================================================== лист 2
def plate_view(pg, part, cx, cy, s):
    pg.part(part, s, cx, cy)
    pg.line([(cx - P.PL / 2 / s - 3, cy), (cx + P.PL / 2 / s + 3, cy)], lw=0.12, ls="-.")
    pg.line([(cx, cy - P.PW / 2 / s - 3), (cx, cy + P.PW / 2 / s + 3)], lw=0.12, ls="-.")
    x0, y0 = cx - P.PL / 2 / s, cy - P.PW / 2 / s
    pg.dim_h(x0, x0 + P.PL / s, y0, y0 - 6, f"{P.PL:g}")
    pg.dim_v(y0, y0 + P.PW / s, x0, x0 - 6, f"{P.PW:g}")
    pg.text(x0, y0 + P.PW / s + 5, f"{part.key} — {part.name}, {part.qty} шт ({part.module} модуль)", 7.5,
            weight="bold")
    pg.text(x0, y0 + P.PW / s + 1.5, part.note, 6)
    win = [c for k, c in part.holes if k == "window"]
    if win:
        wx0, wy0, wx1, wy1 = win[0].bbox()
        ring = P.PL / 2 - wx1
        pg.dim_h(cx + wx1 / s, x0 + P.PL / s, cy - 12, cy - 12, f"{ring:g}", 6)
        pg.text(cx, cy + 2, f"окно {wx1 - wx0:g}x{wy1 - wy0:g} R{P.WINDOW_R:g}", 6, ha="center")
    holes = [c for k, c in part.holes if k == "hole"]
    if holes:
        hx, hy, hr = max(holes, key=lambda c: (c.circle[0], c.circle[1])).circle
        pg.dim_h(cx, cx + hx / s, cy + hy / s, cy + (hy + 30) / s, f"{hx:g}", 6)
        pg.dim_v(cy, cy + hy / s, cx + hx / s, x0 + P.PL / s + 6, f"{hy:g}", 6)
        pg.text(cx + hx / s, cy + hy / s - 5, f"4 отв. Ø{2 * hr:g}", 6, ha="center")
    if part.marks:
        mx, my = max(part.marks)
        pg.dim_h(cx + mx / s, x0 + P.PL / s, cy + my / s, y0 + P.PW / s + 6, f"{P.LEG_INSET:g}", 5.5)


def sheet_plates(pdf, out):
    pg = Page("Плиты и рамки каркаса", 2, TOTAL, "1:5")
    s = 5
    k = PR.by_key()
    pos = {"P2T": (100, 212), "P2B": (255, 212), "P1T": (100, 103), "P1B": (255, 103)}
    for key, (cx, cy) in pos.items():
        plate_view(pg, k[key], cx, cy, s)
    lines = [
        f"1. {P.PLY_NAME}.",
        "   Размеры — по DXF (out/dxf/parts),",
        f"   углы плит R{P.PLATE_R:g}.",
        f"2. Пазы под шипы {P.SLOT_W:g} x {P.TENON_LEN + P.SLOT_CLEAR:g},",
        f"   у перегородки снизу {P.SLOT_W:g} x {P.PART_BOT_TENON_LEN + P.SLOT_CLEAR:g};",
        f"   сквозные, «косточки» R{P.DOGBONE_R:g}.",
        f"3. Оси пазов: длинные стенки ±{PR.LONG_Y:g},",
        f"   короткие ±{PR.SHORT_X:g} от центра;",
        f"   стенки на {P.INSET:g} от кромки плиты.",
        "4. Плиты симметричны, кроме P1B:",
        f"   метки опор (Ø{P.TOOL_D:g}, гл. {P.MARK_DEPTH:g}) — наружу,",
        "   вниз.",
        "5. P2B: футорки — со стороны стенок",
        "   (внутрь модуля), ДО склейки каркаса.",
        "6. P2T сплошная, шипы вровень с пластью.",
        "7. Кромки плит не скруглять: на них",
        "   на скобу крепится картон 3 мм.",
    ]
    pg.notes(338, 280, "Указания", lines, 6.2, 4.0)
    pg.save(pdf, out / "sheet_2_plates.png")


# ====================================================================== лист 3
TENONS = {
    "W1L": (P.LONG_TENONS, P.TENON_LEN, P.LONG_TENONS, P.TENON_LEN),
    "W2L": (P.LONG_TENONS, P.TENON_LEN, P.LONG_TENONS, P.TENON_LEN),
    "W1S": (P.SHORT_TENONS, P.TENON_LEN, P.SHORT_TENONS, P.TENON_LEN),
    "W2S": (P.SHORT_TENONS, P.TENON_LEN, P.SHORT_TENONS, P.TENON_LEN),
    "W2P": (P.PART_TOP_TENONS, P.TENON_LEN, P.PART_BOT_TENONS, P.PART_BOT_TENON_LEN),
}


def chain(pg, x0, y_from, y_dim, s, marks, size=5.2):
    """Цепочка размеров по точкам marks (мм модели от левого торца)."""
    for a, b in zip(marks, marks[1:]):
        pg.dim_h(x0 + a / s, x0 + b / s, y_from, y_dim, f"{b - a:g}", size)


def wall_view(pg, part, x0, y0, s):
    pg.part(part, s, x0, y0)
    w, h = part.size()
    top_c, top_l, bot_c, bot_l = TENONS[part.key]
    pg.dim_v(y0, y0 + h / s, x0, x0 - 6, f"{h:g}")
    pg.dim_v(y0 + P.T / s, y0 + (h - P.T) / s, x0 + w / s, x0 + w / s + 6, f"{h - 2 * P.T:g}", 6)
    top = [0.0] + [v for c in top_c for v in (w / 2 + c - top_l / 2, w / 2 + c + top_l / 2)] + [w]
    chain(pg, x0, y0 + h / s, y0 + h / s + 4, s, top)
    if (bot_c, bot_l) != (top_c, top_l):
        bot = [0.0] + [v for c in bot_c for v in (w / 2 + c - bot_l / 2, w / 2 + c + bot_l / 2)] + [w]
        chain(pg, x0, y0, y0 - 4, s, bot)
        pg.dim_h(x0, x0 + w / s, y0 - 4, y0 - 11, f"{w:g}")
    else:
        pg.dim_h(x0, x0 + w / s, y0, y0 - 6, f"{w:g}")
    pg.text(x0, y0 + h / s + 12, f"{part.key} — {part.name}, {part.qty} шт ({part.module} модуль)", 7.5,
            weight="bold")
    if part.note:
        pg.text(x0, y0 + h / s + 8.5, part.note, 6)


def sheet_walls(pdf, out):
    pg = Page("Стенки и перегородка. Узел шипа", 3, TOTAL, "1:5; 1:1")
    s = 5
    k = PR.by_key()
    wall_view(pg, k["W1L"], 40, 222, s)
    wall_view(pg, k["W2L"], 40, 150, s)
    wall_view(pg, k["W1S"], 200, 222, s)
    wall_view(pg, k["W2S"], 200, 150, s)
    wall_view(pg, k["W2P"], 300, 150, s)
    lines = [
        f"Шипы {P.TENON_LEN:g} x {P.T:g} (у перегородки снизу {P.PART_BOT_TENON_LEN:g}) — сверху и снизу,",
        "одинаково; вровень с наружной пластью плит.",
        "Нижние шипы перегородки — только над рамкой P2B.",
        "Короткие стенки и перегородка встают между длинными:",
        "торцы на клей ПВА + 2 скобы/самореза 4x50 через длинную стенку.",
        "Стенки симметричны — ориентация по высоте не важна.",
    ]
    pg.notes(300, 262, "Шипы и стыки", lines, 6.2, 4.0)
    tenon_detail(pg, 40, 62)
    pg.save(pdf, out / "sheet_3_walls.png")


def tenon_detail(pg, ox, oy):
    """Узел В, 1:1: стенка шипом в плите (разрез вдоль стенки) и паз в плане."""
    from geom import dogboned, slot
    pg.text(ox - 10, oy + 55, "Узел В. Шип в пазу, 1:1", 9, weight="bold")
    tl, t, r, cl = P.TENON_LEN, P.T, P.DOGBONE_R, P.SLOT_CLEAR
    sh = 18.0                     # плечики по бокам шипа на виде
    body = 22.0
    a, b = sh, sh + tl
    wall = dogboned([(0, 0), (a, 0), (a, -t), (b, -t), (b, 0), (b + sh, 0), (b + sh, body), (0, body)],
                    {1, 4}, r)
    pg.shape([(ox + x, oy + 20 + y) for x, y in wall.points(0.05)], fc=C_PLY, ec=C_PLY_EDGE, lw=0.3,
             hatch="\\\\")
    for x0, x1 in ((-8, a - cl / 2), (b + cl / 2, b + sh + 8)):
        pg.shape([(ox + x0, oy + 20 - t), (ox + x1, oy + 20 - t), (ox + x1, oy + 20), (ox + x0, oy + 20)],
                 fc=C_PLY, ec=C_PLY_EDGE, lw=0.3, hatch="//")
    pg.dim_h(ox + a, ox + b, oy + 20 - t, oy + 20 - t - 6, f"{tl:g}", 6)
    pg.dim_v(oy + 20 - t, oy + 20, ox + b + sh + 8, ox + b + sh + 14, f"{t:g}", 6)
    pg.text(ox - 8, oy + 20 + body + 3, "стенка", 6)
    pg.text(ox - 8, oy + 20 - t - 4, "плита (разрез)", 6)
    # паз в плане
    ox2, oy2 = ox + 160, oy + 20
    sl = slot(0, 0, tl + cl, P.SLOT_W, r)
    pg.rect(ox2 - 45, oy2 - 17, 90, 34, fc=C_PLY, ec=C_PLY_EDGE, lw=0.3)
    pg.shape([(ox2 + x, oy2 + y) for x, y in sl.points(0.05)], fc="white", ec=C_LINE, lw=0.3)
    pg.dim_h(ox2 - (tl + cl) / 2, ox2 + (tl + cl) / 2, oy2 + P.SLOT_W / 2, oy2 + 21, f"{tl + cl:g}", 6)
    pg.dim_v(oy2 - P.SLOT_W / 2, oy2 + P.SLOT_W / 2, ox2 + 45, ox2 + 51, f"{P.SLOT_W:g}", 6)
    pg.leader((ox2 + (tl + cl) / 2 + 0.4, oy2 + P.SLOT_W / 2 + 0.4), (ox2 + 55, oy2 + 22), f"R{r:g}", 6)
    pg.text(ox2 - 45, oy2 - 22, "паз в плите, вид сверху", 6)
    pg.text(ox - 8, oy - 12, f"Паз длиннее шипа на {cl:g} и шире на {P.SLOT_W - t:g}. «Косточки» R{r:g} в корне шипа и в "
            f"углах паза — фреза Ø{P.TOOL_D:g} выбирает угол целиком,", 6)
    pg.text(ox - 8, oy - 16, "шип садится до упора плечиками. Если в цеху другая фреза — поправить TOOL_D и "
            "DOGBONE_R в params.py (R не меньше радиуса фрезы).", 6)



# ====================================================================== лист 4
def sheet_nesting(pdf, out, placed, stats, ply_area):
    pg = Page("Раскрой фанеры ф15 на ЧПУ", 4, TOTAL, "1:7")
    s = 7
    ox, oy = 30, 58
    sw, sh = P.SHEET
    pg.rect(ox, oy, sw / s, sh / s, fc="#f7f3ea", ec=C_LINE, lw=0.35)
    for pl in placed:
        pg.part(pl.part, s, ox, oy)
        x0, y0, x1, y1 = pl.part.outline.bbox()
        win = [c for k, c in pl.part.holes if k == "window"]
        if win:
            wy0 = win[0].bbox()[1]
            tx, ty = x0 + 212, (y0 + wy0) / 2
        else:
            tx, ty = (x0 + x1) / 2, (y0 + y1) / 2
        rot = 90 if (y1 - y0) > (x1 - x0) and not win else 0
        pg.text(ox + tx / s, oy + ty / s, pl.label, 7, ha="center", va="center", weight="bold", rotation=rot)
    pg.dim_h(ox, ox + sw / s, oy, oy - 6, f"{sw:g}")
    pg.dim_v(oy, oy + sh / s, ox, ox - 5, f"{sh:g}")
    pg.text(ox, oy + sh / s + 3, f"Лист {sw:g} x {sh:g}, ноль — левый нижний угол; отступ {P.SHEET_MARGIN:g}, "
            f"зазор {P.PART_GAP:g}", 6.5)

    rows = []
    for p in PR.all_parts():
        w, h = p.size()
        rows.append([p.key, p.name, p.module, p.qty, f"{w:g} x {h:g}"])
    y = pg.table(268, 285, [("Дет.", 13, "l"), ("Наименование", 52, "l"), ("Модуль", 17, "l"),
                            ("Шт", 8, "c"), ("Габарит", 30, "c")], rows, 6.2, 4.8)
    use = ply_area / (sw * sh / 1e6) * 100
    mass = ply_area * P.T / 1000 * P.PLY_DENSITY
    lines = [
        f"Деталей: {sum(p.qty for p in PR.all_parts())} шт, площадь {ply_area:.2f} м², "
        f"использование листа {use:.0f}%.",
        f"Масса фанеры каркаса ≈ {mass:.1f} кг.",
        f"УП: nc/sheet_1.tap — фреза Ø{P.TOOL_D:g}, S{P.SPINDLE}, F{P.F_CUT:g}/{P.F_PLUNGE:g},",
        f"глубина {P.CUT_DEPTH:g} за {len(__import__('cam').pass_depths())} прохода, "
        f"перемычки {P.TAB_W:g}x{P.TAB_H:g} ({P.TABS_OUTER} на деталь, {P.TABS_WINDOW} на окно).",
        f"Путь реза {stats['cut_m']:.0f} м, ≈ {stats['minutes']:.0f} мин.",
        "Порядок: метки опор -> пазы (выбираются целиком) -> отверстия",
        "-> детали в окнах -> окна рамок -> наружные контуры.",
        "Короткие стенки W1S-1, W2S-1, W2S-2 лежат в окнах рамок.",
        "УП сделана типовым постпроцессором (Mach3/NcStudio),",
        "НЕ цеховым: перед резкой проверить в симуляторе станка",
        "или пересобрать цеховым постом из dxf/sheet_1.dxf.",
        "Слои DXF: CUT_OUT, CUT_IN, MARK_D2, LABEL, SHEET.",
    ]
    pg.notes(268, y - 8, "Раскрой и УП", lines, 6.2, 4.0)
    pg.save(pdf, out / "sheet_4_nesting.png")


# ====================================================================== лист 5
def draw_pack(pg, packed, ox, oy, s, width, length, arrow=None, label_fmt=None, fc="#fff"):
    pg.rect(ox, oy, width / s, length / s, fc="#f4f4f4", ec=C_LINE, lw=0.25)
    for p, i, x, y in packed:
        px, py = ox + x / s, oy + y / s
        if p.r:
            pg.contour(rounded_rect(p.w, p.h, p.r), s, px + p.w / 2 / s, py + p.h / 2 / s, fc=fc, ec=C_LINE,
                       lw=0.25)
        else:
            pg.rect(px, py, p.w / s, p.h / s, fc=fc, ec=C_LINE, lw=0.25)
        pg.text(px + p.w / 2 / s, py + p.h / 2 / s + 1.2, p.key, 6.5, ha="center", va="center", weight="bold")
        pg.text(px + p.w / 2 / s, py + p.h / 2 / s - 2.2, f"{p.w:g} x {p.h:g}", 5.8, ha="center", va="center")
        if arrow:
            pg.ax.annotate("", xy=(px + p.w / s - 4, py + 2), xytext=(px + p.w / s - 4, py + p.h / s - 2),
                           arrowprops=dict(arrowstyle="-|>", lw=0.5, color="#555", mutation_scale=5))


def sheet_soft(pdf, out):
    pg = Page("Раскрой ППУ, холкона, ткани. Картон", 5, TOTAL, "1:10; 1:5")
    s = 10
    # --- ткань
    fab = soft.fabric_pieces()
    packed, fabric_used = soft.shelf_pack(fab, P.FABRIC_ROLL_W)
    ox, oy = 38, 282 - fabric_used / s
    pg.text(ox - 8, 285.5, f"Ткань {P.FABRIC_ROLL_W:g}: {fabric_used / 1000:.2f} м.п.  (стрелка — ворс)", 8.5,
            weight="bold")
    draw_pack(pg, packed, ox, oy, s, P.FABRIC_ROLL_W, fabric_used, arrow=True, fc="#f1d5cc")
    pg.dim_v(oy, oy + fabric_used / s, ox, ox - 5, f"{fabric_used:g}")
    pg.text(ox + P.FABRIC_ROLL_W / s / 2, oy - 3.5, f"ширина рулона {P.FABRIC_ROLL_W:g}", 6, ha="center",
            color=C_DIM)
    # --- ППУ боковая
    lay = soft.foam_layouts()
    fw, fh = P.FOAM_SHEET
    x2 = 200
    packed, _ = lay[P.FOAM_SIDE]
    oy2 = 282 - fh / s
    pg.text(x2, 285.5, f"ППУ {P.FOAM_SIDE} 30 мм — лист {fw:g}x{fh:g}", 8.5, weight="bold")
    draw_pack(pg, packed, x2, oy2, s, fw, fh, fc=C_FOAM)
    # --- ППУ сиденья
    packed, _ = lay[P.FOAM_SEAT]
    oy3 = 115
    pg.text(x2, 172, f"ППУ {P.FOAM_SEAT} 30 мм — сиденье", 8.5, weight="bold")
    draw_pack(pg, packed, x2, oy3, s, 700, 490, fc=C_FOAM)
    edge_detail(pg, 292, 118)
    # --- таблица
    rows = []
    for p in soft.foam_pieces() + soft.holcon_pieces() + soft.fabric_pieces() + soft.other_pieces():
        rows.append([p.key, p.name, p.qty, f"{p.w:g} x {p.h:g}" + (f" R{p.r:g}" if p.r else ""), p.note])
    pg.table(28, 80, [("Дет.", 13, "l"), ("Наименование", 60, "l"), ("Шт", 7, "c"), ("Размер", 30, "c"),
                      ("Примечание", 88, "l")], rows, 5.5, 4.2)
    hol = soft.area_m2(soft.holcon_pieces())
    side = soft.area_m2([p for p in soft.foam_pieces() if P.FOAM_SIDE in p.material])
    seat = soft.area_m2([p for p in soft.foam_pieces() if P.FOAM_SEAT in p.material])
    lines = [
        f"ППУ {P.FOAM_SIDE}: {side:.2f} м²; {P.FOAM_SEAT}: {seat:.2f} м² (толщина 30).",
        f"Холкон {P.HOLCON_GSM} г/м²: {hol:.2f} м² (рулон {P.HOLCON_ROLL_W:g} -> "
        f"≈{hol / P.HOLCON_ROLL_W * 1000 * 1.1:.1f} м.п.).",
        f"Ткань: {fabric_used / 1000:.2f} м.п. при ширине {P.FABRIC_ROLL_W:g} + 5% на подгонку.",
        "Картон 3 мм: C-UP, C-LO. Спанбонд — на дно после стяжки.",
        "ППУ — клей распылением; холкон — лёгким слоем, без пятен.",
    ]
    pg.notes(236, 100, "Расход", lines, 6.0, 3.8)
    pg.save(pdf, out / "sheet_5_soft.png")


def edge_detail(pg, ox, oy):
    """Профиль боковой ППУ нижнего модуля, 1:5."""
    s = 5
    pg.text(ox, oy + 49, "Профиль боковины ППУ, 1:5", 7.5, weight="bold")
    r = P.EDGE_R
    for i, (hh, name, top_r) in enumerate(((P.HF_LO, "F-LO", True), (P.HF_UP, "F-UP", False))):
        x0 = ox + i * 25
        c = Contour([(0, 0, 0), (P.FOAM - r, 0, K90), (P.FOAM, r, 0)]
                    + ([(P.FOAM, hh - r, K90), (P.FOAM - r, hh, 0)] if top_r else [(P.FOAM, hh, 0)])
                    + [(0, hh, 0)])
        pg.poly([(x0 + x / s, oy + y / s) for x, y in c.points(0.3)], fc=C_FOAM, ec=C_LINE, lw=0.25)
        pg.text(x0, oy - 3.5, f"{name}\nh{hh:g}", 5.8)
    pg.text(ox + 50, oy + 40, f"наружу ->\nкромки R{r:g}\n(срез ножом\nпо шаблону)", 5.8)


# ====================================================================== лист 6
def iso(x, y, z, s, ox, oy):
    c, sn = math.cos(math.radians(30)), math.sin(math.radians(30))
    return ox + (x - y) * c / s, oy + ((x + y) * sn + z) / s


def prism(pg, outer, holes, z0, z1, s, ox, oy, fc, ec=C_PLY_EDGE):
    """Призма из контура (списки точек модели). Рисуются видимые боковые грани и верх."""
    faces = []
    for ring, is_hole in [(outer, False)] + [(h, True) for h in holes]:
        n = len(ring)
        area = sum(ring[i][0] * ring[(i + 1) % n][1] - ring[(i + 1) % n][0] * ring[i][1] for i in range(n))
        ccw = area > 0
        for i in range(n):
            (ax, ay), (bx, by) = ring[i], ring[(i + 1) % n]
            dx, dy = bx - ax, by - ay
            nx, ny = (dy, -dx) if ccw else (-dy, dx)        # наружу от материала
            if is_hole:
                nx, ny = -nx, -ny
            if -nx - ny <= 0:
                continue
            depth = -(ax + bx) / 2 - (ay + by) / 2
            faces.append((depth, [iso(ax, ay, z0, s, ox, oy), iso(bx, by, z0, s, ox, oy),
                                  iso(bx, by, z1, s, ox, oy), iso(ax, ay, z1, s, ox, oy)]))
    for _, f in sorted(faces, key=lambda t: t[0]):
        pg.poly(f, fc=_shade(fc), ec=ec, lw=0.08)
    pg.shape([iso(x, y, z1, s, ox, oy) for x, y in outer],
             [[iso(x, y, z1, s, ox, oy) for x, y in h] for h in holes], fc=fc, ec=ec, lw=0.2)


def _shade(c):
    import matplotlib.colors as mc
    r, g, b = mc.to_rgb(c)
    return (r * 0.8, g * 0.8, b * 0.8)


def sheet_assembly(pdf, out):
    pg = Page("Схема сборки", 6, TOTAL, "б/м")
    s = 8.5
    ox, oy = 132, 78
    k = PR.by_key()
    G_WALL, G_MOD, G_LEG = 110.0, 170.0, 150.0
    z = 0.0
    labels = []

    def plate(key, zz):
        p = k[key]
        prism(pg, p.outline.points(2), [c.points(2) for _, c in p.holes if c.circle is None], zz, zz + P.T,
              s, ox, oy, C_PLY)
        labels.append((key, iso(-P.PL / 2 + 40, -P.PW / 2 + 40, zz + P.T, s, ox, oy)))

    def box_walls(hf, zz, partition):
        body = hf - 2 * P.T
        items = []
        for sy in (-1, 1):
            y0 = sy * PR.LONG_Y - P.T / 2
            items.append((sy * PR.LONG_Y,
                          [(-P.WALL_LONG / 2, y0), (P.WALL_LONG / 2, y0), (P.WALL_LONG / 2, y0 + P.T),
                           (-P.WALL_LONG / 2, y0 + P.T)]))
        for sx in (-1, 1):
            x0 = sx * PR.SHORT_X - P.T / 2
            items.append((sx * PR.SHORT_X, [(x0, -P.WALL_SHORT / 2), (x0 + P.T, -P.WALL_SHORT / 2),
                                           (x0 + P.T, P.WALL_SHORT / 2), (x0, P.WALL_SHORT / 2)]))
        if partition:
            items.append((0.0, [(-P.T / 2, -P.WALL_SHORT / 2), (P.T / 2, -P.WALL_SHORT / 2),
                                (P.T / 2, P.WALL_SHORT / 2), (-P.T / 2, P.WALL_SHORT / 2)]))
        for _, pts in sorted(items, key=lambda t: -t[0]):
            prism(pg, pts, [], zz, zz + body, s, ox, oy, "#e3c089")

    lx, ly = P.PL / 2 - P.LEG_INSET, P.PW / 2 - P.LEG_INSET
    for cx, cy in sorted(PR.four(lx, ly), key=lambda t: -(t[0] + t[1])):
        c = [(cx + P.LEG_D / 2 * math.cos(a / 12 * math.pi), cy + P.LEG_D / 2 * math.sin(a / 12 * math.pi))
             for a in range(24)]
        prism(pg, c, [], z, z + P.LEG_H, s, ox, oy, "#333", ec="#111")
    labels.append(("опоры 4 шт", iso(-lx, -ly, P.LEG_H / 2, s, ox, oy)))
    z += P.LEG_H + G_LEG
    z_lo0 = z
    plate("P1B", z)
    z += P.T + G_WALL
    box_walls(P.HF_LO, z, False)
    labels.append(("W1L x2, W1S x2", iso(-P.WALL_LONG / 2 + 60, -PR.LONG_Y, z + 90, s, ox, oy)))
    z += P.HF_LO - 2 * P.T + G_WALL
    plate("P1T", z)
    z_p1t = z + P.T
    z_lo1 = z_p1t
    z += P.T + G_MOD
    z_p2b = z
    z_up0 = z
    plate("P2B", z)
    z += P.T + G_WALL
    box_walls(P.HF_UP, z, True)
    labels.append(("W2L x2, W2S x2, W2P", iso(-P.WALL_LONG / 2 + 60, -PR.LONG_Y, z + 75, s, ox, oy)))
    z += P.HF_UP - 2 * P.T + G_WALL
    plate("P2T", z)
    z_up1 = z + P.T
    bx, by = P.BOLT_XY
    for x, y in PR.four(bx, by):
        a = iso(x, y, z_p1t - P.T - 60, s, ox, oy)
        b = iso(x, y, z_p2b + P.T + 20, s, ox, oy)
        pg.line([a, b], lw=0.2, color="#b00", ls="-.")
    labels.append(("болты M8x40 снизу -> футорки P2B", iso(-bx, -by, (z_p1t + z_p2b) / 2, s, ox, oy)))
    for t, (x, y) in labels:
        pg.leader((x, y), (28, y), t, 6.2)
    # скобки модулей справа
    xr = ox + 454 / s + 4
    for (z0, z1, t) in ((z_lo0, z_lo1, "НИЖНИЙ\nмодуль"), (z_up0, z_up1, "ВЕРХНИЙ\nмодуль")):
        y0 = oy + (50 + z0) / s          # правый угол плит (312; -212)
        y1 = oy + (50 + z1) / s
        pg.line([(xr, y0), (xr + 2, y0), (xr + 2, y1), (xr, y1)], lw=0.3)
        pg.text(xr + 4, (y0 + y1) / 2, t, 7, va="center", weight="bold")

    steps = [
        "1. Фрезеровать лист (лист 4). Снять перемычки, зачистить шипы.",
        "   Сухая сборка: шипы входят в пазы от руки / киянкой.",
        "2. P2B: забить 4 футорки M8 со стороны стенок.",
        "3. Верхний модуль: P2T пластью вниз -> стенки W2L, W2S и",
        "   перегородка W2P шипами в пазы на клей ПВА D3 -> P2B сверху.",
        "   Углы стенок — клей + 2 скобы/самореза через длинную стенку.",
        "   Проверить диагонали, стянуть струбцинами до схватывания.",
        "4. Нижний модуль так же: P1B -> W1L, W1S -> P1T.",
        "5. Картон 3 мм по периметру обоих каркасов на скобу к",
        "   кромкам плит (стык по середине торца).",
        f"6. ППУ {P.FOAM_SIDE} 30 на картон (клей), кромки R{P.EDGE_R:g} наружу.",
        f"   Верхний модуль: ППУ {P.FOAM_SEAT} 30 на P2T, кромка сиденья",
        "   на клей с обжимом на торец боковины.",
        f"7. Холкон {P.HOLCON_GSM}: верх и бока верхнего, бока нижнего.",
        "8. Чехлы. Верхний: верх + бортик, шов по ребру без канта, низ",
        "   под P2B на скобу. Нижний: бортик под P1T и под P1B на скобу.",
        f"   Скоба в {P.FABRIC_STAPLE_IN:g} мм от кромки; отверстия болтов не зашить.",
        "   Ворс — сверху вниз на обоих модулях.",
        "9. Опоры: сверла Ø3 насквозь по меткам P1B до обивки, после",
        "   обивки найти шилом, опоры на саморезы 4x25.",
        "10. Прокладки 2 мм на болты, поставить верхний модуль на нижний,",
        "   болты M8x40 с шайбой снизу через окно P1B -> в футорки.",
        "11. Спанбонд на дно (закрыть окно P1B) на скобу.",
    ]
    pg.notes(232, 285, "Порядок сборки", steps, 6.1, 3.75)
    rows = [
        [P.BOLT, 4], [P.TNUT, 4], ["Прокладка 2 мм (фетр/ткань) Ø30", 4],
        [P.LEG, 4], [P.LEG_SCREW, 4], ["Клей ПВА D3 (столярный)", "0,2 кг"],
        ["Скоба/саморез 4x50 в углы коробок", 16], ["Скоба мебельная 10 мм (картон, ткань)", "~400"],
        ["Клей для ППУ (баллон)", "0,5 л"],
    ]
    pg.table(232, 190 - 2 * 3.75 - 70, [("Крепёж и расходники на 1 пуф", 150, "l"), ("Кол.", 30, "c")],
             rows, 6.0, 4.5)
    pg.save(pdf, out / "sheet_6_assembly.png")


# ====================================================================== альбом
def build_album(out, placed, stats, ply_area):
    (out / "png").mkdir(parents=True, exist_ok=True)
    with PdfPages(out / "album_A3.pdf") as pdf:
        sheet_general(pdf, out / "png")
        sheet_plates(pdf, out / "png")
        sheet_walls(pdf, out / "png")
        sheet_nesting(pdf, out / "png", placed, stats, ply_area)
        sheet_soft(pdf, out / "png")
        sheet_assembly(pdf, out / "png")
