import io
import re
import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup

# Cấu hình giao diện trang Web
st.set_page_config(
    page_title="Công cụ Thu Thập Dữ Liệu & Google Maps",
    page_icon="🏢",
    layout="wide",
)

st.title("🏢 Công Cụ Export Dữ Liệu NiceOffice & Geocoding Maps")
st.write(
    "Nhập URL danh mục sản phẩm từ website **NiceOffice** và tích hợp lấy tọa độ"
    " từ Google Maps."
)

# --- CẤU HÌNH API KEY TRÊN SIDEBAR ---
st.sidebar.header("⚙️ Cấu hình Google Maps API")
api_key_input = st.sidebar.text_input(
    "Nhập Google Maps API Key:",
    type="password",
    help="Dán API Key của bạn vào đây để lấy kinh độ, vĩ độ.",
)

# 1. Ô NHẬP URL
target_url = st.text_input(
    "📌 Nhập URL Danh Mục NiceOffice:",
    value="https://niceoffice.com.vn/danh-muc-vp/van-phong-cho-thue-hcm/",
    placeholder="https://niceoffice.com.vn/danh-muc-vp/van-phong-cho-thue-quan-1/",
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
        " like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


def clean_text(text):
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text).strip()
    if text.startswith(":"):
        text = text[1:].strip()
    return text.strip()


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


def get_lat_lng(address, building_name, api_key):
    """Hàm gọi Google Maps Geocoding API để lấy tọa độ từ Tòa nhà + Địa chỉ"""
    if not api_key:
        return "", ""

    # Kết hợp tên tòa nhà và địa chỉ để Google Maps tìm kiếm chính xác nhất
    query = f"{building_name}, {address}" if address else building_name
    url = f"https://maps.googleapis.com/maps/api/geocode/json?address={requests.utils.quote(query)}&key={api_key}"

    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data["results"]:
                location = data["results"][0]["geometry"]["location"]
                return location["lat"], location["lng"]
    except Exception:
        pass
    return "", ""


def scrape_data(base_url, api_key):
    if not base_url.endswith("/"):
        base_url += "/"

    all_products = []

    res = requests.get(base_url, headers=HEADERS, timeout=15)
    if res.status_code != 200:
        st.error(
            f"Không thể kết nối tới URL (Mã lỗi HTTP: {res.status_code}). Vui"
            " lòng kiểm tra lại đường link!"
        )
        return pd.DataFrame()

    first_soup = BeautifulSoup(res.text, "html.parser")
    total_pages = get_total_pages(first_soup)

    # Thanh hiển thị tiến độ (Progress bar)
    progress_bar = st.progress(0)
    status_text = st.empty()

    for page in range(1, total_pages + 1):
        url = base_url if page == 1 else f"{base_url}page/{page}/"
        status_text.text(
            f"🔄 Đang quét dữ liệu trang web [{page}/{total_pages}]..."
        )
        progress_bar.progress(page / total_pages)

        try:
            response = (
                requests.get(url, headers=HEADERS, timeout=15)
                if page > 1
                else res
            )
            if response.status_code != 200:
                continue

            soup = BeautifulSoup(response.text, "html.parser")
            main_container = (
                soup.select_one(
                    ".shop-container, .products, .archive-products"
                )
                or soup
            )
            cards = main_container.select(
                ".product-small, .product-main, .col.post-item"
            )

            for card in cards:
                title_el = card.select_one(
                    ".title a, .product-title a, h3 a, h2 a, .name a"
                ) or card.find(["h2", "h3", "h4", "a"])
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

                img_tag = card.find("img")
                thumbnail_url = ""
                if img_tag:
                    thumbnail_url = (
                        img_tag.get("data-src")
                        or img_tag.get("src")
                        or img_tag.get("srcset", "").split(" ")[0]
                    )

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

                address, area, direction = "", "", ""
                paragraphs = card.find_all(["p", "div", "li"])

                for p in paragraphs:
                    if (
                        p.find("ins")
                        or p.find("del")
                        or "price" in p.get("class", [])
                    ):
                        continue
                    p_text = clean_text(p.get_text(strip=" "))
                    if not p_text or p_text == title or "USD" in p_text:
                        continue

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
                    elif not area and re.search(
                        r"^[\d\s,.]+$", p_text.replace("m2", "").strip()
                    ):
                        area = p_text
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

        except Exception:
            pass

    df = pd.DataFrame(all_products)
    if not df.empty:
        df.drop_duplicates(subset=["Tòa nhà"], inplace=True)

        # Nếu người dùng có nhập API Key, tiến hành quét tọa độ Google Maps
        if api_key:
            status_text.text(
                "🗺️ Đang kết nối Google Maps để quét kinh độ, vĩ độ..."
            )
            lat_list = []
            lng_list = []

            for index, row in df.iterrows():
                lat, lng = get_lat_lng(row["Địa chỉ"], row["Tòa nhà"], api_key)
                lat_list.append(lat)
                lng_list.append(lng)

            df["Vĩ độ (Lat)"] = lat_list
            df["Kinh độ (Lng)"] = lng_list

    status_text.text("✅ Đã hoàn thành toàn bộ quá trình thu thập dữ liệu!")
    progress_bar.progress(1.0)
    return df


# 2. NÚT KÍCH HOẠT QUÉT DỮ LIỆU
if st.button("🚀 Bắt Đầu Thu Thập & Lấy Tọa Độ", type="primary"):
    if not target_url:
        st.warning("Vui lòng nhập đường link danh mục!")
    else:
        # Lấy API Key từ ô nhập hoặc Streamlit Secrets
        active_api_key = api_key_input or st.secrets.get(
            "GOOGLE_MAPS_API_KEY", ""
        )

        if not active_api_key:
            st.warning(
                "⚠️ Bạn chưa nhập Google Maps API Key ở thanh bên trái. Tool"
                " vẫn sẽ cào dữ liệu văn phòng bình thường nhưng sẽ bỏ qua phần"
                " lấy tọa độ!"
            )

        df_result = scrape_data(target_url, active_api_key)

        if not df_result.empty:
            st.success(
                f"🎉 Thu thập thành công **{len(df_result)}** sản phẩm!"
            )

            # 3. HIỂN THỊ BẢNG KẾT QUẢ NGAY BÊN DƯỚI
            st.subheader("📊 Bảng Dữ Liệu Trực Quan (Có Tọa Độ)")
            st.dataframe(df_result, use_container_width=True)

            # Nếu có dữ liệu tọa độ hợp lệ, hiển thị trực quan lên bản đồ Streamlit
            if (
                "Vĩ độ (Lat)" in df_result.columns
                and not df_result["Vĩ độ (Lat)"].eq("").all()
            ):
                map_df = df_result[
                    df_result["Vĩ độ (Lat)"].ne("")
                    & df_result["Kinh độ (Lng)"].ne("")
                ].copy()
                if not map_df.empty:
                    map_df["lat"] = map_df["Vĩ độ (Lat)"].astype(float)
                    map_df["lon"] = map_df["Kinh độ (Lng)"].astype(float)
                    st.subheader("🗺️ Bản Đồ Vị Trí Các Tòa Nhà")
                    st.map(map_df[["lat", "lon"]])

            # 4. NÚT TẢI FILE EXCEL
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
                df_result.to_excel(writer, index=False)

            st.download_button(
                label="📥 Tải File Excel Kết Quả (.xlsx)",
                data=buffer.getvalue(),
                file_name="NiceOffice_With_Coordinates.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        else:
            st.error("Không tìm thấy dữ liệu sản phẩm nào từ đường link này.")