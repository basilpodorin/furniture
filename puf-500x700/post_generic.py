"""Постпроцессор-заглушка: G-код в стиле Mach3 / NcStudio (.tap).

ВНИМАНИЕ: это НЕ постпроцессор цеха (в этой среде его нет). Формат типовой:
G21/G90, ноль — левый нижний угол листа, Z0 — верх листа, одна фреза.
Перед запуском проверить в симуляторе или заменить этот модуль цеховым:
на вход приходят штрихи cam.Stroke (опускание в первую точку, рез, подъём).
"""
import params as P


def f(v):
    s = f"{v:.3f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def post(strokes, title, stats):
    o = []
    o.append("%")
    o.append(f"({title})")
    o.append("(GENERIC POST - NOT SHOP POSTPROCESSOR - VERIFY IN SIMULATOR)")
    o.append(f"(SHEET {f(P.SHEET[0])}x{f(P.SHEET[1])} PLY {f(P.T)}  ZERO: SHEET LOWER-LEFT, Z0 = TOP OF SHEET)")
    o.append(f"(TOOL: D{f(P.TOOL_D)} FLAT SPIRAL, CUT DEPTH {f(P.CUT_DEPTH)}, TABS {f(P.TAB_W)}x{f(P.TAB_H)})")
    o.append(f"(CUT LENGTH {stats['cut_m']:.1f} M, EST. {stats['minutes']:.0f} MIN)")
    o.append("G21 G90 G17 G40 G49 G80")
    o.append(f"G0 Z{f(P.SAFE_Z)}")
    o.append(f"M3 S{P.SPINDLE}")
    o.append("G4 P3")
    last_group = None
    for s in strokes:
        if s.group != last_group:
            o.append(f"({s.group.upper()})")
            last_group = s.group
        x, y, z = s.points[0]
        o.append(f"G0 X{f(x)} Y{f(y)}")
        o.append("G0 Z1")
        o.append(f"G1 Z{f(z)} F{f(P.F_PLUNGE)}")
        feed_set = False
        px, py, pz = x, y, z
        for x, y, z in s.points[1:]:
            if abs(x - px) < 1e-6 and abs(y - py) < 1e-6:
                if abs(z - pz) > 1e-6:
                    o.append(f"G1 Z{f(z)} F{f(P.F_PLUNGE)}")
                    feed_set = False
            else:
                w = f"G1 X{f(x)} Y{f(y)}"
                if abs(z - pz) > 1e-6:
                    w += f" Z{f(z)}"
                if not feed_set:
                    w += f" F{f(P.F_CUT)}"
                    feed_set = True
                o.append(w)
            px, py, pz = x, y, z
        o.append(f"G0 Z{f(P.SAFE_Z)}")
    o.append("M5")
    o.append(f"G0 Z{f(P.SAFE_Z)}")
    o.append("G0 X0 Y0")
    o.append("M30")
    o.append("%")
    return "\n".join(o) + "\n"
