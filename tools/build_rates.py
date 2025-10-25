# -*- coding: utf-8 -*-
"""
Daily builder for Uzbek banks buy/sell exchange rates.
Usage:
  python tools/build_rates.py                # собрать все банки
  python tools/build_rates.py hamkorbank     # собрать только один
  python tools/build_rates.py --debug        # сохранять HTML в tools/_debug
Outputs: public/rates.json
"""

from __future__ import annotations
import json, re, time, sys, os, random
from dataclasses import dataclass, asdict
from datetime import date
from typing import List, Dict, Any
import requests
from requests.adapters import HTTPAdapter, Retry
from bs4 import BeautifulSoup

TODAY = date.today().isoformat()
DEBUG = ("--debug" in sys.argv)
ONLY = next((arg for arg in sys.argv[1:] if arg.isalpha() and arg != "--debug"), None)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Cache-Control": "no-cache",
    "Referer": "https://www.google.com/",
}

CCYS = {"USD","EUR","RUB","GBP","JPY","CHF","TRY","CNY","KZT"}

def _num(x: str):
    if not x: return None
    x = x.strip().replace("\xa0"," ").replace(" ", "").replace(",", ".")
    m = re.search(r"^-?\d+(\.\d+)?$", x)
    if not m:
        m2 = re.search(r"(\d[\d\s]*[.,]\d+|\d+)", x)
        if not m2: return None
        x = m2.group(1).replace(" ", "").replace(",", ".")
    try:
        return float(x)
    except:
        return None

def _sess():
    s = requests.Session()
    retries = Retry(
        total=3, backoff_factor=0.8,
        status_forcelist=(403, 429, 500, 502, 503, 504),
        allowed_methods=["GET", "HEAD"]
    )
    s.mount("https://", HTTPAdapter(max_retries=retries))
    s.mount("http://", HTTPAdapter(max_retries=retries))
    return s

def fetch_html(url: str, timeout=25) -> BeautifulSoup:
    sess = _sess()
    hdrs = dict(HEADERS)
    # небольшая рандомизация UA — иногда помогает против 403
    ua_tail = str(random.randint(1000,9999))
    hdrs["User-Agent"] = hdrs["User-Agent"].replace("120.0.0.0", f"12{ua_tail}.0.0")
    r = sess.get(url, timeout=timeout, headers=hdrs, allow_redirects=True)
    r.raise_for_status()
    return BeautifulSoup(r.text, "lxml"), r.text

def save_debug(bank: str, html: str):
    if not DEBUG: return
    dbg_dir = os.path.join(os.path.dirname(__file__), "_debug")
    os.makedirs(dbg_dir, exist_ok=True)
    path = os.path.join(dbg_dir, f"{bank}.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[debug] saved: {path}")

@dataclass
class Rate:
    ccy: str
    buy: float | None
    sell: float | None

@dataclass
class BankRates:
    bank: str
    date: str
    rates: List[Rate]
    source_url: str

# ---------- Adapters ----------

def hamkorbank() -> BankRates:
    urls = [
        "https://hamkorbank.uz/ru/exchange-rate/",
        "https://hamkorbank.uz/en/exchange-rate/",
    ]
    for url in urls:
        try:
            soup, html = fetch_html(url)
            save_debug("hamkorbank", html)
            rates: List[Rate] = []
            rows_scanned = 0
            for table in soup.find_all("table"):
                for tr in table.find_all("tr"):
                    cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td","th"])]
                    if not cells: continue
                    rows_scanned += 1
                    ccy = next((c.upper() for c in cells if c.upper() in CCYS), None)
                    if not ccy: continue
                    nums = [_num(c) for c in cells]
                    nums = [n for n in nums if n is not None]
                    if len(nums) >= 2:
                        rates.append(Rate(ccy, nums[-2], nums[-1]))
            print(f"[hamkorbank] scanned rows={rows_scanned}, found={len(rates)}")
            if rates:
                dedup = {r.ccy: r for r in rates}
                major = [dedup[c] for c in ("USD","EUR","RUB") if c in dedup]
                if major:
                    return BankRates("Hamkorbank", TODAY, major, url)
        except Exception as e:
            print("[hamkorbank] err:", e)
            continue
    return BankRates("Hamkorbank", TODAY, [], urls[0])

def kapitalbank() -> BankRates:
    urls = [
        "https://www.kapitalbank.uz/ru/services/exchange-rates-new/",
        "https://www.kapitalbank.uz/ru/services/exchange-rates/",
        "https://www.kapitalbank.uz/en/services/exchange-rates-new/",
        "https://www.kapitalbank.uz/services/exchange-rates-new/",
    ]
    last = None
    for url in urls:
        try:
            soup, html = fetch_html(url)
            save_debug("kapitalbank", html)
            bag: Dict[str, List[Rate]] = {}
            rows = 0
            for tr in soup.find_all("tr"):
                cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td","th"])]
                if not cells: continue
                rows += 1
                ccy = next((c.upper() for c in cells if c.upper() in {"USD","EUR","RUB"}), None)
                if not ccy: continue
                nums = [_num(x) for x in cells]
                nums = [n for n in nums if n is not None]
                if len(nums) >= 2:
                    bag.setdefault(ccy, []).append(Rate(ccy, nums[0], nums[1]))
            print(f"[kapitalbank] rows={rows}, USD/EUR/RUB groups={ {k:len(v) for k,v in bag.items()} }")
            out: List[Rate] = []
            for ccy, arr in bag.items():
                b = sum(r.buy for r in arr if r.buy is not None)/len(arr)
                s = sum(r.sell for r in arr if r.sell is not None)/len(arr)
                out.append(Rate(ccy, round(b,2), round(s,2)))
            if out:
                return BankRates("Kapitalbank", TODAY, sorted(out, key=lambda r: r.ccy), url)
        except Exception as e:
            last = e
            print("[kapitalbank] err:", e)
            continue
    if last: raise last
    return BankRates("Kapitalbank", TODAY, [], urls[0])

def agrobank() -> BankRates:
    urls = [
        "https://agrobank.uz/ru/person",
        "https://agrobank.uz/ru/individuals",
        "https://agrobank.uz/en/person",
    ]
    for url in urls:
        try:
            soup, html = fetch_html(url)
            save_debug("agrobank", html)
            rates: List[Rate] = []
            rows = 0
            for tr in soup.find_all("tr"):
                cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td","th"])]
                if not cells: continue
                rows += 1
                ccy = next((c.upper() for c in cells if c.upper() in {"USD","EUR","RUB"}), None)
                if not ccy: continue
                nums = [_num(x) for x in cells]
                nums = [n for n in nums if n is not None]
                if len(nums) >= 2:
                    rates.append(Rate(ccy, nums[0], nums[1]))
            print(f"[agrobank] rows={rows}, found={len(rates)}")
            if rates:
                dedup = {r.ccy: r for r in rates}
                major = [dedup[c] for c in ("USD","EUR","RUB") if c in dedup]
                if major:
                    return BankRates("Agrobank", TODAY, major, url)
        except Exception as e:
            print("[agrobank] err:", e)
            continue
    return BankRates("Agrobank", TODAY, [], urls[0])

def ipakyulibank() -> BankRates:
    urls = [
        "https://ipakyulibank.uz/ru",
        "https://ipakyulibank.uz/ru/exchange-rates",
        "https://ipakyulibank.uz/ru/individuals/exchange-rates",
        "https://ipakyulibank.uz/en",
    ]
    for url in urls:
        try:
            soup, html = fetch_html(url)
            save_debug("ipakyulibank", html)
            rates: List[Rate] = []
            rows = 0
            for tr in soup.find_all("tr"):
                cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td","th"])]
                if not cells: continue
                rows += 1
                ccy = next((c.upper() for c in cells if c.upper() in {"USD","EUR","RUB"}), None)
                if not ccy: continue
                nums = [_num(x) for x in cells]
                nums = [n for n in nums if n is not None]
                if len(nums) >= 2:
                    rates.append(Rate(ccy, nums[0], nums[1]))
            print(f"[ipakyulibank] rows={rows}, found={len(rates)}")
            if rates:
                dedup = {r.ccy: r for r in rates}
                major = [dedup[c] for c in ("USD","EUR","RUB") if c in dedup]
                if major:
                    return BankRates("Ipak Yuli Bank", TODAY, major, url)
        except Exception as e:
            print("[ipakyulibank] err:", e)
            continue
    return BankRates("Ipak Yuli Bank", TODAY, [], urls[0])

def tbc_bank_uz() -> BankRates:
    urls = [
        "https://tbcbank.uz/ru",
        "https://tbcbank.uz/en",
    ]
    for url in urls:
        try:
            soup, html = fetch_html(url)
            save_debug("tbc_bank_uz", html)
            rates: List[Rate] = []
            rows = 0
            for tr in soup.find_all("tr"):
                cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td","th"])]
                if not cells: continue
                rows += 1
                ccy = next((c.upper() for c in cells if c.upper() in {"USD","EUR","RUB"}), None)
                if not ccy: continue
                nums = [_num(x) for x in cells]
                nums = [n for n in nums if n is not None]
                if len(nums) >= 2:
                    rates.append(Rate(ccy, nums[0], nums[1]))
            print(f"[tbc_bank_uz] rows={rows}, found={len(rates)}")
            if rates:
                dedup = {r.ccy: r for r in rates}
                major = [dedup[c] for c in ("USD","EUR","RUB") if c in dedup]
                if major:
                    return BankRates("TBC Bank Uzbekistan", TODAY, major, url)
        except Exception as e:
            print("[tbc_bank_uz] err:", e)
            continue
    return BankRates("TBC Bank Uzbekistan", TODAY, [], urls[0])

ADAPTERS = [
    hamkorbank,
    agrobank,
    kapitalbank,
    ipakyulibank,
    tbc_bank_uz,
]

# ---------- Optional: CBU reference (not buy/sell) ----------
def cbu_reference() -> BankRates | None:
    """Подстраховка, чтобы фронт не пустел. Это НЕ buy/sell, а официальный курс ЦБ на день."""
    try:
        url = f"https://cbu.uz/ru/arkhiv-kursov-valyut/json/all/{TODAY}/"
        sess = _sess()
        r = sess.get(url, timeout=20)
        r.raise_for_status()
        data = r.json()
        d = {x["Ccy"].upper(): float(x["Rate"]) for x in data if x.get("Ccy")}
        wanted = []
        for c in ("USD","EUR","RUB"):
            if c in d:
                wanted.append(Rate(c, d[c], d[c]))
        if wanted:
            return BankRates("CBU (справочно)", TODAY, wanted, url)
    except Exception as e:
        print("[cbu] err:", e)
    return None

# ---------- Main ----------
def main():
    out: List[Dict[str, Any]] = []
    used = [fn for fn in ADAPTERS if (ONLY is None or fn.__name__ == ONLY)]
    for fn in used:
        print(f"==> {fn.__name__}")
        try:
            br: BankRates = fn()
            if br.rates:
                out.append({
                    "bank": br.bank,
                    "date": br.date,
                    "rates": [asdict(r) for r in br.rates],
                    "source_url": br.source_url,
                })
                print(f"[ok] {br.bank}: {len(br.rates)} валют")
            else:
                print(f"[warn] {br.bank}: не нашли курсы")
            time.sleep(1.0)
        except Exception as e:
            print(f"[ERR] {fn.__name__}: {e}")

    if not out:
        ref = cbu_reference()
        if ref:
            out.append({
                "bank": ref.bank,
                "date": ref.date,
                "rates": [asdict(r) for r in ref.rates],
                "source_url": ref.source_url,
            })
            print("[info] добавили справочные курсы ЦБ РУз (не buy/sell) для заполнения таблицы")

    os.makedirs("public", exist_ok=True)
    with open("public/rates.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"Wrote {len(out)} banks to public/rates.json")

if __name__ == "__main__":
    main()
