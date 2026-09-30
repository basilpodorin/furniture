"""Общие утилиты для сборщиков каталогов велюра."""
import io
import json
import os
import re
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor

import requests
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "velour")
PHOTO_DIR = os.path.join(DATA_DIR, "photos")
RAW_DIR = os.path.join(DATA_DIR, "raw")

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# Максимальная длинная сторона сохраняемого фото, px.
PHOTO_MAX_SIDE = 1000
PHOTO_QUALITY = 82

_session = requests.Session()
_session.headers.update({"User-Agent": UA, "Accept-Language": "ru-RU,ru;q=0.9"})


def get(url, *, tries=5, timeout=60, **kw):
    """GET с повторами при сетевых сбоях и 5xx."""
    last = None
    for attempt in range(tries):
        try:
            r = _session.get(url, timeout=timeout, **kw)
            if r.status_code >= 500:
                raise requests.HTTPError(f"{r.status_code} for {url}")
            return r
        except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as e:
            last = e
            time.sleep(2 ** attempt)
    raise last


def get_text(url, **kw):
    r = get(url, **kw)
    r.raise_for_status()
    r.encoding = r.encoding or "utf-8"
    return r.text


def pmap(fn, items, workers=4):
    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(fn, items))


def slug(s):
    """Безопасное имя файла/папки (латиница, цифры, кириллица, - и _)."""
    s = unicodedata.normalize("NFKC", str(s)).strip()
    s = re.sub(r"[^\w\- ]+", "", s, flags=re.U)
    s = re.sub(r"\s+", "_", s)
    return s.strip("_") or "item"


def clean(s):
    if s is None:
        return None
    s = unicodedata.normalize("NFKC", str(s)).replace("\xa0", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s or None


def num(s):
    """Первое число из строки: '251,5 г/м2' -> 251.5, '60 000 циклов' -> 60000."""
    if s is None:
        return None
    m = re.search(r"\d[\d\s]*(?:[.,]\d+)?", str(s).replace("\xa0", " "))
    if not m:
        return None
    v = m.group(0).replace(" ", "").replace(",", ".")
    f = float(v)
    return int(f) if f.is_integer() else f


def save_photo(url, rel_path):
    """Скачивает фото, приводит к JPEG c длинной стороной <= PHOTO_MAX_SIDE.

    rel_path — путь относительно velour/photos без расширения.
    Возвращает путь относительно папки velour/ или None при ошибке.
    """
    out = os.path.join(PHOTO_DIR, rel_path + ".jpg")
    rel = os.path.relpath(out, DATA_DIR)
    if os.path.exists(out) and os.path.getsize(out) > 0:
        return rel
    try:
        r = get(url)
        if r.status_code != 200 or not r.headers.get("content-type", "").startswith("image"):
            return None
        im = Image.open(io.BytesIO(r.content))
        im = im.convert("RGB")
        im.thumbnail((PHOTO_MAX_SIDE, PHOTO_MAX_SIDE), Image.LANCZOS)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        im.save(out, "JPEG", quality=PHOTO_QUALITY, optimize=True, progressive=True)
        return rel
    except Exception as e:  # noqa: BLE001
        print(f"  ! фото не скачано {url}: {e}")
        return None


def write_raw(name, rows):
    os.makedirs(RAW_DIR, exist_ok=True)
    with open(os.path.join(RAW_DIR, name + ".json"), "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
