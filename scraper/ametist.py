"""Аметист: официальный ametist-store.ru закрыт капчей для зарубежных IP.

Источник — каталог белорусского дилера «Первый портал мебельных тканей»
(мебельныеткани.бел): страницы раздела «Велюр» с «Фабрика тканей: Ametist».
Список страниц берётся из sitemap.xml (robots.txt запрещает URL с «?»).
"""
import re
from datetime import date
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from common import clean, get_text, num, pmap, save_photo, slug, write_raw

BASE = "https://xn--80ablbatmgfod1dzgm.xn--90ais/"
SUPPLIER = "Аметист"
FACTORY = "Ametist"


def velour_pages():
    xml = get_text(BASE + "sitemap.xml")
    return sorted(set(re.findall(r"<loc>(https://[^<]*/katalog/velyur/[^<]+\.html)</loc>", xml)))


def parse(url):
    s = BeautifulSoup(get_text(url), "lxml")
    brand = s.select_one('[itemprop="brand"] [itemprop="name"]')
    if not brand or clean(brand.get("content")) != FACTORY:
        return []
    specs = {}
    for tr in s.select("tr"):
        tds = tr.find_all("td")
        if len(tds) == 2:
            specs[clean(tds[0].get_text()).rstrip(":").strip()] = clean(tds[1].get_text(" "))
    title = clean(s.find("h1").get_text())
    collection = specs.get("Название коллекции") or re.sub(r"^Велюр\s+|\s*\(.*\)$", "", title)
    byn = s.select_one('[itemprop="lowPrice"]')
    byn = num(byn.get("content")) if byn else None
    rows = []
    for item in s.select("#dynamic .item"):
        a = item.find("a", href=True)
        img = item.find("img")
        code = clean(img.get("title")) if img else None
        rows.append({
            "supplier": SUPPLIER,
            "collection": collection,
            "article": f"{collection} {code}",
            "color": code,
            "name_full": title,
            "fabric_type": "Велюр",
            "composition": specs.get("Состав"),
            "width_cm": num(specs.get("Ширина")),
            "density": specs.get("Плотность"),
            "martindale_text": specs.get("Устойчивость к истиранию"),
            "martindale": num(specs.get("Устойчивость к истиранию")),
            "country": None,
            "price_rub": None,
            "old_price_rub": None,
            "price_note": f"{byn} BYN/п.м. у дилера в РБ" if byn else None,
            "stock": "не проверено: сайт Аметиста недоступен",
            "in_stock": None,
            "status": None,
            "url": url,
            "photo_url": urljoin(BASE, a["href"]) if a else None,
            "source": "мебельныеткани.бел (дилер в РБ; официальный ametist-store.ru закрыт капчей)",
            "collected": date.today().isoformat(),
        })
    print(f"  {collection}: цветов {len(rows)}")
    return rows


def main():
    pages = velour_pages()
    print(f"{SUPPLIER}: страниц велюра у дилера {len(pages)}, отбираю фабрику {FACTORY}")
    rows = [r for batch in pmap(parse, pages, workers=4) for r in batch]

    def photo(r):
        r["photo_file"] = save_photo(
            r["photo_url"], f"{slug(SUPPLIER)}/{slug(r['collection'])}/{slug(r['article'])}"
        ) if r["photo_url"] else None
        return r

    rows = pmap(photo, rows, workers=4)
    write_raw("ametist", rows)
    print(f"{SUPPLIER}: итого {len(rows)} позиций")


if __name__ == "__main__":
    main()
