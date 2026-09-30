"""Мягкая часть: ППУ 30 мм, холкон, ткань, картон, спанбонд.

Контуры по плану (от центра, мм):
плита 624x424 R30 -> картон 630x430 R33 -> ППУ 690x490 R63 -> по ткани 700x500 R68.
"""
import math
from dataclasses import dataclass

import params as P


@dataclass
class Piece:
    key: str
    name: str
    material: str
    qty: int
    w: float           # длина (поперёк рулона / вдоль листа)
    h: float           # ширина / высота
    r: float = 0.0     # скругление углов (у сиденья и верха чехла)
    note: str = ""


# контуры по слоям
CARD_W, CARD_H, CARD_R = P.PL + 2 * P.CARD, P.PW + 2 * P.CARD, P.PLATE_R + P.CARD
FOAM_W, FOAM_H, FOAM_R = CARD_W + 2 * P.FOAM, CARD_H + 2 * P.FOAM, CARD_R + P.FOAM
OUT_R = P.PLATE_R + P.SIDE_STACK


def foam_strip_half():
    """Половина боковой ленты ППУ: длина по средней линии слоя + 5 на поджатие стыка."""
    mean = P.rounded_perimeter(CARD_W + P.FOAM, CARD_H + P.FOAM, CARD_R + P.FOAM / 2)
    return math.ceil(mean / 2 + 5)


def arc_loss(r):
    """На сколько скругление кромки R укорачивает путь ткани против прямого угла."""
    return 2 * r - math.pi * r / 2


def fabric_band_heights():
    """Высоты бортиков чехла: шов/запах + бок + уход под плиту до скобы + припуск."""
    under = P.SIDE_STACK + P.FABRIC_STAPLE_IN + P.FABRIC_GRIP     # под рамку до скобы
    up = P.FABRIC_SEAM + P.MODULE_H - arc_loss(P.EDGE_R) + under
    lo = under + P.MODULE_H - 2 * arc_loss(P.EDGE_R) + under
    return math.ceil(up / 10) * 10, math.ceil(lo / 10) * 10


def fabric_band_half():
    per = P.rounded_perimeter(P.L, P.W, OUT_R)
    return math.ceil(per / 2 + 2 * P.FABRIC_SEAM)


def foam_pieces():
    half = foam_strip_half()
    return [
        Piece("F-SEAT", "Сиденье (верхний модуль)", f"ППУ {P.FOAM_SEAT} 30 мм", 1,
              FOAM_W, FOAM_H, FOAM_R,
              "кромка на клей с обжимом на торец боковины -> скругление ~R30"),
        Piece("F-UP", "Бок верхнего модуля (половина)", f"ППУ {P.FOAM_SIDE} 30 мм", 2,
              half, P.HF_UP, 0,
              f"вровень с плитами; нижняя наружная кромка R{P.EDGE_R:g}"),
        Piece("F-LO", "Бок нижнего модуля (половина)", f"ППУ {P.FOAM_SIDE} 30 мм", 2,
              half, P.HF_LO, 0,
              f"вровень с плитами; верхняя и нижняя наружные кромки R{P.EDGE_R:g}"),
    ]


def holcon_pieces():
    half = math.ceil(P.rounded_perimeter(P.L, P.W, OUT_R) / 2)
    return [
        Piece("H-TOP", "Верх сиденья", f"Холкон {P.HOLCON_GSM} г/м²", 1,
              P.L + 20, P.W + 20, OUT_R + 10, "заходит на кромку на 10"),
        Piece("H-UP", "Бок верхнего модуля (половина)", f"Холкон {P.HOLCON_GSM} г/м²", 2,
              half, P.MODULE_H, 0, "от шва сиденья до низа"),
        Piece("H-LO", "Бок нижнего модуля (половина)", f"Холкон {P.HOLCON_GSM} г/м²", 2,
              half, P.MODULE_H, 0, "бок, без верха и низа"),
    ]


def fabric_pieces():
    up, lo = fabric_band_heights()
    half = fabric_band_half()
    s = P.FABRIC_SEAM
    return [
        Piece("T-TOP", "Верх чехла (верхний модуль)", P.FABRIC_NAME, 1,
              P.L + 2 * s, P.W + 2 * s, OUT_R + s, f"припуск на шов {s:g}; ворс -> к лицевой длинной стороне"),
        Piece("T-UP", "Бортик верхнего модуля (половина)", P.FABRIC_NAME, 2,
              half, up, 0, "шов с верхом по ребру без канта; низ — под рамку на скобу"),
        Piece("T-LO", "Бортик нижнего модуля (половина)", P.FABRIC_NAME, 2,
              half, lo, 0, "верх и низ — под рамки на скобу; без верхней панели"),
    ]


def other_pieces():
    card_len = math.ceil(P.rounded_perimeter(P.PL, P.PW, P.PLATE_R) / 2 + 15)
    return [
        Piece("C-UP", "Картон 3 мм, бок верхнего каркаса (половина)", "Картон 3 мм", 2,
              card_len, P.HF_UP, 0, "стык по середине торца, на скобу к кромкам плит"),
        Piece("C-LO", "Картон 3 мм, бок нижнего каркаса (половина)", "Картон 3 мм", 2,
              card_len, P.HF_LO, 0, "стык по середине торца, на скобу к кромкам плит"),
        Piece("S-BOT", "Спанбонд на дно", "Спанбонд 60-80 г/м²", 1,
              P.PL - 20, P.PW - 20, 0, "после монтажа болтов, на скобу к нижней рамке"),
    ]


# ---------------------------------------------------------------- раскладки
def shelf_pack(pieces, width, gap=0.0):
    """Простая укладка полками: детали кладутся строками поперёк ширины рулона/листа.

    Детали с w > width не поворачиваются (направление ворса важно).
    Возвращает ([(piece, i, x, y)], длина_расхода).
    """
    items = [(p, i) for p in pieces for i in range(p.qty)]
    assert all(p.w <= width for p, _ in items), "деталь шире рулона/листа"
    items.sort(key=lambda t: -t[0].h)
    rows, out = [], []
    for p, i in items:
        for row in rows:
            if row["x"] + p.w <= width + 1e-6 and p.h <= row["h"] + 1e-6:
                out.append((p, i, row["x"], row["y"]))
                row["x"] += p.w + gap
                break
        else:
            y = rows[-1]["y"] + rows[-1]["h"] + gap if rows else 0.0
            rows.append({"y": y, "h": p.h, "x": p.w + gap})
            out.append((p, i, 0.0, y))
    used = max(y + p.h for p, i, x, y in out)
    return out, used


def foam_layouts():
    """Отдельно по маркам: ППУ сиденья и боковая."""
    res = {}
    for grade in (P.FOAM_SEAT, P.FOAM_SIDE):
        ps = [p for p in foam_pieces() if grade in p.material]
        res[grade] = shelf_pack(ps, P.FOAM_SHEET[0], gap=5)
    return res


def area_m2(pieces):
    return sum(p.w * p.h * p.qty for p in pieces) / 1e6


def foam_mass():
    m = 0.0
    for p in foam_pieces():
        grade = P.FOAM_SEAT if P.FOAM_SEAT in p.material else P.FOAM_SIDE
        m += p.w * p.h * P.FOAM * p.qty / 1e9 * P.FOAM_DENSITY[grade]
    return m
