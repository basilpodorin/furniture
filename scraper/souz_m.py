"""Союз-М (souz-m.ru): все цвета с типом ткани «Велюр»."""
import re
from datetime import date
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from common import clean, get_text, num, pmap, save_photo, slug, write_raw

BASE = "https://souz-m.ru"
SUPPLIER = "Союз-М"
VELOUR_TYPE_ID = 14  # filter_TextileType_ID «Велюр»
LISTING = BASE + "/products/?filter_TextileType_ID%5B0%5D={tid}&recNum=12&curPos={pos}"


def collections():
    """[(название коллекции, url первой страницы цвета)] из фильтра «Велюр»."""
    out, pos = [], 0
    while True:
        s = BeautifulSoup(get_text(LISTING.format(tid=VELOUR_TYPE_ID, pos=pos)), "lxml")
        cards = s.select("[data-js-name-col]")
        if not cards:
            break
        for c in cards:
            a = c.select_one('a[href^="/products/"][href$=".html"]')
            if a:
                out.append((clean(c["data-js-name-col"]), urljoin(BASE, a["href"])))
        total = num(s.select_one("[data-js-found] .val").get_text())
        pos += 12
        if pos >= total:
            break
    return out


def color_links(url):
    s = BeautifulSoup(get_text(url), "lxml")
    links = []
    for a in s.select("[data-js-other-tkani-wrapper] a[data-js-change-kartochka]"):
        href = urljoin(BASE, a["href"])
        if href not in links:
            links.append(href)
    return links or [url]


LABELS = {
    "Русское название": "name_ru",
    "Цвет": "color",
    "Состав ткани": "composition",
    "Ширина ткани": "width",
    "Плотность ткани 1м2": "density",
    "Устойчивость к истиранию": "martindale",
    "Тип ткани": "fabric_type",
    "Тип дизайна": "design",
    "Страна-производитель": "country",
}


def parse_color(url, collection):
    h = get_text(url)
    s = BeautifulSoup(h, "lxml")
    specs = {}
    for p in s.select("section.card-details p"):
        strong = p.find("strong")
        if not strong:
            continue
        val = clean(strong.get_text(""))
        strong.extract()
        label = clean(p.get_text("")).rstrip(":").strip()
        if label in LABELS:
            specs[LABELS[label]] = val
    title = clean(s.find("h1").get_text()) if s.find("h1") else None
    prices = [num(e.get_text(" ")) for e in s.select(".card_price .cardFullPrice")]
    prices = [p for p in prices if p]
    price_label = s.select_one(".card_price .cardFullPrice_text")
    price_note = clean(price_label.get_text()).rstrip(":") if price_label else None
    stock_el = s.select_one(".wrap_card_stock")
    stock = clean(stock_el.get_text(" ")) if stock_el else None
    img_el = s.select_one(".js_card__img_full img[data-img]")
    img = None
    if img_el:
        img = urljoin(BASE, re.sub(r"_\d+x\d+(\.\w+)$", r"\1", img_el["data-img"]))
    return {
        "supplier": SUPPLIER,
        "collection": collection,
        "article": title,
        "color": specs.get("color"),
        "name_ru": specs.get("name_ru"),
        "fabric_type": specs.get("fabric_type"),
        "design": specs.get("design"),
        "composition": specs.get("composition"),
        "width_cm": num(specs.get("width")),
        "density_gsm": num(specs.get("density")),
        "martindale": num(specs.get("martindale")),
        "country": specs.get("country"),
        "price_rub": prices[0] if prices else None,
        "old_price_rub": prices[1] if len(prices) > 1 else None,
        "price_note": price_note,
        "stock": stock,
        "url": url,
        "photo_url": img,
        "source": "souz-m.ru (официальный сайт)",
        "collected": date.today().isoformat(),
    }


def photo(r):
    """Оригинал фото; если он битый — версия 570x480 с той же страницы."""
    r["photo_file"] = None
    if r["photo_url"]:
        rel = f"{slug(SUPPLIER)}/{slug(r['collection'])}/{slug(r['article'])}"
        r["photo_file"] = save_photo(r["photo_url"], rel)
        if not r["photo_file"]:
            alt = re.sub(r"(\.\w+)$", r"_570x480\1", r["photo_url"])
            r["photo_file"] = save_photo(alt, rel)
            if r["photo_file"]:
                r["photo_url"] = alt
    return r


def main():
    cols = collections()
    print(f"{SUPPLIER}: коллекций велюра {len(cols)}")
    rows = []
    for name, first in cols:
        links = color_links(first)
        items = pmap(lambda u: parse_color(u, name), links, workers=4)
        velour = [r for r in items if (r["fabric_type"] or "").lower() == "велюр"]
        print(f"  {name}: цветов {len(items)}, велюр {len(velour)}")
        rows.extend(velour)

    rows = pmap(photo, rows, workers=6)
    write_raw("souz_m", rows)
    print(f"{SUPPLIER}: итого {len(rows)} позиций")


if __name__ == "__main__":
    main()
