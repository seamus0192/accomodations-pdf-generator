#!/usr/bin/env python3
"""
scrape_to_pdf.py

Usage:
    python scrape_to_pdf.py links.txt

Produces:
    listings.pdf
"""

import os
import sys
import time
import requests
from io import BytesIO
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from fpdf import FPDF
from PIL import Image

# --- CONFIGURATION ---
# Number of images per listing
MAX_IMAGES = 3
# Directory to cache downloaded images
IMG_DIR = "images"
# Output PDF
OUTPUT_PDF = "listings.pdf"
# ---------------------

def init_webdriver():
    chrome_opts = Options()
    chrome_opts.add_argument("--headless")
    chrome_opts.add_argument("--disable-gpu")
    chrome_opts.add_argument("--no-sandbox")
    driver = webdriver.Chrome(options=chrome_opts)
    return driver

def fetch_page(driver, url):
    driver.get(url)
    # wait for dynamic content
    time.sleep(3)
    return driver.page_source

def parse_airbnb(html):
    """Returns dict with keys: images, location, address, price, rating"""
    soup = BeautifulSoup(html, "html.parser")
    data = {}
    # Images: look for <meta property="og:image" content="...">
    imgs = [m["content"] for m in soup.select('meta[property="og:image"]') if m.get("content")]
    data["images"] = imgs[:MAX_IMAGES]
    # Location: meta tag, or breadcrumb
    loc = soup.select_one('meta[property="airbedandbreakfast:location"]')
    if loc and loc.get("content"):
        data["location"] = loc["content"]
    else:
        h1 = soup.select_one("h1")
        data["location"] = h1.get_text(strip=True) if h1 else "—"
    # Address: look for aria-label or structured data
    address = soup.select_one('[data-testid="listing-title-subtitle"]')
    data["address"] = address.get_text(strip=True) if address else "—"
    # Price: look for span with price
    price = soup.select_one('[data-testid="price"]')
    data["price"] = price.get_text(strip=True) if price else "—"
    # Rating: look for span aria-label containing rating
    rating = soup.select_one('[aria-label*="Rating"]')
    data["rating"] = rating.get_text(strip=True) if rating else "—"
    return data

def parse_booking(html):
    """Returns dict with keys: images, location, address, price, rating"""
    soup = BeautifulSoup(html, "html.parser")
    data = {}
    # Images: gallery bullets
    imgs = []
    for img in soup.select(".bh-photo-grid-thumb img"):
        src = img.get("data-highres") or img.get("src")
        if src:
            imgs.append(src)
    data["images"] = imgs[:MAX_IMAGES]
    # Location: breadcrumb
    loc = soup.select_one(".hp_address_subtitle")
    data["location"] = loc.get_text(strip=True) if loc else "—"
    # Address: sometimes same as location on Booking
    data["address"] = data["location"]
    # Price: look for price summary
    price = soup.select_one(".bui-price-display__value")
    data["price"] = price.get_text(strip=True) if price else "—"
    # Rating: review score badge
    rating = soup.select_one(".bui-review-score__badge")
    data["rating"] = rating.get_text(strip=True) if rating else "—"
    return data

def download_image(url, dest_folder, idx, listing_idx):
    os.makedirs(dest_folder, exist_ok=True)
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        img = Image.open(BytesIO(resp.content))
        path = os.path.join(dest_folder, f"listing{listing_idx}_img{idx}.jpg")
        img.save(path, format="JPEG")
        return path
    except Exception as e:
        print(f"  [!] Failed to download {url}: {e}")
        return None

def make_pdf(listings):
    pdf = FPDF(unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    for i, l in enumerate(listings, 1):
        pdf.add_page()
        pdf.set_font("Arial", "B", 16)
        pdf.cell(0, 10, f"Listing {i}", ln=True)

        pdf.set_font("Arial", "", 12)
        pdf.cell(0, 8, f"Location: {l['location']}", ln=True)
        pdf.cell(0, 8, f"Address:  {l['address']}", ln=True)
        pdf.cell(0, 8, f"Price:    {l['price']}", ln=True)
        pdf.cell(0, 8, f"Rating:   {l['rating']}", ln=True)
        pdf.ln(5)

        # images in a row
        x_start = pdf.get_x()
        y_start = pdf.get_y()
        img_w = (pdf.w - 2*pdf.l_margin - 10) / MAX_IMAGES
        img_h = img_w * 0.75
        for img_path in l["downloaded_images"]:
            if not img_path:
                continue
            pdf.image(img_path, x=pdf.get_x(), y=pdf.get_y(), w=img_w, h=img_h)
            pdf.set_x(pdf.get_x() + img_w + 5)
        # reset position
        pdf.ln(img_h + 5)

    pdf.output(OUTPUT_PDF)
    print(f"[+] PDF generated: {OUTPUT_PDF}")

def main(links_file):
    with open(links_file) as f:
        urls = [l.strip() for l in f if l.strip()]

    driver = init_webdriver()
    listings = []
    for idx, url in enumerate(urls, 1):
        print(f"[{idx}/{len(urls)}] Scraping {url}")
        html = fetch_page(driver, url)
        domain = urlparse(url).netloc.lower()
        if "airbnb.com" in domain:
            info = parse_airbnb(html)
        elif "booking.com" in domain:
            info = parse_booking(html)
        else:
            print(f"  [!] Unsupported domain: {domain}")
            continue

        # download images
        dl_imgs = []
        for i, img_url in enumerate(info["images"], 1):
            path = download_image(img_url, IMG_DIR, i, idx)
            if path:
                dl_imgs.append(path)
        info["downloaded_images"] = dl_imgs
        listings.append(info)

    driver.quit()
    make_pdf(listings)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scrape_to_pdf.py links.txt")
        sys.exit(1)
    main(sys.argv[1])

