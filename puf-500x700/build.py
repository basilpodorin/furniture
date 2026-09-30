"""Сборка пакета для цеха: python3 build.py

out/dxf/parts/*.dxf   — детали по одной, габарит от (0, 0)
out/dxf/sheet_1.dxf   — раскладка на лист
out/nc/sheet_1.tap    — УП (типовой пост, см. post_generic.py)
out/album_A3.pdf      — 6 листов А3 (+ out/png/)
out/report.txt        — спецификация, расход, проверки
out/preview.html      — предпросмотр: 3D, раскрой с проигрыванием УП, листы, спецификация
python3 build.py --web ПУТЬ — ещё и страница для Artifact (three.js с CDN)
"""
import itertools
import math
import sys
from pathlib import Path

from shapely.geometry import Point, box

import cam
import dxfout
import nest
import params as P
import parts as PR
import post_generic
import preview
import sheets
import soft

OUT = Path(__file__).parent / "out"


# ---------------------------------------------------------------- проверки
def verify_toolpaths(placed, strokes):
    """Проверка УП по геометрии: след фрезы (все проходы) против деталей."""
    from shapely.geometry import LineString
    from shapely.ops import unary_union
    r = P.TOOL_D / 2
    lines = [LineString([p[:2] for p in s.points]) for s in strokes if len(s.points) > 1]
    tol = 0.06                              # аппроксимация дуг в УП и в проверке
    tight = unary_union([ln.buffer(r - tol, quad_segs=16) for ln in lines])
    loose = unary_union([ln.buffer(r + tol, quad_segs=16) for ln in lines])
    gouge = max(tight.intersection(pl.part.polygon(0.01)).area for pl in placed)
    left = 0.0
    for pl in placed:
        p = pl.part
        edges = [p.outline.polygon(0.01).exterior] + [c.polygon(0.01).exterior for _, c in p.holes]
        for e in edges:
            left = max(left, e.difference(loose).length)
        for k, c in p.holes:
            if k != "window":
                left = max(left, c.polygon(0.01).difference(loose).area)
    good = gouge < 0.5 and left < 0.5
    return good, f"УП по геометрии: зарез в детали {gouge:.2f} мм², недорез {left:.2f} мм"


def checks(placed, strokes):
    res = []

    def ok(cond, text):
        res.append((bool(cond), text))

    z = P.z_levels()
    ok(abs(z["edge_top"] + P.DOME - P.H) < 0.01, f"высота {z['edge_top']:g} + купол {P.DOME:g} = {P.H:g}")
    ok(abs(P.PL + 2 * P.SIDE_STACK - P.L) < 0.01 and abs(P.PW + 2 * P.SIDE_STACK - P.W) < 0.01,
       f"плита {P.PL:g}x{P.PW:g} + 2x{P.SIDE_STACK:g} = {P.L:g}x{P.W:g}")
    ok(P.DOGBONE_R >= P.TOOL_D / 2, f"косточки R{P.DOGBONE_R:g} >= радиуса фрезы {P.TOOL_D / 2:g}")
    corner = math.dist((P.PL / 2 - P.INSET, P.PW / 2 - P.INSET),
                       (P.PL / 2 - P.PLATE_R, P.PW / 2 - P.PLATE_R))
    ok(corner <= P.PLATE_R, f"угол коробки внутри дуги плиты R{P.PLATE_R:g} ({corner:.1f})")

    # перемычки у пазов и отверстий
    for p in PR.plates():
        outer = p.outline.polygon()
        wins = [c.polygon() for k, c in p.holes if k == "window"]
        feats = [c.polygon() for k, c in p.holes if k != "window"]
        inside = all(outer.contains(g) and not any(w.intersects(g) for w in wins) for g in feats)
        web = min(min([outer.exterior.distance(g)] + [w.exterior.distance(g) for w in wins]) for g in feats)
        ok(inside and web >= 5, f"{p.key}: {len(feats)} пазов/отв. в теле плиты, мин. перемычка {web:.1f} мм")

    # болты: в перекрытии рамок и доступны снизу через окно P1B
    k = PR.by_key()
    bx, by = P.BOLT_XY
    d = PR.bolt_window_clearance()
    ok(d >= P.SOCKET_R,
       f"болт ({bx:g};{by:g}) в окне P1B, до края {d:.1f} мм (>= {P.SOCKET_R:g})")
    for key in ("P1T", "P2B"):
        win = next(c for kk, c in k[key].holes if kk == "window").polygon()
        ok(win.exterior.distance(Point(bx, by)) >= 12, f"{key}: болт/футорка на рамке с запасом")
    # опоры на рамке P1B
    lx, ly = P.PL / 2 - P.LEG_INSET, P.PW / 2 - P.LEG_INSET
    leg = Point(lx, ly).buffer(P.LEG_D / 2)
    ok(k["P1B"].polygon().contains(leg), f"опора Ø{P.LEG_D:g} целиком на рамке P1B")

    # раскладка
    sheet = box(P.SHEET_MARGIN, P.SHEET_MARGIN, P.SHEET[0] - P.SHEET_MARGIN, P.SHEET[1] - P.SHEET_MARGIN)
    polys = {pl.label: pl.part.polygon() for pl in placed}
    ok(all(sheet.contains(pl.part.outline.polygon()) for pl in placed), "все детали на листе с отступом")
    worst = min(polys[a.label].distance(polys[b.label]) for a, b in itertools.combinations(placed, 2))
    ok(worst >= P.PART_GAP - 0.01, f"мин. зазор между деталями {worst:.1f} мм (>= {P.PART_GAP:g})")
    need = {p.key: p.qty for p in PR.all_parts()}
    got = {}
    for pl in placed:
        key = pl.label.split("-")[0]
        got[key] = got.get(key, 0) + 1
    ok(need == got, "на листе полный комплект деталей")
    for pl in placed:
        if pl.parent:
            par = next(x for x in placed if x.label == pl.parent)
            win = next(c for kk, c in par.part.holes if kk == "window").polygon()
            ok(win.buffer(-P.PART_GAP + 0.01).contains(pl.part.outline.polygon()),
               f"{pl.label} в окне {pl.parent} с зазором")

    # УП: фреза не заходит в детали, пазы выбраны, контуры прорезаны
    ok_cut, text = verify_toolpaths(placed, strokes)
    ok(ok_cut, text)

    # ППУ и ткань
    for grade, (packed, used) in soft.foam_layouts().items():
        ok(used <= P.FOAM_SHEET[1], f"ППУ {grade}: раскрой на лист {P.FOAM_SHEET[0]:g}x{P.FOAM_SHEET[1]:g}")
    ok(all(p.w <= P.FABRIC_ROLL_W for p in soft.fabric_pieces()), "ткань: детали в ширину рулона")
    return res


# ---------------------------------------------------------------- отчёт
def report(placed, stats, chk, ply_area):
    L = []
    w = L.append
    w(f"{P.NAME}  ({P.CODE})")
    w("=" * 72)
    w(f"Габарит {P.L:g} x {P.W:g} x {P.H:g}; два модуля по {P.MODULE_H:g} на болтах M8.")
    w(f"Мягкие слои на сторону: ткань {P.FABRIC:g} + холкон {P.HOLCON_SIDE:g} + ППУ {P.FOAM:g} "
      f"+ картон {P.CARD:g} = {P.SIDE_STACK:g} мм.")
    z = P.z_levels()
    w("Высоты: " + ", ".join(f"{k} {v:g}" for k, v in z.items()))
    w("")
    w("КАРКАС (фанера ф15)")
    for p in PR.all_parts():
        a, b = p.size()
        w(f"  {p.key:4} {p.name:30} {p.module:8} {p.qty} шт  {a:g} x {b:g}")
    mass = ply_area * P.T / 1000 * P.PLY_DENSITY
    w(f"  площадь {ply_area:.2f} м², масса ≈ {mass:.1f} кг, лист {P.SHEET[0]:g}x{P.SHEET[1]:g} — 1 шт "
      f"({ply_area / (P.SHEET[0] * P.SHEET[1] / 1e6) * 100:.0f}%)")
    w(f"  УП: {stats['strokes']} операций, путь реза {stats['cut_m']:.0f} м, ≈ {stats['minutes']:.0f} мин")
    w("")
    for title, pieces in (("ППУ", soft.foam_pieces()), ("ХОЛКОН", soft.holcon_pieces()),
                          ("ТКАНЬ", soft.fabric_pieces()), ("ПРОЧЕЕ", soft.other_pieces())):
        w(title)
        for p in pieces:
            r = f" R{p.r:g}" if p.r else ""
            w(f"  {p.key:6} {p.name:46} {p.qty} шт  {p.w:g} x {p.h:g}{r}  [{p.material}]")
            if p.note:
                w(f"         {p.note}")
    _, fab_used = soft.shelf_pack(soft.fabric_pieces(), P.FABRIC_ROLL_W)
    w("")
    w(f"Ткань: {fab_used / 1000:.2f} м.п. при ширине {P.FABRIC_ROLL_W:g}; "
      f"холкон {soft.area_m2(soft.holcon_pieces()):.2f} м²; ППУ ≈ {soft.foam_mass():.1f} кг")
    fab_kg = soft.area_m2(soft.fabric_pieces()) * P.FABRIC_GSM / 1000
    hol_kg = soft.area_m2(soft.holcon_pieces()) * P.HOLCON_GSM / 1000
    w(f"Масса пуфа ≈ {mass + soft.foam_mass() + fab_kg + hol_kg + 0.6:.1f} кг "
      f"(каркас {mass:.1f}, ППУ {soft.foam_mass():.1f}, ткань {fab_kg:.1f}, холкон {hol_kg:.1f}, "
      "картон и крепёж ~0.6)")
    w("")
    w("КРЕПЁЖ")
    w(f"  {P.BOLT} — 4;  {P.TNUT} — 4;  {P.LEG} — 4 + {P.LEG_SCREW} — 4")
    w("")
    w("ПРОВЕРКИ")
    for good, text in chk:
        w(f"  [{'OK' if good else '!!'}] {text}")
    w("")
    w("ВНИМАНИЕ: nc/sheet_1.tap сделана типовым постпроцессором (post_generic.py),")
    w("а не цеховым. Проверить в симуляторе или пересобрать цеховым постом.")
    return "\n".join(L) + "\n"


def main():
    for d in ("dxf/parts", "nc", "png"):
        (OUT / d).mkdir(parents=True, exist_ok=True)
    for p in PR.all_parts():
        dxfout.write_part(p, OUT / "dxf" / "parts" / f"{p.key}.dxf")
    placed = nest.layout()
    dxfout.write_sheet(placed, OUT / "dxf" / "sheet_1.dxf")
    strokes = cam.toolpaths(placed)
    stats = cam.stats(strokes)
    (OUT / "nc" / "sheet_1.tap").write_text(
        post_generic.post(strokes, f"{P.CODE} SHEET 1 PLY {P.T:g}", stats), encoding="ascii")
    ply_area = sum(p.polygon().area * p.qty for p in PR.all_parts()) / 1e6
    chk = checks(placed, strokes)
    sheets.build_album(OUT, placed, stats, ply_area)
    web = sys.argv[sys.argv.index("--web") + 1] if "--web" in sys.argv else None
    preview.build_preview(OUT, placed, strokes, stats, chk, ply_area, web)
    rep = report(placed, stats, chk, ply_area)
    (OUT / "report.txt").write_text(rep, encoding="utf-8")
    print(rep)
    bad = [t for good, t in chk if not good]
    if bad:
        print("ПРОВЕРКИ НЕ ПРОШЛИ:", *bad, sep="\n  ")
        sys.exit(1)


if __name__ == "__main__":
    main()
