#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批次查核 StockBox 2026 贈品照片，僅補足撿股讚沒有實照的股票。
這支程式應在可連線的 CI 環境執行；不在瀏覽器跨網域爬取資料。"""
import csv
import json
import re
import time
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
CSV = ROOT / "stockgift_2026.csv"
OUT = ROOT / "stockbox_photos.json"
BASE = "https://www.stockbox.com.tw"
VALID_IMAGE_HOSTS = {"s3.ap-northeast-1.amazonaws.com", "img.stockbox.com.tw"}
HEADERS = {"User-Agent": "smallstockgift-2026-photo-checker/1.0 (+https://github.com/iot-superman/smallstockgift-2026)"}


def normalize(value: str) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).lower()
    return re.sub(r"[\s\-_—–·、,，.。()\[\]（）]", "", text)


def same_gift(a: str, b: str) -> bool:
    # 以贈品名稱為關鍵，不可僅因股號相同就採用不同年度的照片。
    a, b = normalize(a), normalize(b)
    if not a or not b:
        return False
    return a == b or (min(len(a), len(b)) >= 8 and SequenceMatcher(None, a, b).ratio() >= 0.89)


def image_address(img, page_url: str) -> str:
    value = (img.get("src") or img.get("data-src") or img.get("data-original") or "").strip()
    if not value and img.get("srcset"):
        value = img["srcset"].split(",")[0].strip().split(" ")[0]
    url = urljoin(page_url, value)
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in VALID_IMAGE_HOSTS:
        return ""
    if not re.search(r"\.(?:jpe?g|png|webp)(?:\?|$)", parsed.path, re.I):
        return ""
    return url


def find_verified_photo(session, stock_code: str, gift: str):
    page_url = f"{BASE}/stocks/{stock_code}"
    try:
        response = session.get(page_url, timeout=16)
        response.raise_for_status()
    except requests.RequestException:
        return None

    soup = BeautifulSoup(response.text, "html.parser")
    page_header = soup.find("h1")
    if not page_header or stock_code not in page_header.get_text(" ", strip=True) or "2026" not in page_header.get_text(" ", strip=True):
        return None

    # 限定目前這年度主贈品標題，排除下面的「歷年紀念品」圖片。
    gift_headings = []
    for node in soup.find_all(["h2", "h3"]):
        content = node.get_text(" ", strip=True)
        if same_gift(content, gift):
            gift_headings.append(content)
    if not gift_headings:
        return None

    current_gift = gift_headings[0]
    for img in soup.find_all("img"):
        alt = img.get("alt", "").strip()
        # 必須為本年度主贈品照片，不採用最新領取、歷年、廣告或 Logo。
        if not same_gift(alt, current_gift):
            continue
        photo_url = image_address(img, page_url)
        if photo_url:
            return {"gift": gift, "url": photo_url, "source": page_url}
    return None


def main():
    with CSV.open("r", encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    with OUT.open("r", encoding="utf-8") as file:
        existing = json.load(file)
    photos = existing.get("photos", {})
    candidates = [
        r for r in rows
        if r.get("圖") != "有圖"
        and not r.get("2026贈品圖片網址_有圖示")
        and re.fullmatch(r"\d{4,6}", r.get("代號", ""))
    ]

    # 尊重來源站 robots.txt；若明確不允許，則不爬取。
    robot = RobotFileParser()
    try:
        robot.set_url(BASE + "/robots.txt")
        robot.read()
        allowed = robot.can_fetch(HEADERS["User-Agent"], BASE + "/stocks/2880")
    except Exception:
        allowed = False
    if not allowed:
        print("StockBox robots.txt 無法確認允許抓取，本次停止。")
        return

    with requests.Session() as session:
        session.headers.update(HEADERS)
        added = 0
        for index, row in enumerate(candidates, 1):
            code, gift = row["代號"], row["紀念品"]
            if code in photos and same_gift(photos[code].get("gift", ""), gift):
                continue
            photo = find_verified_photo(session, code, gift)
            if photo:
                photos[code] = photo
                added += 1
                print(f"[{index}/{len(candidates)}] verified: {code} {gift}")
            # 將連線頻率降至約每秒一筆；失敗與缺圖均不寫入假資料。
            time.sleep(1.0)
    result = {
        "version": "2026-11-14",
        "description": "StockBox 2026 verified secondary gift photos; stock code and gift must match",
        "photos": dict(sorted(photos.items()))
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"CSV rows={len(rows)}, missing={len(candidates)}, new verified photos={added}, total secondary photos={len(photos)}")


if __name__ == "__main__":
    main()
