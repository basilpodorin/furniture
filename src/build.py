"""Генерация шаблонов: DXF 1:1 (по одному на деталь + листы раскроя) и PDF для печати 1:1.

Запуск:  python3 src/build.py            (результат — в templates/)
Зависимости: ezdxf, shapely, matplotlib
"""
import math
import os

import ezdxf
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from shapely.geometry import Point, Polygon

import geometry as g

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
OUT = os.path.join(ROOT, "templates")
SHEET_W, SHEET_H = 2440.0, 1220.0      # лист МДФ/фанеры, мм
MARGIN, GAP = 10.0, 15.0
MARK_LEN = 30.0                        # длина метки центра паза от грани внутрь, мм

SLOT_W, SLOT_PITCH, SLOT_DEPTH, SLOT_LEN = 10.0, 20.0, 21.0, 30.0
SLOT_NOTE = ("2 паза %gx%g (30 — по толщине 70, по центру), глубина %g, шаг %g между центрами, "
             "симметрично от центра грани" % (SLOT_W, SLOT_LEN, SLOT_DEPTH, SLOT_PITCH))


def poly(verts):
    return Polygon(g.sample(verts, 0.5))


def face_marks(part):
    """Метки центра грани: [(начало, конец, подпись)] — линия от грани внутрь детали."""
    pl = poly(part.verts)
    res = []
    for f in part.faces:
        mx, my = f.mid
        dx, dy = f.q[0] - f.p[0], f.q[1] - f.p[1]
        n = (-dy / f.length, dx / f.length)
        if not pl.contains(Point(mx + n[0] * 1.0, my + n[1] * 1.0)):
            n = (-n[0], -n[1])
        res.append(((mx, my), (mx + n[0] * MARK_LEN, my + n[1] * MARK_LEN), f.name))
    return res


def pockets(part):
    """Контуры двух пазов на каждой торцевой грани в плане: прямоугольники 10 x 21 внутрь детали."""
    res = []
    for (m, e, _), f in zip(face_marks(part), part.faces):
        ux, uy = (f.q[0] - f.p[0]) / f.length, (f.q[1] - f.p[1]) / f.length
        nx, ny = (e[0] - m[0]) / MARK_LEN, (e[1] - m[1]) / MARK_LEN
        for sgn in (-1, 1):
            cx, cy = m[0] + ux * sgn * SLOT_PITCH / 2, m[1] + uy * sgn * SLOT_PITCH / 2
            h = SLOT_W / 2
            res.append([(cx - ux * h, cy - uy * h), (cx + ux * h, cy + uy * h),
                        (cx + ux * h + nx * SLOT_DEPTH, cy + uy * h + ny * SLOT_DEPTH),
                        (cx - ux * h + nx * SLOT_DEPTH, cy - uy * h + ny * SLOT_DEPTH)])
    return res


def half_marks(part):
    """Метки осей для половинных шаблонов столешницы/подстолья (после поворота: прямая кромка x=0)."""
    if not part.key.endswith("_half"):
        return []
    x0, y0, x1, y1 = part.bbox()
    ym = (y0 + y1) / 2
    L = 80.0
    return [((x0, ym), (x0 + L, ym)), ((x1 - L, ym), (x1, ym)),     # продольная ось на торцах
            ((x0, y0), (x0, y0 + 25)), ((x0, y1 - 25), (x0, y1)),    # края оси симметрии
            ((x0, ym - 40), (x0, ym + 40))]


def label_lines(part):
    b = part.bbox()
    return ["%s — %s" % (part.title, part.qty),
            "габарит %.2f x %.2f мм, масштаб 1:1" % (b[2] - b[0], b[3] - b[1])]


def new_doc():
    doc = ezdxf.new("R2010", setup=True)
    doc.units = ezdxf.units.MM
    doc.layers.add("CUT", color=1)       # контур шаблона — режется
    doc.layers.add("MARK", color=5)      # метки — гравировка/разметка, не резать
    doc.layers.add("TEXT", color=7)      # подписи
    doc.layers.add("SHEET", color=8)     # границы листа
    return doc


def draw_part(msp, part, dx=0.0, dy=0.0, label_dy=-8.0):
    """Рисует деталь со сдвигом (dx, dy): контур, метки, подпись."""
    verts = g.transform(part.verts, dx=dx, dy=dy)
    msp.add_lwpolyline([(x, y, 0, 0, b) for x, y, b in verts], format="xyseb",
                       close=True, dxfattribs={"layer": "CUT"})
    for a, b, name in face_marks(part):
        msp.add_line((a[0] + dx, a[1] + dy), (b[0] + dx, b[1] + dy), dxfattribs={"layer": "MARK"})
        msp.add_text(name, height=4, dxfattribs={"layer": "MARK"}).set_placement(
            (b[0] + dx + 2, b[1] + dy + 2))
    for rect in pockets(part):
        msp.add_lwpolyline([(x + dx, y + dy) for x, y in rect], close=True, dxfattribs={"layer": "MARK"})
    for a, b in half_marks(part) + part.marks:
        msp.add_line((a[0] + dx, a[1] + dy), (b[0] + dx, b[1] + dy), dxfattribs={"layer": "MARK"})
    for hole in part.holes:
        msp.add_lwpolyline([(x, y, 0, 0, bl) for x, y, bl in g.transform(hole, dx=dx, dy=dy)],
                           format="xyseb", close=True, dxfattribs={"layer": "CUT"})
    x0, y0, x1, y1 = part.bbox()
    ty = y0 + dy + label_dy
    for i, line in enumerate(label_lines(part)):
        msp.add_text(line, height=6, dxfattribs={"layer": "TEXT"}).set_placement(
            (x0 + dx, ty - i * 9))


def write_part_dxf(part):
    doc = new_doc()
    x0, y0, _, _ = part.bbox()
    msp = doc.modelspace()
    draw_part(msp, part, dx=-x0, dy=-y0, label_dy=-30)
    if part.note:
        msp.add_text(part.note, height=5, dxfattribs={"layer": "TEXT"}).set_placement((0, -52))
    if part.faces:
        msp.add_text("Слой MARK: центр грани и пазы в плане. " + SLOT_NOTE, height=5,
                     dxfattribs={"layer": "TEXT"}).set_placement((0, -62))
    path = os.path.join(OUT, "dxf", part.key + ".dxf")
    doc.saveas(path)
    return path


def write_sheet(name, placements):
    """placements: [(part, x, y)] — положение левого нижнего угла габарита детали на листе."""
    doc = new_doc()
    msp = doc.modelspace()
    msp.add_lwpolyline([(0, 0), (SHEET_W, 0), (SHEET_W, SHEET_H), (0, SHEET_H)], close=True,
                       dxfattribs={"layer": "SHEET"})
    msp.add_text("Лист %gx%g, МДФ/фанера 18 мм (рекомендуется)" % (SHEET_W, SHEET_H), height=8,
                 dxfattribs={"layer": "SHEET"}).set_placement((MARGIN, SHEET_H + 12))
    for part, x, y in placements:
        x0, y0, x1, y1 = part.bbox()
        assert x + (x1 - x0) <= SHEET_W - MARGIN + 1e-6 and y + (y1 - y0) <= SHEET_H - MARGIN + 1e-6, part.key
        draw_part(msp, part, dx=x - x0, dy=y - y0, label_dy=-22)
    path = os.path.join(OUT, "dxf", name + ".dxf")
    doc.saveas(path)
    return path


def nest():
    P = {p.key: p for p in g.all_parts()}
    sheets = {}
    # лист 1: половина столешницы слева, мелкие детали справа
    sx = MARGIN + 1250.0 + 25.0
    top, lo = SHEET_H - MARGIN - 135.0, SHEET_H - MARGIN - 135.0 - 250.0
    sheets["sheet1_tabletop_half_and_small_parts"] = [
        (P["tabletop_half"], MARGIN, MARGIN + 60),
        (P["leg"], sx, SHEET_H - MARGIN - 115.0 - 40),
        (P["upper"], sx + 741.26 + GAP, SHEET_H - MARGIN - 79.3 - 40),
        (P["lower"], sx, SHEET_H - MARGIN - 330),
        (P["hub"], sx + 255.0 + GAP + 40, SHEET_H - MARGIN - 330 - 40),
    ]
    sheets["sheet2_subplate_half"] = [(P["subplate_half"], MARGIN, MARGIN + 60),
                                      (P["mortise_jig"], MARGIN + 1225.0 + 40, MARGIN + 60)]
    return {n: write_sheet(n, pl) for n, pl in sheets.items()}


# ------------------------------------------------------------------ PDF ---

A4 = (297.0, 210.0)  # альбомная, мм
PAD = 10.0
OVERLAP = 10.0


def _fig():
    fig = plt.figure(figsize=(A4[0] / 25.4, A4[1] / 25.4))
    return fig


def draw_outline(ax, part, lw=1.0):
    pts = g.sample(part.verts, 0.5)
    xs, ys = zip(*(pts + [pts[0]]))
    ax.plot(xs, ys, color="black", lw=lw, solid_capstyle="round")
    for a, b, name in face_marks(part):
        ax.plot([a[0], b[0]], [a[1], b[1]], color="tab:blue", lw=0.8)
        ax.text(b[0], b[1], " " + name, color="tab:blue", fontsize=6)
    for rect in pockets(part):
        xs, ys = zip(*(rect + [rect[0]]))
        ax.plot(xs, ys, color="tab:blue", lw=0.8)
    for hole in part.holes:
        pts = g.sample(hole, 0.5)
        xs, ys = zip(*(pts + [pts[0]]))
        ax.plot(xs, ys, color="black", lw=lw)
    for a, b in half_marks(part) + part.marks:
        ax.plot([a[0], b[0]], [a[1], b[1]], color="tab:blue", lw=0.8)


def overview_page(pdf, part):
    fig = _fig()
    x0, y0, x1, y1 = part.bbox()
    w, h = x1 - x0, y1 - y0
    ax = fig.add_axes([PAD / A4[0], 55 / A4[1], (A4[0] - 2 * PAD) / A4[0], (A4[1] - 55 - 20) / A4[1]])
    draw_outline(ax, part)
    ax.set_aspect("equal")
    ax.set_xlim(x0 - 0.04 * w, x1 + 0.04 * w)
    ax.set_ylim(y0 - 0.1 * h, y1 + 0.1 * h)
    ax.axis("off")
    lines = ["%s" % part.title, "Количество: %s" % part.qty,
             "Габарит: %.2f x %.2f мм" % (w, h)]
    if part.note:
        lines.append(part.note)
    if part.faces:
        lines.append("Синее — центр торцевой грани и пазы под ламели: " + SLOT_NOTE + ".")
    fig.text(PAD / A4[0], 1 - 12 / A4[1], lines[0], fontsize=14, weight="bold", va="top")
    fig.text(PAD / A4[0], 40 / A4[1], "\n".join(lines[1:]), fontsize=8, va="top")
    pdf.savefig(fig)
    plt.close(fig)


def tiled_pages(pdf, part):
    """Печать 1:1 на листах A4 (альбомных) с нахлёстом и линейкой 100 мм на каждом листе."""
    x0, y0, x1, y1 = part.bbox()
    uw, uh = A4[0] - 2 * PAD, A4[1] - 2 * PAD
    nx = max(1, math.ceil((x1 - x0 - OVERLAP) / (uw - OVERLAP)))
    ny = max(1, math.ceil((y1 - y0 - OVERLAP) / (uh - OVERLAP)))
    # центрируем сетку относительно детали
    gx = x0 - ((nx * (uw - OVERLAP) + OVERLAP) - (x1 - x0)) / 2
    gy = y0 - ((ny * (uh - OVERLAP) + OVERLAP) - (y1 - y0)) / 2
    k = 0
    for j in range(ny - 1, -1, -1):
        for i in range(nx):
            k += 1
            tx, ty = gx + i * (uw - OVERLAP), gy + j * (uh - OVERLAP)
            fig = _fig()
            ax = fig.add_axes([PAD / A4[0], PAD / A4[1], uw / A4[0], uh / A4[1]])
            draw_outline(ax, part, lw=0.9)
            ax.set_xlim(tx, tx + uw)
            ax.set_ylim(ty, ty + uh)
            ax.set_aspect("equal")
            ax.set_xticks([]); ax.set_yticks([])
            for sp in ax.spines.values():
                sp.set_color("0.6"); sp.set_linewidth(0.5)
            # метки нахлёста и совмещения
            for ox in (tx + OVERLAP, tx + uw - OVERLAP):
                ax.plot([ox, ox], [ty, ty + 6], color="0.5", lw=0.5)
                ax.plot([ox, ox], [ty + uh - 6, ty + uh], color="0.5", lw=0.5)
            for oy in (ty + OVERLAP, ty + uh - OVERLAP):
                ax.plot([tx, tx + 6], [oy, oy], color="0.5", lw=0.5)
                ax.plot([tx + uw - 6, tx + uw], [oy, oy], color="0.5", lw=0.5)
            ax.plot([tx + 15, tx + 115], [ty + 15, ty + 15], color="red", lw=1.0)
            for xx in (tx + 15, tx + 115):
                ax.plot([xx, xx], [ty + 12, ty + 18], color="red", lw=1.0)
            ax.text(tx + 15, ty + 20, "проверка масштаба: отрезок = 100 мм", color="red", fontsize=6)
            ax.text(tx + uw - 3, ty + uh - 3,
                    "%s  лист %d/%d (колонка %d, ряд %d)" % (part.title, k, nx * ny, i + 1, ny - j),
                    ha="right", va="top", fontsize=7, color="0.3")
            pdf.savefig(fig)
            plt.close(fig)
    return nx * ny


def build_pdf():
    parts = {p.key: p for p in g.all_parts()}
    path = os.path.join(OUT, "pdf", "templates_print.pdf")
    counts = {}
    with PdfPages(path) as pdf:
        for p in g.all_parts():
            overview_page(pdf, p)
        for key in ("leg", "upper", "lower", "hub", "mortise_jig"):
            counts[key] = tiled_pages(pdf, parts[key])
    return path, counts


def main():
    os.makedirs(os.path.join(OUT, "dxf"), exist_ok=True)
    os.makedirs(os.path.join(OUT, "pdf"), exist_ok=True)
    for p in g.all_parts():
        print(write_part_dxf(p))
    for n, path in nest().items():
        print(path)
    path, counts = build_pdf()
    print(path, counts)


if __name__ == "__main__":
    main()
