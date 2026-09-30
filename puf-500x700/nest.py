"""Раскладка деталей на лист ф15 1525 x 1525.

Раскладка ручная (детерминированная), проверяется build.py: всё в листе,
зазоры не меньше PART_GAP, короткие стенки лежат в окнах рамок.
Начало координат — левый нижний угол листа.
"""
from dataclasses import dataclass

import params as P
from parts import by_key


@dataclass
class Placed:
    part: object          # parts.Part в координатах листа
    label: str            # «P2B», «W2S-1»
    parent: str = ""      # в окне какой детали лежит


def place(part, x, y, rot=False):
    p = part.normalized()
    if rot:
        o = p.outline.rot90()
        x0, y0, _, _ = o.bbox()
        p.outline = o.moved(-x0, -y0)
        p.holes = [(k, c.rot90().moved(-x0, -y0)) for k, c in p.holes]
        p.marks = [(-my - x0, mx - y0) for mx, my in p.marks]
    p.outline = p.outline.moved(x, y)
    p.holes = [(k, c.moved(x, y)) for k, c in p.holes]
    p.marks = [(mx + x, my + y) for mx, my in p.marks]
    return p


def centered_in(parent_placed, part, rot=False):
    """Деталь по центру окна рамки."""
    win = next(c for k, c in parent_placed.holes if k == "window")
    x0, y0, x1, y1 = win.bbox()
    w, h = part.size()
    if rot:
        w, h = h, w
    return place(part, (x0 + x1 - w) / 2, (y0 + y1 - h) / 2, rot)


def layout():
    k = by_key()
    m, g = P.SHEET_MARGIN, P.PART_GAP
    pw, ph = P.PL, P.PW
    out = []

    col2 = m + pw + g
    row2 = m + ph + g
    p1b = place(k["P1B"], m, m)
    p1t = place(k["P1T"], col2, m)
    p2b = place(k["P2B"], m, row2)
    p2t = place(k["P2T"], col2, row2)
    out += [Placed(p1b, "P1B"), Placed(p1t, "P1T"), Placed(p2b, "P2B"), Placed(p2t, "P2T")]

    # короткие стенки — в окна рамок
    out.append(Placed(centered_in(p1b, k["W1S"]), "W1S-1", "P1B"))
    out.append(Placed(centered_in(p1t, k["W2S"]), "W2S-1", "P1T"))
    out.append(Placed(centered_in(p2b, k["W2S"]), "W2S-2", "P2B"))

    # длинные стенки — два ряда под плитами
    row3 = row2 + ph + g
    wl1 = k["W1L"].size()[1]
    row4 = row3 + wl1 + g
    wl = k["W1L"].size()[0]
    for i, x in enumerate((m, m + wl + g)):
        out.append(Placed(place(k["W1L"], x, row3), f"W1L-{i + 1}"))
        out.append(Placed(place(k["W2L"], x, row4), f"W2L-{i + 1}"))

    # правая полоса — стоймя
    col3 = col2 + pw + g
    out.append(Placed(place(k["W1S"], col3, m, rot=True), "W1S-2"))
    y = m + k["W1S"].size()[0] + g
    out.append(Placed(place(k["W2P"], col3, y, rot=True), "W2P"))
    return out
