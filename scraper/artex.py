"""Артекс (artextkani.ru): категория «Велюр» через WooCommerce Store API."""
import html
from datetime import date

from common import clean, get, num, pmap, save_photo, slug, write_raw

BASE = "https://artextkani.ru"
SUPPLIER = "Артекс"
API = BASE + "/wp-json/wc/store/v1"
VELOUR_SLUG = "velyur"


def all_categories():
    cats, page = [], 1
    while True:
        r = get(f"{API}/products/categories?per_page=100&page={page}")
        r.raise_for_status()
        batch = r.json()
        cats += batch
        if len(batch) < 100:
            return cats
        page += 1


def products(cat_id):
    out, page = [], 1
    while True:
        r = get(f"{API}/products?category={cat_id}&per_page=100&page={page}")
        r.raise_for_status()
        out += r.json()
        if page >= int(r.headers.get("x-wp-totalpages", 1)):
            return out
        page += 1


def attr(p, name):
    for a in p.get("attributes", []):
        if a["name"] == name:
            return clean(html.unescape(", ".join(t["name"] for t in a["terms"])))
    return None


def main():
    cats = all_categories()
    velour = next(c for c in cats if c["slug"] == VELOUR_SLUG)
    collections = {c["id"]: clean(c["name"]) for c in cats if c["parent"] == velour["id"]}
    items = products(velour["id"])
    print(f"{SUPPLIER}: коллекций {len(collections)}, товаров в «Велюр» {len(items)}")
    rows = []
    for p in items:
        col = next((collections[c["id"]] for c in p["categories"] if c["id"] in collections), None)
        pr = p["prices"]
        price, regular = num(pr.get("price")), num(pr.get("regular_price"))
        rows.append({
            "supplier": SUPPLIER,
            "collection": col,
            "article": clean(p.get("sku")) or clean(html.unescape(p["name"])),
            "name_full": clean(html.unescape(p["name"])),
            "color": attr(p, "Цвет"),
            "fabric_type": attr(p, "Тип ткани"),
            "composition": attr(p, "Состав"),
            "width_cm": num(attr(p, "Ширина")),
            "density": attr(p, "Плотность"),
            "martindale_text": attr(p, "Стойкость к истиранию"),
            "martindale": num(attr(p, "Стойкость к истиранию")),
            "pilling": attr(p, "Пиллинг"),
            "country": attr(p, "Страна производитель"),
            "price_rub": price,
            "old_price_rub": regular if regular and price and regular != price else None,
            "price_note": "Розничная цена за 1 п.м. (сайт)",
            "stock": clean(p.get("stock_availability", {}).get("text")),
            "url": p["permalink"],
            "photo_url": p["images"][0]["src"] if p.get("images") else None,
            "extra_photos": [i["src"] for i in p.get("images", [])[1:]],
            "source": "artextkani.ru (официальный сайт)",
            "collected": date.today().isoformat(),
        })

    def photo(r):
        r["photo_file"] = save_photo(
            r["photo_url"], f"{slug(SUPPLIER)}/{slug(r['collection'] or 'Прочее')}/{slug(r['article'])}"
        ) if r["photo_url"] else None
        return r

    rows = pmap(photo, rows, workers=6)
    write_raw("artex", rows)
    print(f"{SUPPLIER}: итого {len(rows)} позиций")


if __name__ == "__main__":
    main()
