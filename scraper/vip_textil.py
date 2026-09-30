"""Вип Текстиль (viptextil.ru): раздел «Велюр», все цвета коллекций."""
import json
import re
from datetime import date
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from common import clean, get_text, num, pmap, save_photo, slug, write_raw

BASE = "https://viptextil.ru"
SUPPLIER = "Вип Текстиль"
CATEGORY = BASE + "/catalog/mebelnie-tkani/velyur/"
RESTS = BASE + "/catalog/special/rests-display/"  # «Актуальные остатки»


def rests():
    """{название цвета в нижнем регистре: (статус наличия, [разделы])}."""
    s = BeautifulSoup(get_text(RESTS), "lxml")
    out = {}
    for li in s.select('li.rests-item[data-is-product="1"]'):
        st = li.select_one(".rests-status")
        cats = [clean(c.select_one(".rests-item-name").contents[0]) for c in li.find_parents("li", class_="is-category")]
        out[clean(li["data-name"]).lower()] = (clean(st.get_text()) if st else None, cats)
    return out


def collection_urls():
    s = BeautifulSoup(get_text(CATEGORY), "lxml")
    urls = []
    for a in s.select('a[href^="/catalog/mebelnie-tkani/velyur/"]'):
        href = urljoin(BASE, a["href"].split("?")[0])
        if href != CATEGORY and href.count("/") == CATEGORY.count("/") + 1 and href not in urls:
            urls.append(href)
    return urls


def img_url(path):
    # "/images/editor/catalog/../items/x.jpg" -> "https://viptextil.ru/images/editor/items/x.jpg"
    return urljoin(BASE + "/images/editor/catalog/", path.replace("/images/editor/catalog/", ""))


def parse_collection(url, rests_map):
    h = get_text(url)
    s = BeautifulSoup(h, "lxml")
    specs = {}
    for row in s.select("#fabric-properties .row"):
        k, v = row.select_one(".product-tech-name"), row.select_one(".product-tech-value")
        if k and v:
            specs[clean(k.get_text())] = clean(v.get_text(" "))
    m = re.search(r"window\.productData\s*=\s*(\{.*?\});\s*\n", h, re.S)
    data = json.loads(m.group(1))
    base = data["base"]
    stock = s.select_one(".bg-green")
    stock_more = s.select_one(".this-block-to-delete.fs-6")
    stock_txt = " ".join(filter(None, [clean(stock.get_text()) if stock else None,
                                        clean(stock_more.get_text()) if stock_more else None])) or None
    collection = clean(base["name"])
    links = {d["data-config-id"]: urljoin(BASE, d.img["data-configuration-link"])
             for d in s.select(".material-color-selector [data-config-id]")
             if d.img and d.img.get("data-configuration-link")}
    rows = []
    for c in (data.get("configurations") or {}).values():
        imgs = c.get("images") or []
        # первая картинка конфигурации — фото именно этого цвета
        photo = img_url(imgs[0]["src"]) if imgs else None
        price, old = num(c.get("priceWithDiscount")), num(c.get("originalPrice"))
        rest_status, rest_cats = rests_map.get((clean(c.get("name")) or "").lower(), (None, []))
        rows.append({
            "supplier": SUPPLIER,
            "collection": collection,
            "article": clean(c.get("name")),
            "sku": clean(c.get("nomenclature")),
            "color": clean(c.get("color")),
            "fabric_type": specs.get("Тип материала"),
            "purpose": specs.get("Назначение"),
            "composition": specs.get("Состав"),
            "width_cm": num(specs.get("Ширина полотна")),
            "density": specs.get("Плотность"),
            "martindale_text": specs.get("Тест Мартиндейла"),
            "martindale": num(specs.get("Тест Мартиндейла")),
            "lightfastness": specs.get("Цветоустойчивость к свету"),
            "country": None,
            "price_rub": price,
            "old_price_rub": old if old and price and old != price else None,
            "price_note": "Цена за 1 п.м. (сайт)",
            "stock": rest_status or stock_txt,
            "in_stock": rest_status == "есть в наличии",
            "status": "Распродажа" if "РАСПРОДАЖА" in rest_cats else None,
            "url": links.get(c.get("id"), url),
            "photo_url": photo,
            "source": "viptextil.ru (официальный сайт)",
            "collected": date.today().isoformat(),
        })
    print(f"  {collection}: цветов {len(rows)}")
    return rows


def main():
    urls = collection_urls()
    print(f"{SUPPLIER}: коллекций велюра {len(urls)}")
    rests_map = rests()
    rows = [r for u in urls for r in parse_collection(u, rests_map)]

    def photo(r):
        r["photo_file"] = save_photo(
            r["photo_url"], f"{slug(SUPPLIER)}/{slug(r['collection'])}/{slug(r['article'])}"
        ) if r["photo_url"] else None
        return r

    for r in rows:
        r["photo_file"] = None
    # фото качаем только для цветов в наличии
    pmap(photo, [r for r in rows if r["in_stock"]], workers=3)
    write_raw("vip_textil", rows)
    print(f"{SUPPLIER}: итого {len(rows)} позиций")


if __name__ == "__main__":
    main()
