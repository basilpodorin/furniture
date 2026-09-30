"""out/preview.html — предпросмотр пакета одним файлом, работает без интернета.

3D-модель пуфа из тех же контуров, что идут в DXF; раскрой листа с
проигрыванием УП; листы А3; спецификация и проверки.
"""
import base64
import io
import json
from pathlib import Path

import params as P
import parts as PR
import soft
from geom import K90, Contour, rounded_rect

HERE = Path(__file__).parent


def _n(v, nd=1):
    v = round(float(v), nd)
    return int(v) if v.is_integer() else v


def _pts(contour, tol=0.3):
    return [[_n(x, 2), _n(y, 2)] for x, y in contour.points(tol)]


def _extrude(mid, label, grp, color, level, outer, holes, depth, u, v, w, o, key=""):
    return {"id": mid, "label": label, "key": key, "grp": grp, "color": color, "level": level,
            "kind": "extrude", "outer": outer, "holes": holes, "depth": depth,
            "m": [*u, *v, *w, *[_n(c, 2) for c in o]]}


def meshes():
    z = P.z_levels()
    k = PR.by_key()
    out = []
    X, Y, Z = (1, 0, 0), (0, 1, 0), (0, 0, 1)
    NY = (0, -1, 0)

    # --- плиты: контур в XY от центра, выдавливание вверх
    plates = (("P1B", z["lo_frame_bot"], 1), ("P1T", z["lo_frame_top"] - P.T, 3),
              ("P2B", z["up_frame_bot"], 5), ("P2T", z["up_frame_top"] - P.T, 7))
    for key, z0, lvl in plates:
        p = k[key]
        out.append(_extrude(key, f"{key} — {p.name}", "frame", "#e9cc9f", lvl, _pts(p.outline),
                            [_pts(c) for _, c in p.holes], P.T, X, Y, Z, (0, 0, z0), key))

    # --- стенки: контур (вдоль, вверх), выдавливание по толщине; базис правый
    def walls(sfx, z0, lvl):
        items = []
        for sy in (-1, 1):
            items.append((f"W{sfx}L", f"W{sfx}L-{(sy + 3) // 2}", X, Z, NY,
                          (-P.WALL_LONG / 2, sy * PR.LONG_Y + P.T / 2, z0)))
        for sx in (-1, 1):
            items.append((f"W{sfx}S", f"W{sfx}S-{(sx + 3) // 2}", Y, Z, X,
                          (sx * PR.SHORT_X - P.T / 2, -P.WALL_SHORT / 2, z0)))
        if sfx == "2":
            items.append(("W2P", "W2P", Y, Z, X, (-P.T / 2, -P.WALL_SHORT / 2, z0)))
        for key, mid, u, v, w, o in items:
            p = k[key].normalized()
            col = "#cfa56d" if key == "W2P" else "#dcb47f"
            out.append(_extrude(mid, f"{key} — {p.name} ({p.module} модуль)", "frame", col, lvl,
                                _pts(p.outline), [], P.T, u, v, w, o, key))

    walls("1", z["lo_frame_bot"], 2)
    walls("2", z["up_frame_bot"], 6)

    # --- картон — кольцом; боковой ППУ — протяжкой профиля со скруглёнными кромками
    plate = _pts(rounded_rect(P.PL, P.PW, P.PLATE_R))
    card = _pts(rounded_rect(soft.CARD_W, soft.CARD_H, soft.CARD_R))
    r, t = P.EDGE_R, P.FOAM
    for mod, z0, hf, lvl, top_r in (("нижний", z["lo_frame_bot"], P.HF_LO, 2, True),
                                    ("верхний", z["up_frame_bot"], P.HF_UP, 6, False)):
        z1 = z0 + hf
        out.append(_extrude(f"card-{mod}", f"Картон 3 мм ({mod} модуль)", "card", "#9d9d9d", lvl,
                            card, [plate], hf, X, Y, Z, (0, 0, z0)))
        prof = Contour([(0, z0, 0), (t - r, z0, K90), (t, z0 + r, 0)]
                       + ([(t, z1 - r, K90), (t - r, z1, 0)] if top_r else [(t, z1, 0)]) + [(0, z1, 0)])
        out.append({"id": f"foam-{mod}", "label": f"ППУ {P.FOAM_SIDE} 30 — бока ({mod} модуль)", "grp": "foam",
                    "color": "#f1e19a", "level": lvl, "kind": "sweep", "path": card, "prof": _pts(prof, 0.5)})
    sb = P.FOAM / 2
    out.append({"id": "foam-seat", "label": f"ППУ {P.FOAM_SEAT} 30 — сиденье", "grp": "foam", "color": "#f6ea9f",
                "level": 8, "kind": "pillow", "bevel": sb, "z0": z["up_frame_top"], "h": P.FOAM,
                "outer": _pts(rounded_rect(soft.FOAM_W - 2 * sb, soft.FOAM_H - 2 * sb, soft.FOAM_R - sb))})

    # --- чехлы: скруглённые «подушки» (выдавливание с фаской-скруглением)
    b = P.EDGE_R
    for mid, z0, z1, lvl, name in (("cover-lo", P.LEG_H, z["lo_top"], 2, "нижний"),
                                   ("cover-up", z["lo_top"], z["edge_top"], 6, "верхний")):
        out.append({"id": mid, "label": f"Чехол {P.FABRIC_NAME} + холкон ({name} модуль)", "grp": "cover",
                    "color": "#c8735e", "level": lvl, "kind": "pillow",
                    "outer": _pts(rounded_rect(P.L - 2 * b, P.W - 2 * b, soft.OUT_R - b)),
                    "bevel": b, "z0": z0, "h": z1 - z0})

    # --- крепёж и опоры
    lx, ly = P.PL / 2 - P.LEG_INSET, P.PW / 2 - P.LEG_INSET
    for i, (x, y) in enumerate(PR.four(lx, ly)):
        out.append({"id": f"leg{i}", "label": P.LEG, "grp": "hw", "color": "#2d2d2d", "level": 0,
                    "kind": "cyl", "r": P.LEG_D / 2, "x": x, "y": y, "z0": 0, "h": P.LEG_H})
    bx, by = P.BOLT_XY
    zb = z["lo_frame_top"] - P.T
    for i, (x, y) in enumerate(PR.four(bx, by)):
        out.append({"id": f"bolt{i}", "label": P.BOLT, "grp": "hw", "color": "#8c9096", "level": 4,
                    "kind": "cyl", "r": 4, "x": x, "y": y, "z0": zb - 1.6, "h": 40})
        out.append({"id": f"head{i}", "label": P.BOLT, "grp": "hw", "color": "#6d7177", "level": 4,
                    "kind": "cyl", "r": 6.5, "seg": 6, "x": x, "y": y, "z0": zb - 6.9, "h": 5.3})
        out.append({"id": f"tnut{i}", "label": P.TNUT, "grp": "hw", "color": "#a9adb3", "level": 5,
                    "kind": "cyl", "r": 11, "x": x, "y": y, "z0": z["up_frame_bot"] + P.T, "h": 1.5})
    return out


def _label_pos(part):
    """Как в DXF: у рамок — на нижней полке между пазами, у остальных — по центру."""
    x0, y0, x1, y1 = part.outline.bbox()
    win = [c for k, c in part.holes if k == "window"]
    if win:
        return x0 + 212, (y0 + win[0].bbox()[1]) / 2
    return (x0 + x1) / 2, (y0 + y1) / 2


def nest_data(placed):
    out = []
    for pl in placed:
        lx, ly = _label_pos(pl.part)
        out.append({"label": pl.label, "parent": pl.parent, "outer": _pts(pl.part.outline, 0.3),
                    "holes": [_pts(c, 0.3) for _, c in pl.part.holes], "lx": _n(lx), "ly": _n(ly),
                    "marks": [[_n(x), _n(y)] for x, y in pl.part.marks]})
    return {"sheet": list(P.SHEET), "parts": out}


def strokes_data(strokes):
    out = []
    for s in strokes:
        flat = []
        for x, y, zz in s.points:
            flat += [_n(x), _n(y), _n(zz, 2)]
        out.append({"g": s.group, "l": s.label, "p": flat})
    return out


def sheet_images():
    from PIL import Image
    titles = ["Общий вид, разрез, узел стяжки", "Плиты и рамки", "Стенки, узел шипа", "Раскрой фанеры",
              "Раскрой ППУ, холкона, ткани", "Схема сборки"]
    out = []
    for i, png in enumerate(sorted((HERE / "out" / "png").glob("sheet_*.png"))):
        im = Image.open(png).convert("RGB").quantize(colors=96, method=Image.Quantize.MEDIANCUT)
        buf = io.BytesIO()
        im.save(buf, "PNG", optimize=True)
        out.append({"title": f"Лист {i + 1}. {titles[i] if i < len(titles) else png.stem}",
                    "src": "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()})
    return out


def spec_data(chk, ply_area, stats):
    frame = [[p.key, p.name, p.module, p.qty, "{:g} x {:g}".format(*p.size())] for p in PR.all_parts()]
    softp = [[p.key, p.name, p.material, p.qty, f"{p.w:g} x {p.h:g}" + (f" R{p.r:g}" if p.r else ""), p.note]
             for p in soft.foam_pieces() + soft.holcon_pieces() + soft.fabric_pieces() + soft.other_pieces()]
    _, fab = soft.shelf_pack(soft.fabric_pieces(), P.FABRIC_ROLL_W)
    mass = ply_area * P.T / 1000 * P.PLY_DENSITY
    return {
        "frame": frame, "soft": softp,
        "hw": [[P.BOLT, 4], [P.TNUT, 4], ["Прокладка 2 мм (фетр/ткань) Ø30", 4], [P.LEG, 4], [P.LEG_SCREW, 4]],
        "checks": [[bool(g), t] for g, t in chk],
        "facts": [
            ["Габарит", f"{P.L:g} × {P.W:g} × {P.H:g} мм, 2 модуля по {P.MODULE_H:g}"],
            ["Каркас", f"{P.PLY_NAME}, {ply_area:.2f} м², ≈{mass:.1f} кг, 1 лист {P.SHEET[0]:g}×{P.SHEET[1]:g}"],
            ["Мягкие слои на сторону", f"ткань {P.FABRIC:g} + холкон {P.HOLCON_SIDE:g} + ППУ {P.FOAM:g} + "
                                       f"картон {P.CARD:g} = {P.SIDE_STACK:g} мм"],
            ["ППУ", f"сиденье {P.FOAM_SEAT} 30, бока {P.FOAM_SIDE} 30"],
            ["Ткань", f"{P.FABRIC_NAME}: {fab / 1000:.2f} м.п. при ширине {P.FABRIC_ROLL_W:g}"],
            ["УП", f"фреза Ø{P.TOOL_D:g}, {stats['strokes']} операций, {stats['cut_m']:.0f} м, "
                   f"≈{stats['minutes']:.0f} мин (типовой пост)"],
        ],
    }


CDN = "https://cdn.jsdelivr.net/npm/three@0.147.0"


def build_preview(out, placed, strokes, stats, chk, ply_area, web=None):
    """out/preview.html — офлайн (three.js внутри файла). web — путь для страницы-Artifact:
    без собственного каркаса документа, three.js с CDN из списка разрешённых."""
    data = {
        "name": P.NAME, "code": P.CODE,
        "cam": {"tool": P.TOOL_D, "depth": P.CUT_DEPTH, "tab": -(P.T - P.TAB_H), "feed": P.F_CUT,
                "stats": {k: _n(v, 2) for k, v in stats.items()}},
        "meshes": meshes(), "nest": nest_data(placed), "strokes": strokes_data(strokes),
        "sheets": sheet_images(), "spec": spec_data(chk, ply_area, stats),
    }
    tpl = (HERE / "preview_template.html").read_text(encoding="utf-8")
    js = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    tpl = tpl.replace("@DATA@", js)
    head, body = tpl.split("<!--@BODY@-->")

    three = (HERE / "vendor" / "three.min.js").read_text(encoding="utf-8")
    orbit = (HERE / "vendor" / "OrbitControls.js").read_text(encoding="utf-8")
    offline = ("<!doctype html>\n<html lang=\"ru\">\n<head>\n<meta charset=\"utf-8\">\n"
               "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1, viewport-fit=cover\">\n"
               + head + "</head>\n<body>\n"
               + body.replace("<!--@LIBS@-->", f"<script>{three}</script>\n<script>{orbit}</script>")
               + "</body>\n</html>\n")
    (out / "preview.html").write_text(offline, encoding="utf-8")
    if web:
        libs = (f'<script src="{CDN}/build/three.min.js"></script>\n'
                f'<script src="{CDN}/examples/js/controls/OrbitControls.js"></script>')
        Path(web).write_text(head + body.replace("<!--@LIBS@-->", libs), encoding="utf-8")
    return out / "preview.html"
