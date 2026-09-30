#!/usr/bin/env python3
"""Генерация всех файлов наконечника в папку out/.

    python build.py                          # параметры по умолчанию
    python build.py --set cap_d=52 collar_d=60
    python build.py --no-render              # без картинок (рендер ~5 мин)

Нужны пакеты из requirements.txt.
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np

from geom import (Line, Params, build_profile, end_heightmap, finial_mesh, fixture_layout, heightmap,
                  index_draft_margin, index_layout, min_concave_radius, orient_outward, radius_table,
                  reed_d, revolve_mesh, simulate_ball, simulate_tool, tapered_ball, write_stl)

OUT = Path(__file__).resolve().parent / "out"


# ----------------------------------------------------------------------------
# Раскладка заготовки на 2 детали (установки 1–2, система координат станка)
# ----------------------------------------------------------------------------
def layout(P: Params) -> dict:
    """X0Y0 — центр заготовки в плане, Z0 — стол (жертвенный слой).
    Оси наконечников параллельны X на высоте stock_t/2; переворот — вокруг оси X."""
    x_lo = -P.tenon_l - P.gap              # стенки кармана в координатах детали
    x_hi = P.length + P.gap
    dx = -(x_lo + x_hi) / 2                # сдвиг детали, чтобы карман был по центру
    pocket_x = x_hi - x_lo
    y_axis = P.collar_d / 2 + P.part_gap / 2
    pocket_y = 2 * (y_axis + P.collar_d / 2 + P.gap)
    rnd = lambda v: 5 * math.ceil(v / 5 - 1e-9)
    Lx = rnd(pocket_x + 2 * P.frame_w)
    Ly = rnd(pocket_y + 2 * P.frame_w)
    pin_x = Lx / 2 - (Lx - pocket_x) / 4   # середина торцевой рамки
    return dict(dx=dx, x_lo=x_lo, x_hi=x_hi, pocket_x=pocket_x, pocket_y=pocket_y,
                y_axis=y_axis, Lx=Lx, Ly=Ly, T=P.stock_t, z_axis=P.stock_t / 2,
                pin_a=(-pin_x, 0.0), pin_b=(pin_x, 0.0))


# ----------------------------------------------------------------------------
# Твёрдые тела (build123d / OpenCascade): тело после установок 1–2 и оснастка
# ----------------------------------------------------------------------------
def body_solid(P: Params):
    import build123d as bd

    prof = build_profile(P)
    es = [bd.Line(s.p0, s.p1) if isinstance(s, Line) else bd.ThreePointArc(s.p0, s.mid, s.p1)
          for s in prof.segs]
    es.append(bd.Line(prof.segs[-1].p1, prof.segs[0].p0))
    return bd.revolve(bd.Face(bd.Wire(es)), bd.Axis.X, 360)


def index_half_solid(P: Params):
    """Половина делительной оправки: брусок B×B×B/2 с полуканавкой под шип вдоль X,
    два отверстия под саморезы (стягивают половины и зажимают шип)."""
    import build123d as bd

    I = index_layout(P)
    B = I["B"]
    half = bd.Pos(-B / 2, 0, B / 4) * bd.Box(B, B, B / 2)
    chan = bd.Pos(-B / 2, 0, B / 2) * bd.Rot(0, 90, 0) * bd.Cylinder(I["chan_r"], B + 2)
    holes = [bd.Pos(-B / 2, s * (B / 2 - 6), B / 4) * bd.Cylinder(2.25, B) for s in (1, -1)]
    cbores = [bd.Pos(-B / 2, s * (B / 2 - 6), 1.5) * bd.Cylinder(4.5, 3.0) for s in (1, -1)]
    out = half - chan
    for c in holes + cbores:
        out = out - c
    return out


def nest_solid(P: Params):
    """Ложемент установки 4 на 2 детали: гнёзда под оправки, зазорный жёлоб
    под воротник, ложе под поясок шляпки. Верх ложемента — Z0."""
    import build123d as bd

    I = index_layout(P)
    B, h, t = I["B"], I["h"], I["t"]
    plate = bd.Pos((I["x0"] + I["x1"]) / 2, 0, -t / 2) * bd.Box(I["x1"] - I["x0"], I["ly"], t)
    out = plate
    for ys in I["stations"]:
        pocket = bd.Pos(-B / 2, ys, -I["pocket"] / 2 + 0.5) * bd.Box(B + 0.4, B + 0.4, I["pocket"] + 1)
        a0, a1 = I["trough_x"]
        c0, c1 = I["cradle_x"]
        trough = bd.Pos((a0 + a1) / 2, ys, h) * bd.Rot(0, 90, 0) * bd.Cylinder(I["trough_r"], a1 - a0)
        cradle = bd.Pos((c0 + c1) / 2, ys, h) * bd.Rot(0, 90, 0) * bd.Cylinder(I["cradle_r"], c1 - c0)
        out = out - pocket - trough - cradle
    return out


def export_solid(solid, stem: Path, stl_tol=0.01, stl=True):
    import build123d as bd

    if not solid.is_valid:
        raise RuntimeError(f"{stem.name}: невалидное тело")
    bd.export_step(solid, str(stem.with_suffix(".step")))
    if stl:
        bd.export_stl(solid, str(stem.with_suffix(".stl")), tolerance=stl_tol, angular_tolerance=0.1)
    return solid.volume


# ----------------------------------------------------------------------------
# DXF
# ----------------------------------------------------------------------------
def _dxf_seg(msp, s, layer, tf=lambda p: p, mirror=False):
    if isinstance(s, Line):
        msp.add_line(tf(s.p0), tf(s.p1), dxfattribs={"layer": layer})
        return
    a0, a1 = s.a0, s.a0 + s.sweep
    c = tf(s.c)
    if mirror:            # зеркало относительно оси X: углы меняют знак
        a0, a1 = -a0, -a1
    lo, hi = (a0, a1) if a1 > a0 else (a1, a0)   # ezdxf: дуга всегда против часовой
    msp.add_arc(c, s.r, lo, hi, dxfattribs={"layer": layer})


def _new_dxf(layers):
    import ezdxf

    doc = ezdxf.new("R2010", setup=True)
    doc.units = ezdxf.units.MM
    for name, color, lt in layers:
        doc.layers.add(name, color=color, linetype=lt)
    return doc, doc.modelspace()


def make_profile_dxf(P: Params, path: Path):
    doc, msp = _new_dxf((("PROFILE", 7, "CONTINUOUS"), ("OUTLINE", 8, "CONTINUOUS"),
                         ("AXIS", 1, "CENTER"), ("PROFILE_CNC", 3, "CONTINUOUS")))
    prof = build_profile(P)
    # замкнутый полупрофиль для «тела вращения» (вокруг оси X)
    for s in prof.segs:
        _dxf_seg(msp, s, "PROFILE")
    msp.add_line(prof.segs[-1].p1, prof.segs[0].p0, dxfattribs={"layer": "PROFILE"})
    # полный силуэт (справочно)
    for s in prof.segs:
        _dxf_seg(msp, s, "OUTLINE", tf=lambda p: (p[0], -p[1]), mirror=True)
    msp.add_line((-P.tenon_l - 5, 0), (P.length + 5, 0), dxfattribs={"layer": "AXIS"})
    # вариант с перемычками — со смещением вниз
    cnc = build_profile(P, bridges=True)
    off = -2.2 * P.collar_d
    for s in cnc.segs:
        _dxf_seg(msp, s, "PROFILE_CNC", tf=lambda p, o=off: (p[0], p[1] + o))
    msp.add_line((cnc.segs[-1].p1[0], off), (cnc.segs[0].p0[0], off), dxfattribs={"layer": "PROFILE_CNC"})
    doc.saveas(path)


def make_layout_dxf(P: Params, L: dict, path: Path):
    doc, msp = _new_dxf((("STOCK", 7, "CONTINUOUS"), ("POCKET", 5, "CONTINUOUS"),
                         ("PART", 3, "CONTINUOUS"), ("PINS", 1, "CONTINUOUS"),
                         ("AXIS", 1, "CENTER"), ("TEXT", 8, "CONTINUOUS")))
    Lx, Ly = L["Lx"], L["Ly"]
    msp.add_lwpolyline([(-Lx / 2, -Ly / 2), (Lx / 2, -Ly / 2), (Lx / 2, Ly / 2), (-Lx / 2, Ly / 2)],
                       close=True, dxfattribs={"layer": "STOCK"})
    px, py = L["pocket_x"] / 2, L["pocket_y"] / 2
    msp.add_lwpolyline([(-px, -py), (px, -py), (px, py), (-px, py)], close=True,
                       dxfattribs={"layer": "POCKET"})
    cnc = build_profile(P, bridges=True)
    for sy in (1, -1):
        yc = sy * L["y_axis"]
        for mir in (False, True):
            tf = (lambda p, yc=yc, m=mir: (p[0] + L["dx"], yc + (-p[1] if m else p[1])))
            for s in cnc.segs:
                if isinstance(s, Line) and abs(s.p0[1]) < 1e-9 and abs(s.p1[1]) < 1e-9:
                    continue
                if isinstance(s, Line) and abs(s.p0[0] - s.p1[0]) < 1e-9 and min(s.p0[1], s.p1[1]) < 1e-9:
                    continue  # торцы перемычек лежат на стенке кармана
                _dxf_seg(msp, s, "PART", tf=tf, mirror=mir)
        msp.add_line((-Lx / 2 - 5, yc), (Lx / 2 + 5, yc), dxfattribs={"layer": "AXIS"})
    msp.add_line((-Lx / 2 - 10, 0), (Lx / 2 + 10, 0), dxfattribs={"layer": "AXIS"})
    msp.add_circle(L["pin_a"], P.pin_d / 2, dxfattribs={"layer": "PINS"})
    msp.add_circle(L["pin_b"], P.pin2_d / 2, dxfattribs={"layer": "PINS"})
    msp.add_text("ОСЬ ПЕРЕВОРОТА (X)", dxfattribs={"layer": "TEXT", "height": 3}).set_placement((-Lx / 2, 2))
    doc.saveas(path)


def make_fixture_dxf(P: Params, path: Path):
    F = fixture_layout(P)
    doc, msp = _new_dxf((("FIXTURE", 7, "CONTINUOUS"), ("HOLES", 1, "CONTINUOUS"),
                         ("ROSETTE_ZONE", 5, "CONTINUOUS"), ("COLLAR", 8, "CONTINUOUS"),
                         ("TEXT", 8, "CONTINUOUS")))
    lx, ly = F["Lx"] / 2, F["Ly"] / 2
    msp.add_lwpolyline([(-lx, -ly), (lx, -ly), (lx, ly), (-lx, ly)], close=True,
                       dxfattribs={"layer": "FIXTURE"})
    for c in F["holes"]:
        msp.add_circle(c, F["hole_d"] / 2, dxfattribs={"layer": "HOLES"})
        msp.add_circle(c, F["zone_r"], dxfattribs={"layer": "ROSETTE_ZONE"})
        msp.add_circle(c, P.collar_d / 2, dxfattribs={"layer": "COLLAR"})
    msp.add_text(f"ГНЁЗДА Ø{P.tenon_d:g} ГЛ. {F['hole_depth']:g}; Z0 = ВЕРХ КОНДУКТОРА",
                 dxfattribs={"layer": "TEXT", "height": 3}).set_placement((-lx, -ly - 6))
    doc.saveas(path)


def flute_boundary(P: Params, prof, n=60):
    """Граница обработки установки 4 в плане: сектор ±45° над осью, по зоне каннелюр."""
    x = np.linspace(prof.reed_x[0] - 0.5, prof.reed_x[1] + 0.5, n)
    yb = radius_table(prof, x) * math.sin(2 * math.pi / P.reeds) + 0.3
    return np.vstack([np.c_[x, yb], np.c_[x[::-1], -yb[::-1]]])


def make_index_dxf(P: Params, path: Path):
    I = index_layout(P)
    prof = build_profile(P)
    doc, msp = _new_dxf((("NEST", 7, "CONTINUOUS"), ("POCKET", 1, "CONTINUOUS"),
                         ("TROUGH", 3, "CONTINUOUS"), ("FLUTE_ZONE", 5, "CONTINUOUS"),
                         ("AXIS", 1, "CENTER"), ("TEXT", 8, "CONTINUOUS")))
    ly = I["ly"] / 2
    msp.add_lwpolyline([(I["x0"], -ly), (I["x1"], -ly), (I["x1"], ly), (I["x0"], ly)], close=True,
                       dxfattribs={"layer": "NEST"})
    B, h = I["B"], I["h"]
    for ys in I["stations"]:
        msp.add_lwpolyline([(-B - 0.2, ys - B / 2 - 0.2), (0.2, ys - B / 2 - 0.2), (0.2, ys + B / 2 + 0.2),
                            (-B - 0.2, ys + B / 2 + 0.2)], close=True, dxfattribs={"layer": "POCKET"})
        for (xa, xb), r in ((I["trough_x"], I["trough_r"]), (I["cradle_x"], I["cradle_r"])):
            w = math.sqrt(r * r - h * h)
            msp.add_lwpolyline([(xa, ys - w), (xb, ys - w), (xb, ys + w), (xa, ys + w)], close=True,
                               dxfattribs={"layer": "TROUGH"})
        fb = flute_boundary(P, prof)
        msp.add_lwpolyline([(x, ys + y) for x, y in fb], close=True, dxfattribs={"layer": "FLUTE_ZONE"})
        msp.add_line((I["x0"] - 5, ys), (I["x1"] + 5, ys), dxfattribs={"layer": "AXIS"})
    msp.add_text(f"X0 = ОПОРНЫЙ ТОРЕЦ, Z0 = ВЕРХ ЛОЖЕМЕНТА, ОСЬ НА Z {h:g}",
                 dxfattribs={"layer": "TEXT", "height": 3}).set_placement((I["x0"], -ly - 6))
    doc.saveas(path)


# ----------------------------------------------------------------------------
# Проверки технологичности
# ----------------------------------------------------------------------------
def checks(P: Params, step=0.1) -> dict:
    prof = build_profile(P)
    cnc = build_profile(P, bridges=True)
    res = {"min_concave_profile": min_concave_radius(P)}
    # установки 1–2: гладкое тело вращения, сферы ⌀8 и ⌀6
    xs = np.arange(-P.tenon_l - P.gap, P.length + P.gap + 1e-9, step)
    R = P.collar_d / 2 + P.ball_d / 2 + 2
    ys = np.arange(-R, R + 1e-9, step)
    for bd_ in sorted({P.ball_d, 6.0}):
        rb = bd_ / 2
        Z = heightmap(P, cnc, xs, ys, floor=-(rb + 0.5))
        S = simulate_ball(Z, step, rb)
        gy, gx = np.gradient(Z, step)
        dev_n = (S - Z) / np.sqrt(1 + gx ** 2 + gy ** 2)   # недорез по нормали
        part = (Z > 0.3) & (xs[None, :] > -P.tenon_l) & (xs[None, :] < P.length - 1)
        res[f"ball_{bd_:g}_max_leftover"] = float(dev_n[part].max())
    # установка 4: каннелюры конусной сферой, деталь в оправке, сектор ±45° сверху
    if P.reeds:
        res["index_draft"] = index_draft_margin(P, prof)
        x0, x1 = prof.reed_x
        xs = np.arange(x0 - 4, x1 + 4 + 1e-9, step)
        ys = np.arange(-17, 17 + 1e-9, step)
        Z = heightmap(P, prof, xs, ys, floor=-30.0, reeds=True)
        top = Z.max()
        Zc = np.maximum(Z, top - 22.0)          # глубже 22 мм фреза не опускается — вне зоны каннелюр
        h = tapered_ball(P.flute_tool_r, P.flute_tool_angle)
        rmax = P.flute_tool_r + 22.0 * math.tan(math.radians(P.flute_tool_angle)) + 0.5
        S = simulate_tool(Zc, step, h, rmax)
        gy, gx = np.gradient(Z, step)
        dev_n = (S - Z) / np.sqrt(1 + gx ** 2 + gy ** 2)
        R0 = radius_table(prof, xs)
        d = reed_d(P, prof, xs, R0)
        sector = (np.abs(ys)[:, None] <= R0[None, :] * math.sin(2 * math.pi / P.reeds))
        full = d > 0.9 * P.reed_depth * R0 / (P.neck_d / 2)
        # дно канавки — острое, фреза оставит радиус своего кончика: исключаем полосу у дна
        phi = np.arctan2(ys[:, None], np.maximum(Z, 1e-3))
        step_a = 2 * math.pi / P.reeds
        dv = np.abs(phi % step_a - step_a / 2)          # угловое расстояние до ближайшей канавки
        near_valley = dv * R0[None, :] < 2.0 * P.flute_tool_r
        m = sector & full[None, :] & ~near_valley
        res["flute_max_leftover"] = float(dev_n[m].max())
        res["flute_valley_leftover"] = float(dev_n[sector & full[None, :]].max())
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--set", nargs="*", default=[], metavar="ИМЯ=ЗНАЧ", help="переопределить параметры")
    ap.add_argument("--no-render", action="store_true")
    a = ap.parse_args()
    P = Params().with_overrides(a.set)
    if P.reeds % 4:
        raise SystemExit("reeds должно делиться на 4 (гребни на верху и в плоскости разъёма)")
    if min_concave_radius(P) < P.ball_d / 2 + 0.2:
        raise SystemExit(f"вогнутые радиусы профиля меньше радиуса фрезы Ø{P.ball_d}")
    OUT.mkdir(exist_ok=True)

    prof = build_profile(P)
    cnc = build_profile(P, bridges=True)
    L = layout(P)
    I = index_layout(P)

    # --- STL ---
    # готовая деталь (для просмотра): каннелюры + розетка, ось X, опорный торец x = 0
    V, F = finial_mesh(P, prof, d_rho=0.2, k_fine=2)
    F, vol = orient_outward(V, F)
    write_stl(OUT / "finial.stl", V, F, "finial")
    print(f"finial.stl: {len(F)} треуг., объём {vol / 1000:.1f} см³, масса ≈ {vol / 1000 * 0.68:.0f} г")

    # установки 1–2: обе детали с перемычками, шейка и купол гладкие, координаты станка
    V, F = revolve_mesh(P, cnc, n_phi=180, reeds=False)
    F, _ = orient_outward(V, F)
    Vs, Fs = [], []
    for k, sy in enumerate((1, -1)):
        W = V.copy()
        W += [L["dx"], sy * L["y_axis"], L["z_axis"]]
        Vs.append(W)
        Fs.append(F + k * len(V))
    write_stl(OUT / "cnc_setup1-2_2pcs.stl", np.vstack(Vs), np.vstack(Fs), "cnc_setup1-2")

    # установка 3: розетка, деталь торцом вверх (ось = Z, опорный торец Z = 0); только шляпка
    if P.rosette:
        x_cut = prof.marks["xs"] - 4.0
        V, F = finial_mesh(P, prof, reeds=False, x_min=x_cut, d_rho=0.15)
        F, _ = orient_outward(V, F)
        write_stl(OUT / "cnc_setup3_rosette_1pc.stl", V[:, [1, 2, 0]], F, "cnc_setup3")

    # установка 4: каннелюры, 2 детали в ложементе (ось X, Z0 — верх ложемента)
    if P.reeds:
        V, F = revolve_mesh(P, prof, reeds=True)
        F, _ = orient_outward(V, F)
        Vs, Fs = [], []
        for k, ys in enumerate(I["stations"]):
            Vs.append(V + [0.0, ys, I["h"]])
            Fs.append(F + k * len(V))
        write_stl(OUT / "cnc_setup4_flutes_2pcs.stl", np.vstack(Vs), np.vstack(Fs), "cnc_setup4")
    print("STL готовы")

    # --- розетка: 16-битная карта высот (для «рельеф из изображения») ---
    if P.rosette:
        from PIL import Image
        g, Z = end_heightmap(P, prof)
        lo, hi = prof.marks["xe"], float(np.nanmax(Z))
        img = np.nan_to_num((Z - lo) / (hi - lo), nan=0.0)
        Image.fromarray(np.round(np.clip(img, 0, 1) * 65535).astype(np.uint16)).save(
            OUT / "rosette_heightmap_16bit.png")
        (OUT / "rosette_heightmap.txt").write_text(
            f"rosette_heightmap_16bit.png: {Z.shape[1]}x{Z.shape[0]} px, {g[1] - g[0]:.2f} мм/px, "
            f"поле {2 * g[-1]:.0f}x{2 * g[-1]:.0f} мм, центр = ось детали.\n"
            f"Чёрный = Z {lo:.2f} мм, белый = Z {hi:.2f} мм от опорного торца (высота рельефа "
            f"{hi - lo:.2f} мм).\n", encoding="utf-8")

    # --- DXF ---
    make_profile_dxf(P, OUT / "finial_profile.dxf")
    make_layout_dxf(P, L, OUT / "cnc_setup1-2_layout.dxf")
    if P.rosette:
        make_fixture_dxf(P, OUT / "cnc_setup3_fixture.dxf")
    if P.reeds:
        make_index_dxf(P, OUT / "cnc_setup4_nest.dxf")
    print("DXF готовы")

    # --- STEP (+ STL оснастки) ---
    v = export_solid(body_solid(P), OUT / "finial_body_smooth", stl=False)
    print(f"finial_body_smooth.step: {v / 1000:.1f} см³ (тело после установок 1–2)")
    if P.reeds:
        export_solid(index_half_solid(P), OUT / "fixture_setup4_index_half")
        export_solid(nest_solid(P), OUT / "fixture_setup4_nest", stl_tol=0.05)
        print("оснастка установки 4: STEP + STL")

    # --- проверки ---
    c = checks(P)
    lines = [f"мин. вогнутый радиус профиля (установки 1–2): R{c['min_concave_profile']:.2f}"]
    lines += [f"установки 1–2, симуляция чистовой сферой ⌀{k.split('_')[1]}: макс. недорез {v:.3f} мм"
              for k, v in c.items() if k.startswith("ball_")]
    if P.reeds:
        lines += [
            f"установка 4: запас между стенками каннелюр и конусом фрезы {c['index_draft']:.1f}°",
            f"установка 4, симуляция конусной сферы R{P.flute_tool_r:g}: недорез на валиках "
            f"{c['flute_max_leftover']:.3f} мм, у дна канавки {c['flute_valley_leftover']:.2f} мм "
            f"(радиус кончика фрезы)",
        ]
    (OUT / "checks.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))

    # --- чертёж и картинки ---
    if not a.no_render:
        import render
        render.make(P, OUT)
    import drawing
    drawing.make(P, prof, cnc, L, c, OUT)


if __name__ == "__main__":
    main()
