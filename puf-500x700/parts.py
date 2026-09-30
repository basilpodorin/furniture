"""Детали каркаса из фанеры ф15.

Плиты — в координатах изделия (центр в 0,0). Стенки — в своих координатах:
X вдоль длины от 0, Y по высоте от 0 (низ нижнего шипа).
"""
from dataclasses import dataclass, field

import params as P
from geom import Contour, circle, dogboned, rounded_rect, slot


@dataclass
class Part:
    key: str
    name: str
    module: str               # "верхний" / "нижний"
    qty: int
    outline: Contour          # против часовой
    holes: list = field(default_factory=list)   # [(вид, Contour)]: slot / window / hole
    marks: list = field(default_factory=list)   # [(x, y)] метки опор
    note: str = ""

    def normalized(self):
        """Копия со сдвигом габарита в (0, 0) — для DXF детали и раскладки."""
        x0, y0, _, _ = self.outline.bbox()
        return Part(self.key, self.name, self.module, self.qty,
                    self.outline.moved(-x0, -y0),
                    [(k, c.moved(-x0, -y0)) for k, c in self.holes],
                    [(x - x0, y - y0) for x, y in self.marks], self.note)

    def size(self):
        x0, y0, x1, y1 = self.outline.bbox()
        return x1 - x0, y1 - y0

    def polygon(self, tol=0.05):
        from shapely.geometry import Polygon
        outer = self.outline.polygon(tol)
        inner = [c.polygon(tol).exterior.coords for _, c in self.holes]
        return Polygon(outer.exterior.coords, inner)


# ---------------------------------------------------------------- стенки
LONG_Y = P.PW / 2 - P.INSET - P.T / 2      # ось длинной стенки: 194.5
SHORT_X = P.PL / 2 - P.INSET - P.T / 2     # ось короткой: 294.5


def wall_outline(length, height, top, bottom):
    """Стенка с шипами. top/bottom — [(центр от середины, длина шипа)]."""
    t = P.T
    y_b, y_t = t, height - t            # плечики
    pts, roots = [], set()

    def add(x, y, root=False):
        if root:
            roots.add(len(pts))
        pts.append((x, y))

    add(0, y_b)
    for c, tl in sorted(bottom):
        a, b = length / 2 + c - tl / 2, length / 2 + c + tl / 2
        add(a, y_b, True); add(a, 0); add(b, 0); add(b, y_b, True)
    add(length, y_b)
    add(length, y_t)
    for c, tl in sorted(top, reverse=True):
        a, b = length / 2 + c - tl / 2, length / 2 + c + tl / 2
        add(b, y_t, True); add(b, height); add(a, height); add(a, y_t, True)
    add(0, y_t)
    return dogboned(pts, roots, P.DOGBONE_R)


def lighten_windows(length, height):
    body = height - 2 * P.T
    wh = body - 2 * 40
    n = 2 if length > 500 else 1
    ww = (length - (n + 1) * 60) / n
    out = []
    for i in range(n):
        cx = 60 + ww / 2 + i * (ww + 60)
        out.append(("window", rounded_rect(ww, wh, 20, cx, height / 2)))
    return out


def walls():
    tl = P.TENON_LEN
    lt = [(c, tl) for c in P.LONG_TENONS]
    st = [(c, tl) for c in P.SHORT_TENONS]
    out = []
    for mod, hf, sfx in (("верхний", P.HF_UP, "2"), ("нижний", P.HF_LO, "1")):
        for key, name, length, ten in ((f"W{sfx}L", "Стенка длинная", P.WALL_LONG, lt),
                                       (f"W{sfx}S", "Стенка короткая", P.WALL_SHORT, st)):
            holes = lighten_windows(length, hf) if (sfx == "1" and P.LIGHTEN_LO_WALLS) else []
            out.append(Part(key, name, mod, 2, wall_outline(length, hf, ten, ten), holes))
        if sfx == "2":
            out.append(Part("W2P", "Перегородка", mod, 1,
                            wall_outline(P.WALL_SHORT, hf,
                                         [(c, tl) for c in P.PART_TOP_TENONS],
                                         [(c, P.PART_BOT_TENON_LEN) for c in P.PART_BOT_TENONS]),
                            note="поперёк, по центру сиденья"))
    return out


# ---------------------------------------------------------------- плиты
def wall_slots(partition=None):
    """Пазы под шипы стенок (и перегородки, если partition = список (y, длина))."""
    w, cl, r = P.SLOT_W, P.SLOT_CLEAR, P.DOGBONE_R
    out = []
    for sy in (-1, 1):
        for c in P.LONG_TENONS:
            out.append(("slot", slot(c, sy * LONG_Y, P.TENON_LEN + cl, w, r)))
    for sx in (-1, 1):
        for c in P.SHORT_TENONS:
            out.append(("slot", slot(sx * SHORT_X, c, w, P.TENON_LEN + cl, r)))
    for c, tl in partition or []:
        out.append(("slot", slot(0.0, c, w, tl + cl, r)))
    return out


def ring_window(ring):
    return ("window", rounded_rect(P.PL - 2 * ring, P.PW - 2 * ring, P.WINDOW_R))


def four(x, y):
    return [(sx * x, sy * y) for sx in (-1, 1) for sy in (-1, 1)]


def plates():
    outline = rounded_rect(P.PL, P.PW, P.PLATE_R)
    bx, by = P.BOLT_XY
    part_top = [(c, P.TENON_LEN) for c in P.PART_TOP_TENONS]
    part_bot = [(c, P.PART_BOT_TENON_LEN) for c in P.PART_BOT_TENONS]
    lx, ly = P.PL / 2 - P.LEG_INSET, P.PW / 2 - P.LEG_INSET
    return [
        Part("P2T", "Плита сиденья (сплошная)", "верхний", 1, outline,
             wall_slots(part_top), note="на неё клеится ППУ сиденья"),
        Part("P2B", "Рамка низа", "верхний", 1, outline,
             [ring_window(P.RING_MID)] + wall_slots(part_bot)
             + [("hole", circle(x, y, P.TNUT_HOLE_D / 2)) for x, y in four(bx, by)],
             note=f"4 отв. Ø{P.TNUT_HOLE_D:g} под футорки M8, футорки изнутри"),
        Part("P1T", "Рамка верха", "нижний", 1, outline,
             [ring_window(P.RING_MID)] + wall_slots()
             + [("hole", circle(x, y, P.BOLT_HOLE_D / 2)) for x, y in four(bx, by)],
             note=f"4 отв. Ø{P.BOLT_HOLE_D:g} под болты M8"),
        Part("P1B", "Рамка низа (окно под монтаж)", "нижний", 1, outline,
             [ring_window(P.RING_BOT)] + wall_slots(), marks=four(lx, ly),
             note="метки опор — наружу (вниз)"),
    ]


def all_parts():
    return plates() + walls()


def by_key():
    return {p.key: p for p in all_parts()}


def bolt_window_clearance():
    """От оси болта до края окна P1B (снизу через окно заводится ключ)."""
    from shapely.geometry import Point
    win = next(c for k, c in by_key()["P1B"].holes if k == "window").polygon()
    pt = Point(*P.BOLT_XY)
    return win.exterior.distance(pt) if win.contains(pt) else -1.0
