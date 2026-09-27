import re
import time
import pandas as pd
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://niceoffice.com.vn/danh-muc-vp/van-phong-cho-thue-hcm/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
        " like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


def get_total_pages(soup):
    try:
        pagination = soup.select_one("ul.page-numbers, .pagination")
        if pagination:
            page_numbers = [
                int(a.text.strip())
                for a in pagination.find_all(["a", "span"])
                if a.text.strip().isdigit()
            ]
            if page_numbers:
                return max(page_numbers)
    except Exception:
        pass
    return 37


def clean_text(text):
    if not text:
        return ""
    # Thay thế nhiều khoảng trắng/xuống dòng liên tiếp thành 1 khoảng trắng duy nhất
    text = re.sub(r"\s+", " ", text).strip()
    if text.startswith(":"):
        text = text[1:].strip()
    return text.strip()


def scrape_nice_office():
    all_products = []

    print("🔎 Đang kết nối tới website NiceOffice...")
    res = requests.get(BASE_URL, headers=HEADERS, timeout=15)
    if res.status_code != 200:
        print(f"❌ Không thể truy cập website (Mã lỗi: {res.status_code})")
        return

    first_soup = BeautifulSoup(res.text, "html.parser")
    total_pages = get_total_pages(first_soup)
    print(f"📌 Tổng số trang phát hiện được: {total_pages} trang\n")

    for page in range(1, total_pages + 1):
        url = BASE_URL if page == 1 else f"{BASE_URL}page/{page}/"
        print(f"🔄 [{page}/{total_pages}] Đang cào dữ liệu: {url}")

        try:
            response = (
                requests.get(url, headers=HEADERS, timeout=15)
                if page > 1
                else res
            )
            if response.status_code != 200:
                print(
                    f"⚠️ Bỏ qua trang {page} (Lỗi HTTP {response.status_code})"
                )
                continue

            soup = BeautifulSoup(response.text, "html.parser")

            main_container = soup.select_one(
                ".shop-container, .products, .archive-products"
            )
            if not main_container:
                main_container = soup

            cards = main_container.select(
                ".product-small, .product-main, .col.post-item"
            )

            if not cards:
                cards = main_container.find_all(
                    "div", class_=lambda c: c and "col" in c and "product" in c
                )

            count_page_items = 0
            for card in cards:
                # 1. TÊN TÒA NHÀ & URL
                title_el = card.select_one(
                    ".title a, .product-title a, h3 a, h2 a, .name a"
                )
                if not title_el:
                    title_el = card.find(["h2", "h3", "h4", "a"])

                title = title_el.get_text(strip=True) if title_el else ""

                if (
                    not title
                    or len(title) < 3
                    or "TIN TỨC" in title.upper()
                    or "ĐỘI NGŨ" in title.upper()
                ):
                    continue

                product_url = ""
                a_tag = card.find("a", href=True)
                if a_tag:
                    product_url = a_tag["href"]

                # 2. URL THUMBNAIL IMAGE
                img_tag = card.find("img")
                thumbnail_url = ""
                if img_tag:
                    thumbnail_url = (
                        img_tag.get("data-src")
                        or img_tag.get("src")
                        or img_tag.get("srcset", "").split(" ")[0]
                    )

                # 3. GIÁ THUÊ THỰC TẾ
                price = ""
                ins_tag = card.find("ins")
                if ins_tag:
                    price = ins_tag.get_text(strip=True)
                else:
                    price_el = card.select_one(
                        ".price, .amount, span[class*='price']"
                    )
                    if price_el:
                        del_tag = price_el.find("del")
                        if del_tag:
                            del_tag.decompose()
                        price = price_el.get_text(strip=True)

                if price:
                    match_price = re.search(
                        r"(\d+[\d\.,]*)\s*USD", price, re.IGNORECASE
                    )
                    if match_price:
                        price = f"{match_price.group(1)} USD++ /m2"
                    else:
                        price = price.replace("+-", "++").strip()

                # 4. TRÍCH XUẤT ĐỊA CHỈ - DIỆN TÍCH - HƯỚNG BẰNG DOM PARSING NGUYÊN KHỐI
                address = ""
                area = ""
                direction = ""

                # Tìm tất cả các thẻ p/div/li chứa thông tin chi tiết
                paragraphs = card.find_all(["p", "div", "li"])

                for p in paragraphs:
                    # Bỏ qua khối giá hoặc tiêu đề
                    if (
                        p.find("ins")
                        or p.find("del")
                        or "price" in p.get("class", [])
                    ):
                        continue

                    # Lấy toàn bộ văn bản của riêng thẻ p đó (chưa bị cắt ngang bởi \n)
                    p_text = clean_text(p.get_text(strip=" "))

                    if not p_text or p_text == title or "USD" in p_text:
                        continue

                    # A. Bóc tách Địa chỉ (Chứa thông tin đường / phường / quận / thành phố / số nhà)
                    if not address and (
                        any(
                            k in p_text
                            for k in [
                                "Phường",
                                "Quận",
                                "Tân Bình",
                                "Bình Thạnh",
                                "Phú Nhuận",
                                "Đường",
                                "Sài Gòn",
                                "Tp.",
                                "Hồ Chí Minh",
                                "Xã",
                                "Huyện",
                            ]
                        )
                        or (
                            re.search(r"\d+/\d+", p_text)
                            and not re.match(r"^[\d\s,.]+$", p_text)
                        )
                    ):
                        address = p_text

                    # B. Bóc tách Diện tích (Chứa danh sách số m2 cách nhau bằng dấu phẩy)
                    elif not area and re.search(
                        r"^[\d\s,.]+$", p_text.replace("m2", "").strip()
                    ):
                        area = p_text

                    # C. Bóc tách Hướng
                    elif not direction and any(
                        d in p_text
                        for d in [
                            "Tây",
                            "Đông",
                            "Nam",
                            "Bắc",
                            "Đang cập nhật",
                            "Tây Bắc",
                            "Đông Nam",
                            "Tây Nam",
                            "Đông Bắc",
                        ]
                    ) and len(p_text) < 20:
                        direction = p_text

                all_products.append(
                    {
                        "Tòa nhà": title,
                        "Địa chỉ": address,
                        "Diện tích thuê": area,
                        "Hướng": direction,
                        "Giá thuê": price,
                        "URL Tòa nhà": product_url,
                        "URL Thumbnail": thumbnail_url,
                    }
                )
                count_page_items += 1

            print(f"   ↳ Lấy chính xác {count_page_items} tòa nhà.")
            time.sleep(1)

        except Exception as e:
            print(f"❌ Lỗi tại trang {page}: {e}")

    # Xuất file Excel
    if all_products:
        df = pd.DataFrame(all_products)
        df.drop_duplicates(subset=["Tòa nhà"], inplace=True)

        file_name = "Danh_Sach_Van_Phong_NiceOffice.xlsx"
        df.to_excel(file_name, index=False)
        print("\n" + "=" * 50)
        print(f"🎉 HOÀN THÀNH!")
        print(f"📊 Tổng số sản phẩm thu thập: {len(df)}")
        print(f"📁 File Excel đã lưu tại: {file_name}")
        print("=" * 50)


if __name__ == "__main__":
    scrape_nice_office()