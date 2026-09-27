import os
import time
import pandas as pd
import requests
from bs4 import BeautifulSoup

# --- 1. CẤU HÌNH ---
# Thay URL danh sách sản phẩm thực tế của bạn vào đây (trang 1)
BASE_URL = "https://example.com/cho-thue-van-phong?page="  # Ví dụ cấu hình pagination dạng ?page=1
TOTAL_PAGES = 37  # Theo ảnh của bạn là 37 trang

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
        " like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

all_products = []

# --- 2. VÒNG LẶP DUYỆT QUA CÁC TRANG ---
for page in range(1, TOTAL_PAGES + 1):
    url = f"{BASE_URL}{page}"
    print(f"🔄 Đang cào dữ liệu trang {page}/{TOTAL_PAGES}: {url}")

    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code != 200:
            print(f"⚠️ Không thể truy cập trang {page} (Code: {response.status_code})")
            continue

        soup = BeautifulSoup(response.text, "html.parser")

        # Tìm tất cả các thẻ bao quanh từng thẻ sản phẩm
        # TODO: Thay '.product-item' bằng class wrapper thật của sản phẩm
        cards = soup.select(".product-item")

        for card in cards:
            # Lấy tên tòa nhà
            # TODO: Thay các Selector bên dưới theo đúng HTML của website
            title_el = card.select_one(".product-title")
            title = title_el.text.strip() if title_el else ""

            # Lấy địa chỉ
            address_el = card.select_one(".product-address")
            address = address_el.text.strip() if address_el else ""

            # Lấy diện tích
            area_el = card.select_one(".product-area")
            area = area_el.text.strip() if area_el else ""

            # Lấy hướng
            direction_el = card.select_one(".product-direction")
            direction = direction_el.text.strip() if direction_el else ""

            # Lấy giá thuê
            price_el = card.select_one(".product-price")
            price = price_el.text.strip() if price_el else ""

            # Lưu vào danh sách
            all_products.append(
                {
                    "Tòa nhà": title,
                    "Địa chỉ": address,
                    "Diện tích thuê": area,
                    "Hướng": direction,
                    "Giá thuê": price,
                }
            )

        # Nghỉ 1-2 giây giữa các trang để tránh bị server chặn (Rate Limit)
        time.sleep(1)

    except Exception as e:
        print(f"❌ Lỗi tại trang {page}: {e}")

# --- 3. XUẤT DỮ LIỆU RA EXCEL ---
if all_products:
    df = pd.DataFrame(all_products)
    output_file = "danh_sach_san_pham.xlsx"
    df.to_excel(output_file, index=False)
    print(
        f"\n✅ Hoàn tất! Đã thu thập {len(all_products)} sản phẩm và xuất ra file '{output_file}'."
    )
else:
    print("\n⚠️ Không thu thập được dữ liệu nào. Vui lòng kiểm tra lại class HTML selector.")