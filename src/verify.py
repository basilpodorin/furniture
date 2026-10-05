"""Сверка сгенерированных контуров с исходными DXF проекта (source/)."""
import math, os, sys
import ezdxf
import geometry as g
from shapely.geometry import Polygon

SRC = os.path.join(os.path.dirname(__file__), "..", "source")


def dxf_entities(fn):
    out = []
    for e in ezdxf.readfile(os.path.join(SRC, fn)).modelspace():
        if e.dxftype() == "LINE":
            out.append(g.Line(tuple(e.dxf.start)[:2], tuple(e.dxf.end)[:2]))
        elif e.dxftype() == "ARC":
            out.append(g.Arc(tuple(e.dxf.center)[:2], e.dxf.radius, e.dxf.start_angle, e.dxf.end_angle))
    return out


def poly(verts):
    return Polygon(g.sample(verts, 0.1))


def main():
    ok = True
    # стойка: полный контур из нога1.DXF
    ref = poly(g.chain(dxf_entities("leg_side.dxf")))
    mine = poly(g.leg().verts)
    print("стойка: площадь %.1f / %.1f, периметр %.2f / %.2f" % (mine.area, ref.area, mine.length, ref.length))
    ok &= abs(mine.area - ref.area) < 5 and abs(mine.length - ref.length) < 0.5
    # столешница: все 12 дуг угла/торца/стороны с R=150/995.41/12272.75 -> полный контур
    top = [e for e in dxf_entities("top_outlines.dxf") if isinstance(e, g.Arc) and
           (abs(e.r - 150) < 0.01 or abs(e.r - 995.41) < 0.01 or abs(e.r - 12272.75) < 0.01)]
    ref = poly(g.chain(top, tol=0.3))
    half = poly(g.tabletop_half().verts)
    print("столешница: площадь полная %.0f, 2*половина %.0f" % (ref.area, 2 * half.area))
    ok &= abs(ref.area - 2 * half.area) < 20
    sub = [e for e in dxf_entities("top_outlines.dxf") if isinstance(e, g.Arc) and
           (abs(e.r - 125) < 0.01 or abs(e.r - 970.41) < 0.01 or abs(e.r - 12247.75) < 0.01)]
    ref = poly(g.chain(sub, tol=0.3))
    half = poly(g.subplate_half().verts)
    print("подстолье: площадь полная %.0f, 2*половина %.0f" % (ref.area, 2 * half.area))
    ok &= abs(ref.area - 2 * half.area) < 20
    # размеры по чертежу
    exp = {"upper": (383.72, 79.27), "lower": (255.0, 94.51), "hub": (140.0, 135.58),
           "tabletop_half": (1250.0, 1000.0), "subplate_half": (1225.0, 950.0), "leg": (741.26, 114.86)}
    for p in g.all_parts():
        b = p.bbox()
        w, h = b[2] - b[0], b[3] - b[1]
        good = abs(w - exp[p.key][0]) < 0.1 and abs(h - exp[p.key][1]) < 0.1
        ok &= good
        print("%-14s %.2f x %.2f %s" % (p.key, w, h, "ok" if good else "!!"))
    print("ИТОГ:", "OK" if ok else "РАСХОЖДЕНИЕ")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
