"""Сборка всех материалов проекта кресла ERIS.

    python build.py            # всё
    python build.py --no-step  # без STEP (быстрее)

Результат — в папке out/.
"""
import argparse
import csv
import time
from pathlib import Path

import numpy as np

import params as P
from lib.checks import clearance_report
from lib.foam import GRADES, Soft
from lib.frame import Frame, S

OUT = Path(__file__).resolve().parent / "out"
TRANSLIT = str.maketrans({"П": "P", "Р": "R", "Н": "N", "В": "V", "С": "S", "Г": "G", "Т": "T", "О": "O", "Б": "B",
                          "л": "l", "п": "p"})

FOAM_COLORS = {"сиденье": "#eec35a", "спинка": "#e59f8b", "подлокотники": "#f1da8e",
               "валик": "#9db6c8", "наружные стенки": "#c9ccd1"}


def latin(code):
    return code.translate(TRANSLIT)


def summary(frame, soft):
    sec = S.section(0, 0.0)
    ys = np.array(sec.exterior.coords)
    seat_top = ys[(ys[:, 0] > -300) & (ys[:, 0] < -200), 1].max()
    top = S.V[:, 2].max()
    top_flat = np.percentile(S.V[S.V[:, 2] > top - 30, 2], 50)
    ply = sum(p.mass_kg for p in frame.parts)
    foam = sum(f.mass_kg for f in soft.pieces)
    steel = np.pi * (P.DISC_D / 2000) ** 2 * P.DISC_T / 1000 * 7850
    misc = soft.info["surface_m2"] * (0.45 + 0.25) + 3.5   # ткань, синтепон, ремни, полосы, крепёж
    swivel = 2.5
    levels = [
        ("Накладки под диском", f"0–{P.PAD_H}"),
        (f"Стальной диск Ø{P.DISC_D}×{P.DISC_T}", f"{P.PAD_H}–{P.PAD_H + P.DISC_T}"),
        (f"Механизм {P.SWIVEL_SIZE}×{P.SWIVEL_SIZE}", f"{P.PAD_H + P.DISC_T}–{P.Z_P1}"),
        ("Дно П1 и плита П2", f"{P.Z_P1}–{P.Z_P1 + 2 * P.PLY}"),
        ("Плита уровня сиденья П3", f"{P.Z_P3}–{P.Z_P3 + P.PLY}"),
        ("Верх сиденья у фасада", f"≈{seat_top:.0f}"),
        ("Верхняя обвязка П4", f"{P.Z_P4}–{P.Z_P4 + P.PLY}"),
        ("Верх спинки (кант)", f"≈{top_flat:.0f}"),
    ]
    si = soft.info
    foam_rows = [
        ("Сиденье С1+С2+С3", "EL 3542 80 · HR 3530 клин · ST 2536 20",
         f"{si['seat']['t_front']:.0f}/{si['seat']['t_mid']:.0f}/{si['seat']['t_back']:.0f}",
         FOAM_COLORS["сиденье"]),
        ("Спинка Сп1+Сп2", "HR 3530 50 · HR 2520 профильный", f"{si['back']['t_min']:.0f}–{si['back']['t_max']:.0f}",
         FOAM_COLORS["спинка"]),
        ("Подлокотники внутри Пл1", "HR 3530", f"{soft.arm_t:.0f}", FOAM_COLORS["подлокотники"]),
        ("Верхний валик В1+В2", "EL 2540 50 · HR 3530 50", f"{si['top']['height']:.0f}", FOAM_COLORS["валик"]),
        ("Наружные стенки Н1, Н2", "ST 2536", "40", FOAM_COLORS["наружные стенки"]),
        ("Боковина снаружи Н3 (под Н1)", "ST 2536 по шаблону", "0–40", FOAM_COLORS["наружные стенки"]),
        ("Обёртка", "синтепон 200 г/м²", "≈10", "#ffffff"),
    ]
    n_inst = sum(p.qty for p in frame.parts)
    totals = [
        ("Фанера ФК 18 и 15 мм", f"{ply:.1f} кг"),
        ("Деталей каркаса", f"{n_inst} шт., {len(frame.parts)} наим."),
        ("Поролон", f"{foam:.1f} кг"),
        ("Стальной диск", f"{steel:.1f} кг"),
        ("Кресло в сборе (оценка)", f"≈{ply + foam + steel + misc + swivel:.0f} кг"),
    ]
    stab = stability(ply + foam + misc + swivel * 0.5, steel + swivel * 0.5)
    return dict(levels=levels, foam=foam_rows, totals=totals, stability=stab,
                mass=dict(ply=ply, foam=foam, steel=steel, misc=misc, swivel=swivel),
                seat_top=float(seat_top), top=float(top_flat))


def stability(m_body, m_base):
    """Опрокидывание: опорный многоугольник — накладки на окружности DISC_PAD_R.
    Центр масс кресла принят на оси поворота. Возвращает список случаев с запасом."""
    edge = P.DISC_PAD_R * np.cos(np.pi / P.DISC_PADS)       # расстояние до стороны многоугольника
    W = m_body + m_base
    cases = [
        ("100 кг сидит на переднем краю сиденья (y = −350)", 100, 350),
        ("100 кг сидит на подлокотнике (x = 330)", 100, 330),
        ("50 кг давит на торец подлокотника при вставании", 50, np.hypot(320, 280)),
    ]
    ply_disc = np.pi * (P.DISC_D / 2000) ** 2 * 0.018 * P.PLY_RHO     # фанерный диск 18 мм
    W_ply = m_body + (m_base - np.pi * (P.DISC_D / 2000) ** 2 * P.DISC_T / 1000 * 7850) + ply_disc
    out = []
    for name, m, d in cases:
        tip = m * max(d - edge, 0)
        out.append(dict(name=name, sf=(W * edge / tip) if tip > 0 else float("inf"),
                        sf_ply=(W_ply * edge / tip) if tip > 0 else float("inf")))
    return dict(edge=edge, mass=W, mass_ply=W_ply, cases=out)


def part_info(frame):
    return {p.code: dict(material=p.material, note=p.note) for p in frame.parts}


def write_bom(frame, soft, summ, path: Path, sheets):
    """sheets — список толщин фанеры по листам раскроя."""
    rows = [("Раздел", "Код", "Наименование", "Материал", "Размер, мм", "Кол-во", "Примечание")]
    for p in frame.parts:
        x0, y0, x1, y1 = p.shape.bounds
        rows.append(("Каркас", p.code, p.name, p.material, f"{x1 - x0:.0f}×{y1 - y0:.0f}×{p.thickness:.0f}",
                     p.qty, p.note))
    for t in sorted(set(sheets), reverse=True):
        rows.append(("Каркас", "—", f"Листы фанеры {t:.0f} мм для раскроя",
                     f"Фанера берёзовая ФК {t:.0f} мм, 1525×1525", "", sheets.count(t),
                     f"раскрой — out/cnc/raskroy_{t:.0f}mm_list_*.dxf"))
    for f in soft.pieces:
        x0, y0, x1, y1 = f.pattern.bounds
        g = GRADES[f.grade]
        rows.append(("Поролон", f.code, f.name, f"ППУ {f.grade} ({g['rho']} кг/м³, {g['kpa']} кПа)",
                     f"{x1 - x0:.0f}×{y1 - y0:.0f}×{f.thickness:.0f}", f.qty, f.note))
    for s in soft.sheet_goods:
        rows.append(("Листовые", "—", s["name"], s["material"], s["size"], s["qty"], s.get("note", "")))
    bi = soft.info["belts"]
    total = sum(b["length"] * (1 - b["stretch"]) for b in soft.belts) / 1000
    rows.append(("Ремни", "—", "Ремень мебельный эластичный 50 мм (удлинение 40–60 %)", "",
                 f"сиденье {bi['seat_long']}+{bi['seat_cross']}, спинка {bi['back']}", "",
                 f"≈{total:.1f} м.п. с запасом на хвосты; натяг 5–8 %"))
    hw = [
        ("Механизм", "Поворотный механизм 195×195×25, 360°", "сталь", "", 1, "Яндекс Маркет 5583855927"),
        ("Основание", f"Диск Ø{P.DISC_D}×{P.DISC_T}", "сталь Ст3, лазерная резка, порошковая покраска",
         "", 1, "out/cnc/disk_osnovaniya.dxf"),
        ("Основание", "Накладки фетр/полиуретан Ø30", "", f"h={P.PAD_H}", P.DISC_PADS, "по окружности R270"),
        ("Крепёж", "Винт М6×16 потай DIN 7991 + гайка М6 с нейлоном", "", "", 4, "нижняя пластина к диску"),
        ("Крепёж", "Болт М6×30 DIN 933 + шайба", "", "", 4, "верхняя пластина к П1/П2"),
        ("Крепёж", "Футорка М6 под Ø8 (вкручиваемая)", "", "", 4, "в П2 сверху"),
        ("Крепёж", "Саморез 4×50", "", "", 20, "боковины к шипам П3/ПГ, П4 к уступам боковин"),
        ("Крепёж", "Шкант берёзовый 8×40", "", "", 2, "П4 к боковинам"),
        ("Крепёж", "Саморез 4×40 (4×30 для П2)", "", "", 120, "плиты к рёбрам через шипы, П2 к П1, бобышки"),
        ("Крепёж", "Бобышка 30×30×150 (брусок сосна)", "", "", 8, "углы короба: П1/ПГ/боковины"),
        ("Крепёж", "Клей ПВА D3 столярный", "", "", "0,5 кг", "все соединения шип–паз"),
        ("Крепёж", "Скобы 80-й серии 8–14 мм", "", "", "1 уп.", "ремни, полосы, ткань"),
        ("Крепёж", "Клей для ППУ (распыляемый)", "", "", "1 л", ""),
    ]
    for sec, name, mat_, size, q, note in hw:
        rows.append((sec, "—", name, mat_, size, q, note))
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        csv.writer(f, delimiter=";").writerows(rows)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-step", action="store_true")
    ap.add_argument("--no-pdf", action="store_true")
    args = ap.parse_args()
    t0 = time.time()
    OUT.mkdir(exist_ok=True)
    frame = Frame()
    soft = Soft(frame)
    summ = summary(frame, soft)
    print(f"каркас: {len(frame.parts)} наименований; поролон: {len(soft.pieces)} деталей")

    # проверка толщин обивки
    rep = clearance_report(frame)
    with open(OUT / "proverka_zazorov.txt", "w", encoding="utf-8") as f:
        f.write("Минимальная глубина деталей каркаса под поверхностью обивки, мм\n")
        f.write("Номинал: стенки 40–50, кромка дна ≥20. Меньше 40 — у канта сиденья (z≈305–320, ткань\n"
                "заправляется в шов, П3 ≈41), у шва торца подлокотника (z≈400–480, боковина ≈34 — контур\n"
                "боковины выпуклый, без S-изгиба) и у скругления низа (боковина, концы перегородок,\n"
                "низ рёбер ≈28–37 — там поролон заворачивается под дно).\n\n")
        for code, name, d, p in rep:
            f.write(f"{code:5s} {name:48s} {d:6.1f}   точка {np.round(p).astype(int).tolist()}\n")

    from lib import export_cnc as X
    for old in [*(OUT / "cnc").glob("raskroy_*.dxf"), *(OUT / "cnc" / "parts").glob("*.dxf"),
                *(OUT / "porolon").glob("*.dxf")]:
        old.unlink()
    placed, sheets = X.export_frame(frame, OUT / "cnc")
    # латинские имена файлов деталей (станки и CAM не всегда понимают кириллицу)
    for fpath in (OUT / "cnc" / "parts").glob("*.dxf"):
        new = fpath.with_name(latin(fpath.stem) + ".dxf")
        if new != fpath:
            fpath.replace(new)
    X.export_disc(OUT / "cnc")
    X.export_foam(soft, OUT / "porolon")
    for fpath in (OUT / "porolon").glob("*.dxf"):
        new = fpath.with_name(latin(fpath.stem) + ".dxf")
        if new != fpath:
            fpath.replace(new)
    write_bom(frame, soft, summ, OUT / "specifikaciya.csv", sheets)
    print("DXF: листы раскроя —", ", ".join(f"{t:.0f} мм" for t in sheets))

    from lib.export_3d import export_stl, viewer_data
    from lib.model import viewer_mesh
    vm = viewer_mesh()
    from lib.geom import Surface, triangulate
    export_stl(Surface(vm[0], triangulate(vm[1])), OUT / "3d" / "eris_obivka.stl")
    if not args.no_step:
        from lib.export_3d import export_step
        export_step(frame, OUT / "3d" / "eris_karkas.step")
        print("STEP готов")
    from lib.viewer import build_html
    data = viewer_data(frame, soft, vm)
    data["info"] = part_info(frame)
    data["summary"] = {k: summ[k] for k in ("levels", "foam", "totals")}
    (OUT / "eris_3d.html").write_text(build_html(data), encoding="utf-8")

    if not args.no_pdf:
        from lib.drawings import make_pdf
        make_pdf(frame, soft, summ, placed, sheets, OUT / "eris_chertezhi.pdf")
        print("PDF готов")
    print(f"готово за {time.time() - t0:.0f} с → {OUT}")


if __name__ == "__main__":
    main()
