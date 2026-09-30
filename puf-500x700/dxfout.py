"""DXF деталей и раскладки (R2010, мм).

Слои: CUT_OUT — наружный контур (фреза снаружи), CUT_IN — пазы, окна,
отверстия (фреза внутри), MARK_D2 — метки опор глубиной 2 мм,
LABEL — подписи (не резать), SHEET — лист.
"""
import ezdxf

import params as P

LAYERS = {"CUT_OUT": 7, "CUT_IN": 1, "MARK_D2": 3, "LABEL": 8, "SHEET": 5}


def _doc():
    doc = ezdxf.new("R2010", setup=False)
    doc.units = ezdxf.units.MM
    doc.header["$INSUNITS"] = 4
    for name, color in LAYERS.items():
        doc.layers.add(name, color=color)
    return doc


def _contour(msp, c, layer):
    if c.circle:
        msp.add_circle(c.circle[:2], c.circle[2], dxfattribs={"layer": layer})
    else:
        msp.add_lwpolyline(c.pts, format="xyb", close=True, dxfattribs={"layer": layer})


def _part(msp, part, label=None):
    _contour(msp, part.outline, "CUT_OUT")
    for _, c in part.holes:
        _contour(msp, c, "CUT_IN")
    for x, y in part.marks:
        msp.add_circle((x, y), P.TOOL_D / 2, dxfattribs={"layer": "MARK_D2"})
    if label:
        x0, y0, x1, y1 = part.outline.bbox()
        h = 14 if min(x1 - x0, y1 - y0) > 150 else 9
        # подпись в теле детали: у рамок — на полке, у стенок — по центру
        win = [c for k, c in part.holes if k == "window"]
        if win:
            wx0, wy0, wx1, wy1 = win[0].bbox()
            pos = (x0 + 212, (y0 + wy0) / 2)
        else:
            pos = ((x0 + x1) / 2, (y0 + y1) / 2)
        msp.add_text(label, height=h, dxfattribs={"layer": "LABEL"}).set_placement(
            pos, align=ezdxf.enums.TextEntityAlignment.MIDDLE_CENTER)


def write_part(part, path):
    doc = _doc()
    _part(doc.modelspace(), part.normalized())
    doc.saveas(path)


def write_sheet(placed, path):
    doc = _doc()
    msp = doc.modelspace()
    sw, sh = P.SHEET
    msp.add_lwpolyline([(0, 0), (sw, 0), (sw, sh), (0, sh)], close=True,
                       dxfattribs={"layer": "SHEET"})
    for pl in placed:
        _part(msp, pl.part, pl.label)
    doc.saveas(path)
