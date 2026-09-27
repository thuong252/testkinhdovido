import io
import re
import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup
from geopy.geocoders import ArcGIS

# Cấu hình giao diện trang Web
st.set_page_config(
    page_title="Công cụ Thu Thập Dữ Liệu & Tọa Độ ArcGIS",
    page_icon="🏢",
    layout="wide",
)

st.title("🏢 Công Cụ Export Dữ Liệu NiceOffice & Lấy Tọa Độ ArcGIS")
st.write(
    "Tool tự động quét dữ liệu từ **NiceOffice** và lấy tọa độ chính xác dựa trên"
    " **Tên tòa nhà** (Cột B) hoàn toàn miễn phí."
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


def get_lat_lng_by_building(building_name, address):
    """Sử dụng ArcGIS geocoder miễn phí, không bị chặn IP trên Streamlit Cloud"""
    try:
        # Khởi tạo ArcGIS geolocator
        geolocator = ArcGIS(user_agent="niceoffice_app_v3")

        # Làm sạch tên tòa nhà (loại bỏ chữ 'TÒA NHÀ' để tìm kiếm chuẩn hơn)
        clean_name = re.sub(
            r"^tòa nhà\s*", "", building_name, flags=re.IGNORECASE
        ).strip()

        # Ưu tiên tìm kiếm kết hợp: Tên tòa nhà + Địa chỉ + Thành phố Hồ Chí Minh
        query = f"{clean_name}, {address}, Thành phố Hồ Chí Minh"

        location = geolocator.geocode(query, timeout=10)
        if location:
            return location.latitude, location.longitude

        # Fallback 1: Thử tìm với tên đầy đủ + địa chỉ
        query_alt = f"{building_name}, {address}, TP.HCM"
        location_alt = geolocator.geocode(query_alt, timeout=10)
        if location_alt:
            return location_alt.latitude, location_alt.longitude

        # Fallback 2: Nếu không ra, tìm bằng riêng địa chỉ
        if address:
            location_addr = geolocator.geocode(
                f"{address}, Thành phố Hồ Chí Minh", timeout=10
            )
            if location_addr:
                return location_addr.latitude, location_addr.longitude

    except Exception:
        pass
    return "", ""


def scrape_data(base_url):
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

        # Tiến hành quét tọa độ qua ArcGIS dựa trên Tên tòa nhà + Địa chỉ
        status_text.text(
            "🗺️ Đang tra cứu tọa độ qua ArcGIS theo Tên tòa nhà..."
        )
        lat_list = []
        lng_list = []

        for index, row in df.iterrows():
            lat, lng = get_lat_lng_by_building(row["Tòa nhà"], row["Địa chỉ"])
            lat_list.append(lat)
            lng_list.append(lng)

        df["Vĩ độ (Lat)"] = lat_list
        df["Kinh độ (Lng)"] = lng_list

    status_text.text("✅ Đã hoàn thành toàn bộ quá trình thu thập dữ liệu!")
    progress_bar.progress(1.0)
    return df


# 2. NÚT KÍCH HOẠT QUÉT DỮ LIỆU
if st.button("🚀 Bắt Đầu Thu Thập & Lấy Tọa Độ ArcGIS", type="primary"):
    if not target_url:
        st.warning("Vui lòng nhập đường link danh mục!")
    else:
        df_result = scrape_data(target_url)

        if not df_result.empty:
            st.success(
                f"🎉 Thu thập thành công **{len(df_result)}** sản phẩm!"
            )

            # 3. HIỂN THỊ BẢNG KẾT QUẢ NGAY BÊN DƯỚI
            st.subheader("📊 Bảng Dữ Liệu Trực Quan (Có Tọa Độ)")
            st.dataframe(df_result, use_container_width=True)

            # Hiển thị trực quan lên bản đồ Streamlit
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
                file_name="NiceOffice_ArcGIS_Coordinates.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        else:
            st.error("Không tìm thấy dữ liệu sản phẩm nào từ đường link này.")
