"""Сводит raw/*.json в единую базу: Excel (с миниатюрами), CSV, JSON и HTML-галерею."""
import csv
import html
import io
import json
import os
import re
from collections import OrderedDict, defaultdict

from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from PIL import Image

from common import DATA_DIR, PHOTO_MAX_SIDE, PHOTO_QUALITY, RAW_DIR

SOURCES = ["souz_m", "artex", "ametist", "vip_textil"]
SUPPLIER_ORDER = ["Союз-М", "Артекс", "Аметист", "Вип Текстиль"]

# (ключ, заголовок, ширина колонки)
COLUMNS = [
    ("supplier", "Поставщик", 14),
    ("collection", "Коллекция", 18),
    ("article", "Артикул / цвет", 26),
    ("color", "Цвет (как на сайте)", 18),
    ("fabric_type", "Тип ткани", 12),
    ("composition", "Состав", 22),
    ("width_cm", "Ширина, см", 10),
    ("density", "Плотность", 16),
    ("martindale", "Истирание (Мартиндейл), циклов", 14),
    ("martindale_text", "Истирание (как на сайте)", 18),
    ("country", "Страна", 10),
    ("price_rub", "Цена, ₽/п.м.", 11),
    ("old_price_rub", "Цена без скидки, ₽", 11),
    ("price_note", "Комментарий к цене", 26),
    ("stock", "Наличие", 18),
    ("url", "Страница товара", 40),
    ("photo_file", "Фото (файл в папке velour)", 40),
    ("photo_url", "Фото (оригинал на сайте)", 40),
    ("source", "Источник", 30),
    ("collected", "Дата сбора", 11),
]


def load():
    rows = []
    for name in SOURCES:
        path = os.path.join(RAW_DIR, name + ".json")
        if not os.path.exists(path):
            print(f"нет {path}, пропускаю")
            continue
        for r in json.load(open(path, encoding="utf-8")):
            # Артекс: карточки-«обложки» коллекций без цвета и фото — не позиции
            if name == "artex" and not r.get("collection"):
                continue
            if name == "souz_m" and r.get("density_gsm") is not None:
                r["density"] = f"{str(r['density_gsm']).replace('.', ',')} г/м²"
            # вся база — велюр; у Артекса тип записан как «велюр, акции»
            r["fabric_type"] = "Велюр"
            if r.get("martindale") and not r.get("martindale_text"):
                r["martindale_text"] = f"{r['martindale']:,} циклов".replace(",", " ")
            rows.append(r)
    rows.sort(key=lambda r: (SUPPLIER_ORDER.index(r["supplier"]),
                             (r["collection"] or "").lower(), _natural(r["article"])))
    return rows


def _natural(s):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s or "")]


def normalize_photos(rows):
    """Приводит все фото к длинной стороне <= PHOTO_MAX_SIDE."""
    n = 0
    for r in rows:
        if not r.get("photo_file"):
            continue
        p = os.path.join(DATA_DIR, r["photo_file"])
        im = Image.open(p)
        if max(im.size) > PHOTO_MAX_SIDE:
            im = im.convert("RGB")
            im.thumbnail((PHOTO_MAX_SIDE, PHOTO_MAX_SIDE), Image.LANCZOS)
            im.save(p, "JPEG", quality=PHOTO_QUALITY, optimize=True, progressive=True)
            n += 1
    print(f"фото уменьшено до {PHOTO_MAX_SIDE}px: {n}")


def write_csv_json(rows):
    keys = [k for k, _, _ in COLUMNS]
    with open(os.path.join(DATA_DIR, "velour.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow([h for _, h, _ in COLUMNS])
        for r in rows:
            w.writerow(["" if r.get(k) is None else r.get(k) for k in keys])
    with open(os.path.join(DATA_DIR, "velour.json"), "w", encoding="utf-8") as f:
        json.dump([{k: r.get(k) for k in keys} for r in rows], f, ensure_ascii=False, indent=1)


def collections(rows):
    groups = OrderedDict()
    for r in rows:
        groups.setdefault((r["supplier"], r["collection"]), []).append(r)
    out = []
    for (sup, col), items in groups.items():
        def uniq(k):
            vals = sorted({str(i[k]) for i in items if i.get(k) not in (None, "")})
            return "; ".join(vals) if vals else None
        prices = [i["price_rub"] for i in items if i.get("price_rub")]
        out.append({
            "supplier": sup, "collection": col, "count": len(items),
            "composition": uniq("composition"), "width_cm": uniq("width_cm"),
            "density": uniq("density"), "martindale_text": uniq("martindale_text"),
            "country": uniq("country"),
            "price": (f"{min(prices)}" if min(prices) == max(prices) else f"{min(prices)}–{max(prices)}") if prices else uniq("price_note"),
            "url": items[0]["url"],
        })
    return out


def thumb_bytes(path, size=64):
    im = Image.open(path).convert("RGB")
    im.thumbnail((size, size), Image.LANCZOS)
    b = io.BytesIO()
    im.save(b, "JPEG", quality=80)
    b.seek(0)
    return b


def write_xlsx(rows, cols):
    wb = Workbook()
    head_font = Font(bold=True, color="FFFFFF")
    head_fill = PatternFill("solid", fgColor="4B3B6B")
    wrap = Alignment(wrap_text=True, vertical="center")

    # --- Лист 1: все позиции с миниатюрами
    ws = wb.active
    ws.title = "Велюр"
    headers = ["Фото"] + [h for _, h, _ in COLUMNS]
    ws.append(headers)
    ws.column_dimensions["A"].width = 10
    for i, (_, _, w) in enumerate(COLUMNS, start=2):
        ws.column_dimensions[get_column_letter(i)].width = w
    for c in ws[1]:
        c.font, c.fill, c.alignment = head_font, head_fill, wrap
    ws.row_dimensions[1].height = 42
    link_cols = {k: i for i, (k, _, _) in enumerate(COLUMNS, start=2) if k in ("url", "photo_url", "photo_file")}
    for n, r in enumerate(rows, start=2):
        ws.append([None] + [r.get(k) for k, _, _ in COLUMNS])
        ws.row_dimensions[n].height = 50
        for k, ci in link_cols.items():
            v = r.get(k)
            if v:
                cell = ws.cell(row=n, column=ci)
                cell.hyperlink = v
                cell.style = "Hyperlink"
        for ci in range(2, len(COLUMNS) + 2):
            ws.cell(row=n, column=ci).alignment = wrap
        if r.get("photo_file"):
            img = XLImage(thumb_bytes(os.path.join(DATA_DIR, r["photo_file"])))
            ws.add_image(img, f"A{n}")
    ws.freeze_panes = "D2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{len(rows) + 1}"

    # --- Лист 2: коллекции
    ws2 = wb.create_sheet("Коллекции")
    h2 = [("supplier", "Поставщик", 14), ("collection", "Коллекция", 22), ("count", "Цветов", 8),
          ("composition", "Состав", 26), ("width_cm", "Ширина, см", 10), ("density", "Плотность", 18),
          ("martindale_text", "Истирание", 20), ("country", "Страна", 10), ("price", "Цена, ₽/п.м.", 16),
          ("url", "Ссылка", 50)]
    ws2.append([h for _, h, _ in h2])
    for i, (_, _, w) in enumerate(h2, start=1):
        ws2.column_dimensions[get_column_letter(i)].width = w
    for c in ws2[1]:
        c.font, c.fill, c.alignment = head_font, head_fill, wrap
    for n, c in enumerate(cols, start=2):
        ws2.append([c.get(k) for k, _, _ in h2])
        ws2.cell(row=n, column=len(h2)).hyperlink = c["url"]
        ws2.cell(row=n, column=len(h2)).style = "Hyperlink"
    ws2.freeze_panes = "C2"
    ws2.auto_filter.ref = f"A1:{get_column_letter(len(h2))}{len(cols) + 1}"

    # --- Лист 3: сводка
    ws3 = wb.create_sheet("Сводка")
    ws3.append(["Поставщик", "Коллекций", "Цветов", "С фото", "Источник"])
    for c in ws3[1]:
        c.font, c.fill = head_font, head_fill
    by = defaultdict(list)
    for r in rows:
        by[r["supplier"]].append(r)
    for sup, items in by.items():
        ws3.append([sup, len({i["collection"] for i in items}), len(items),
                    sum(1 for i in items if i.get("photo_file")), items[0]["source"]])
    ws3.append(["Итого", len(cols), len(rows), sum(1 for r in rows if r.get("photo_file")), ""])
    for col, w in zip("ABCDE", (16, 12, 10, 10, 70)):
        ws3.column_dimensions[col].width = w
    wb.move_sheet("Сводка", offset=-2)
    wb.active = 0
    wb.save(os.path.join(DATA_DIR, "velour.xlsx"))


def write_gallery(rows):
    by = OrderedDict()
    for r in rows:
        by.setdefault(r["supplier"], OrderedDict()).setdefault(r["collection"], []).append(r)
    e = html.escape
    parts = ["""<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Велюр — галерея</title>
<style>
body{font-family:system-ui,sans-serif;margin:0 16px 40px;background:#faf9f7;color:#222}
h1{margin:20px 0 4px}h2{margin:32px 0 8px;border-bottom:2px solid #4b3b6b;padding-bottom:4px}
h3{margin:18px 0 6px;font-size:16px}h3 small{color:#777;font-weight:normal}
nav a{margin-right:14px}
.g{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:10px}
figure{margin:0;background:#fff;border:1px solid #e3e0da;border-radius:6px;overflow:hidden}
figure img{width:100%;aspect-ratio:1;object-fit:cover;display:block;background:#eee}
figcaption{font-size:12px;padding:4px 6px;line-height:1.3}
figcaption a{color:inherit}
</style></head><body><h1>Велюр: Союз-М, Артекс, Аметист, Вип Текстиль</h1><nav>"""]
    for sup, cols in by.items():
        parts.append(f'<a href="#{e(sup)}">{e(sup)} ({sum(len(v) for v in cols.values())})</a>')
    parts.append("</nav>")
    for sup, cols in by.items():
        parts.append(f'<h2 id="{e(sup)}">{e(sup)}</h2>')
        for col, items in cols.items():
            i0 = items[0]
            spec = ", ".join(filter(None, [i0.get("composition"), i0.get("density"),
                                           i0.get("martindale_text"),
                                           f"{i0['width_cm']} см" if i0.get("width_cm") else None]))
            parts.append(f"<h3>{e(col or '')} <small>{len(items)} цв. · {e(spec)}</small></h3><div class=g>")
            for r in items:
                src = e(r["photo_file"]) if r.get("photo_file") else ""
                price = f" · {r['price_rub']} ₽" if r.get("price_rub") else ""
                parts.append(f'<figure><a href="{src}" target="_blank"><img loading="lazy" src="{src}" alt=""></a>'
                             f'<figcaption><a href="{e(r["url"])}" target="_blank">{e(r["article"] or "")}</a>'
                             f'{"<br>" + e(r["color"]) if r.get("color") and r["color"] not in (r["article"] or "") else ""}'
                             f"{price}</figcaption></figure>")
            parts.append("</div>")
    parts.append("</body></html>")
    open(os.path.join(DATA_DIR, "gallery.html"), "w", encoding="utf-8").write("\n".join(parts))


def main():
    rows = load()
    normalize_photos(rows)
    cols = collections(rows)
    write_csv_json(rows)
    write_xlsx(rows, cols)
    write_gallery(rows)
    by = defaultdict(int)
    for r in rows:
        by[r["supplier"]] += 1
    print("позиций:", dict(by), "всего", len(rows), "коллекций", len(cols))


if __name__ == "__main__":
    main()
