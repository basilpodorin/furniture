"""Базовые средства листов А3: рамка, штамп, контуры в масштабе, размеры, таблицы.

Все координаты — мм на листе (А3 альбомный 420 x 297).
"""
import datetime

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt                       # noqa: E402
from matplotlib.patches import PathPatch, Polygon as MPoly   # noqa: E402
from matplotlib.path import Path                      # noqa: E402

import params as P                                    # noqa: E402

PT = 72 / 25.4          # мм -> pt
C_PLY = "#ecd2a6"
C_PLY_EDGE = "#7a5a3a"
C_FOAM = "#f4e7a8"
C_CARD = "#9a9a9a"
C_FABRIC = "#b8624e"
C_HOLCON = "#dbe8f5"
C_LINE = "#1a1a1a"
C_DIM = "#1f3f7a"
DATE = datetime.date.today().strftime("%d.%m.%Y")


class Page:
    def __init__(self, title, num, total, scale=""):
        self.fig = plt.figure(figsize=(420 / 25.4, 297 / 25.4))
        ax = self.fig.add_axes([0, 0, 1, 1])
        ax.set_xlim(0, 420)
        ax.set_ylim(0, 297)
        ax.set_aspect("equal")
        ax.axis("off")
        self.ax = ax
        self._frame()
        self._stamp(title, num, total, scale)

    # ------------------------------------------------ рамка и штамп
    def _frame(self):
        self.rect(20, 5, 395, 287, lw=0.7)

    def _stamp(self, title, num, total, scale):
        x, y, w, h = 230, 5, 185, 40
        self.rect(x, y, w, h, lw=0.7)
        for yy in (y + 10, y + 20, y + 30):
            self.line([(x, yy), (x + w, yy)], lw=0.35)
        self.line([(x + 125, y), (x + 125, y + 30)], lw=0.35)
        self.line([(x + 155, y), (x + 155, y + 30)], lw=0.35)
        self.text(x + 3, y + 35, P.NAME, 10, weight="bold", va="center")
        self.text(x + 3, y + 25, title, 9, va="center")
        self.text(x + 3, y + 15, f"{P.PLY_NAME}; ткань {P.FABRIC_NAME}", 6.2, va="center")
        self.text(x + 3, y + 5, f"{P.CODE}   ·   {DATE}   ·   генерируется build.py", 6.2, va="center")
        self.text(x + 140, y + 25, "Масштаб", 6, ha="center", va="center")
        self.text(x + 140, y + 15, scale or "—", 8, ha="center", va="center")
        self.text(x + 170, y + 25, "Лист", 6, ha="center", va="center")
        self.text(x + 170, y + 15, f"{num} / {total}", 8, ha="center", va="center")
        self.text(x + 140, y + 5, "А3", 6, ha="center", va="center")

    # ------------------------------------------------ примитивы
    def text(self, x, y, s, size=7, **kw):
        kw.setdefault("ha", "left")
        kw.setdefault("va", "baseline")
        return self.ax.text(x, y, s, fontsize=size, color=kw.pop("color", C_LINE), **kw)

    def line(self, pts, lw=0.35, color=C_LINE, **kw):
        xs, ys = zip(*pts)
        self.ax.plot(xs, ys, lw=lw * PT, color=color,
                     solid_capstyle="butt", **kw)

    def rect(self, x, y, w, h, lw=0.35, fc="none", ec=C_LINE, **kw):
        self.ax.add_patch(plt.Rectangle((x, y), w, h, lw=lw * PT, fc=fc, ec=ec, **kw))

    def poly(self, pts, fc="none", ec=C_LINE, lw=0.35, **kw):
        self.ax.add_patch(MPoly(pts, closed=True, fc=fc, ec=ec, lw=lw * PT, **kw))

    def shape(self, outer, holes=(), fc="none", ec=C_LINE, lw=0.35, **kw):
        """Контур с отверстиями (списки точек листа)."""
        verts, codes = [], []
        for ring, ccw in [(outer, True)] + [(h, False) for h in holes]:
            ring = list(ring)
            area = sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(ring, ring[1:] + ring[:1]))
            if (area > 0) != ccw:
                ring = ring[::-1]
            verts += ring + [ring[0]]
            codes += [Path.MOVETO] + [Path.LINETO] * (len(ring) - 1) + [Path.CLOSEPOLY]
        self.ax.add_patch(PathPatch(Path(verts, codes), fc=fc, ec=ec, lw=lw * PT, **kw))

    # ------------------------------------------------ модель -> лист
    @staticmethod
    def tf(pts, s, ox, oy):
        return [(ox + x / s, oy + y / s) for x, y in pts]

    def contour(self, c, s, ox, oy, **kw):
        self.poly(self.tf(c.points(0.2), s, ox, oy), **kw)

    def part(self, part, s, ox, oy, fc=C_PLY, lw=0.35):
        outer = self.tf(part.outline.points(0.2), s, ox, oy)
        holes = [self.tf(c.points(0.2), s, ox, oy) for _, c in part.holes]
        self.shape(outer, holes, fc=fc, ec=C_PLY_EDGE, lw=lw)
        for x, y in part.marks:
            px, py = ox + x / s, oy + y / s
            self.ax.add_patch(plt.Circle((px, py), max(0.6, P.TOOL_D / 2 / s), fc="#2a7a2a", ec="none"))

    # ------------------------------------------------ размеры
    def _arrow(self, a, b):
        self.ax.annotate("", xy=b, xytext=a,
                         arrowprops=dict(arrowstyle="<|-|>", lw=0.5, color=C_DIM,
                                         mutation_scale=5, shrinkA=0, shrinkB=0))

    def dim_h(self, x1, x2, y_from, y_dim, text, size=6.5):
        for x in (x1, x2):
            self.line([(x, y_from), (x, y_dim + (1.5 if y_dim > y_from else -1.5))], lw=0.18, color=C_DIM)
        self._arrow((x1, y_dim), (x2, y_dim))
        self.text((x1 + x2) / 2, y_dim + 0.8, text, size, ha="center", va="bottom", color=C_DIM)

    def dim_v(self, y1, y2, x_from, x_dim, text, size=6.5):
        for y in (y1, y2):
            self.line([(x_from, y), (x_dim + (1.5 if x_dim > x_from else -1.5), y)], lw=0.18, color=C_DIM)
        self._arrow((x_dim, y1), (x_dim, y2))
        self.text(x_dim - 0.8, (y1 + y2) / 2, text, size, ha="right", va="center",
                  rotation=90, color=C_DIM, rotation_mode="anchor")

    def leader(self, xy, txy, text, size=6.5, **kw):
        self.ax.annotate(text, xy=xy, xytext=txy, fontsize=size, color=C_LINE,
                         arrowprops=dict(arrowstyle="-", lw=0.4, color=C_LINE, shrinkA=0, shrinkB=0),
                         va="center", **kw)

    # ------------------------------------------------ таблица
    def table(self, x, y_top, cols, rows, size=6.5, row_h=5.0, head=True):
        """cols: [(заголовок, ширина, выравнивание)]; rows: списки строк."""
        w = sum(c[1] for c in cols)
        all_rows = ([[c[0] for c in cols]] if head else []) + rows
        for i, r in enumerate(all_rows):
            yy = y_top - (i + 1) * row_h
            self.line([(x, yy), (x + w, yy)], lw=0.15 if i else 0.3)
            xx = x
            for (name, cw, al), val in zip(cols, r):
                tx = xx + 1.2 if al == "l" else (xx + cw / 2 if al == "c" else xx + cw - 1.2)
                self.text(tx, yy + row_h / 2, str(val), size, ha={"l": "left", "c": "center", "r": "right"}[al],
                          va="center", weight="bold" if (head and i == 0) else "normal")
                xx += cw
        self.line([(x, y_top), (x + w, y_top)], lw=0.3)
        xx = x
        for c in cols:
            self.line([(xx, y_top), (xx, y_top - len(all_rows) * row_h)], lw=0.15)
            xx += c[1]
        self.line([(xx, y_top), (xx, y_top - len(all_rows) * row_h)], lw=0.15)
        return y_top - len(all_rows) * row_h

    def notes(self, x, y_top, title, lines, size=6.8, step=4.2, width=None):
        self.text(x, y_top, title, size + 1.2, weight="bold")
        y = y_top - step * 1.3
        for s in lines:
            self.text(x, y, s, size)
            y -= step
        return y

    def save(self, pdf, png):
        pdf.savefig(self.fig)
        self.fig.savefig(png, dpi=110)
        plt.close(self.fig)
