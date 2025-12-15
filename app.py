import streamlit as st
from streamlit_folium import st_folium
import folium
from folium.plugins import BeautifyIcon
import sqlite3
from pathlib import Path
import uuid
from PIL import Image
import io
import html
import base64
import requests
from datetime import datetime
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.pyplot as plt
from matplotlib import font_manager, rc

font_path = "C:/Windows/Fonts/malgun.ttf"
font = font_manager.FontProperties(fname=font_path).get_name()
rc("font", family=font)
plt.rcParams["axes.unicode_minus"] = False


# ---------- 설정 ----------
DATA_DIR = Path("./data")
IMAGES_DIR = DATA_DIR / "images"
PHOTOS_DIR = DATA_DIR / "photos"
DB_PATH = DATA_DIR / "bookmarks.db"

DATA_DIR.mkdir(parents=True, exist_ok=True)
IMAGES_DIR.mkdir(parents=True, exist_ok=True)
PHOTOS_DIR.mkdir(parents=True, exist_ok=True)

# ---------- 카테고리 ----------
CATEGORIES = [
    "한식", "중식", "일식", "아시안", "양식",
    "패스트푸드", "카페/디저트", "술집", "기타"
]

# ---------- DB 유틸 ----------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS bookmarks (
            id TEXT PRIMARY KEY,
            name TEXT,
            address TEXT,
            lat REAL,
            lon REAL,
            image_path TEXT,
            rating INTEGER,
            is_recommended INTEGER,
            created_at TEXT,
            memo TEXT,
            category TEXT
        )
        """
    )

    c.execute("PRAGMA table_info(bookmarks)")
    cols = [row[1] for row in c.fetchall()]
    if "rating" not in cols:
        c.execute("ALTER TABLE bookmarks ADD COLUMN rating INTEGER")
    if "is_recommended" not in cols:
        c.execute("ALTER TABLE bookmarks ADD COLUMN is_recommended INTEGER")
    if "created_at" not in cols:
        c.execute("ALTER TABLE bookmarks ADD COLUMN created_at TEXT")
    if "memo" not in cols:
        c.execute("ALTER TABLE bookmarks ADD COLUMN memo TEXT")
    if "category" not in cols:
        c.execute("ALTER TABLE bookmarks ADD COLUMN category TEXT")

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS photos (
            id TEXT PRIMARY KEY,
            store_name TEXT,
            date TEXT,
            image_path TEXT
        )
        """
    )

    conn.commit()
    conn.close()


def insert_bookmark(bid, name, address, lat, lon, image_path, rating, is_recommended, category, memo=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    created_at = datetime.now().isoformat(timespec="seconds")
    c.execute(
        """
        INSERT INTO bookmarks (id, name, address, lat, lon, image_path, rating, is_recommended, created_at, memo, category)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (bid, name, address, lat, lon, image_path, rating, is_recommended, created_at, memo, category),
    )
    conn.commit()
    conn.close()


def get_all_bookmarks():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """
        SELECT id, name, address, lat, lon, image_path, rating, is_recommended, category, memo
        FROM bookmarks
        ORDER BY rowid DESC
        """
    )
    rows = c.fetchall()
    conn.close()
    return rows


def delete_bookmark(bid):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("SELECT image_path FROM bookmarks WHERE id = ?", (bid,))
    row = c.fetchone()
    if row and row[0]:
        p = Path(row[0])
        if p.exists():
            try:
                p.unlink()
            except Exception:
                pass

    c.execute("DELETE FROM bookmarks WHERE id = ?", (bid,))
    conn.commit()
    conn.close()


def update_memo(bid, memo_value):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE bookmarks SET memo = ? WHERE id = ?", (memo_value, bid))
    conn.commit()
    conn.close()


def insert_photo(pid, store_name, date_str, image_path):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO photos (id, store_name, date, image_path) VALUES (?, ?, ?, ?)",
        (pid, store_name, date_str, image_path),
    )
    conn.commit()
    conn.close()


def get_photos_by_date(date_str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT id, store_name, date, image_path FROM photos WHERE date = ? ORDER BY rowid ASC",
        (date_str,),
    )
    rows = c.fetchall()
    conn.close()
    return rows


def delete_photo(pid):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("SELECT image_path FROM photos WHERE id = ?", (pid,))
    row = c.fetchone()
    if row and row[0]:
        p = Path(row[0])
        if p.exists():
            try:
                p.unlink()
            except Exception:
                pass

    c.execute("DELETE FROM photos WHERE id = ?", (pid,))
    conn.commit()
    conn.close()


# ---------- 유틸: 이미지 -> data uri ----------
def image_file_to_data_uri(image_path: str | Path):
    try:
        with open(image_path, "rb") as f:
            data = f.read()
        mime = "image/png"
        encoded = base64.b64encode(data).decode("utf-8")
        return f"data:{mime};base64,{encoded}"
    except Exception:
        return None


# ---------- 유틸: 주소 → 좌표 (지오코딩) ----------
def geocode_address(address: str):
    try:
        url = "https://nominatim.openstreetmap.org/search"
        params = {"q": address, "format": "json", "limit": 1}
        headers = {"User-Agent": "limstreat-app"}
        resp = requests.get(url, params=params, headers=headers, timeout=8)
        resp.raise_for_status()
        data = resp.json()
        if not data:
            return None
        return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception:
        return None


# ---------- 초기화 ----------
init_db()

# ---------- Streamlit 페이지 설정 ----------
st.set_page_config(page_title="Limstreat - Taste Mark Map", layout="wide")
st.title("Limstreat — 테이스트 마크 지도")

# ---------- 세션 상태 초기값 ----------
if "clicked_lat" not in st.session_state:
    st.session_state["clicked_lat"] = None
if "clicked_lon" not in st.session_state:
    st.session_state["clicked_lon"] = None
if "album_index" not in st.session_state:
    st.session_state["album_index"] = 0
if "album_date" not in st.session_state:
    st.session_state["album_date"] = datetime.today().date()
if "mode" not in st.session_state:
    st.session_state["mode"] = "맛집 지도"
if "filter_mode" not in st.session_state:
    st.session_state["filter_mode"] = "전체 보기"
if "edit_memo" not in st.session_state:
    st.session_state["edit_memo"] = {}
if "review_q" not in st.session_state:
    st.session_state["review_q"] = ""


# ---------- 공통 함수 ----------
def render_stars(rating: int | None):
    if rating is None:
        return "별점 없음"
    try:
        r = int(rating)
    except Exception:
        return "별점 없음"
    r = max(0, min(5, r))
    return "⭐" * r + "☆" * (5 - r)


def apply_filter(rows, filter_mode: str):
    def ok(row):
        is_rec = bool(row[7])
        if filter_mode == "전체 보기":
            return True
        if filter_mode == "추천 💗만":
            return is_rec
        if filter_mode == "비추천만":
            return not is_rec
        return True

    return [r for r in rows if ok(r)]


def marker_icon(is_recommended: int):
    """
    ✅ 추천: 핑크 핀 + 흰색 하트
    ✅ 비추천: 진회색 핀만 (안쪽 아이콘 없음)
    """
    if is_recommended:
        return BeautifyIcon(
            icon_shape="marker",
            number="🤍",
            text_color="white",
            background_color="#ff4fa3",
            border_color="#ff4fa3",
        )
    return BeautifyIcon(
        icon_shape="marker",
        number="",
        text_color="white",
        background_color="#4a4a4a",  # 진회색
        border_color="#4a4a4a",
    )


# ---------- 사이드바 ----------
rows_all = get_all_bookmarks()
total_count = len(rows_all)
rec_count = sum(1 for r in rows_all if r[7])
nonrec_count = total_count - rec_count

st.sidebar.markdown("#### 표시할 맛집")
filter_choice = st.sidebar.radio(
    "",
    ["전체 보기", "추천 💗만", "비추천만"],
    index=["전체 보기", "추천 💗만", "비추천만"].index(st.session_state["filter_mode"]),
)
st.session_state["filter_mode"] = filter_choice

st.sidebar.write(f"전체: {total_count}곳")
st.sidebar.write(f"추천 💗: {rec_count}곳")
st.sidebar.write(f"비추천: {nonrec_count}곳")

st.sidebar.markdown("---")
st.sidebar.markdown("#### 화면 이동")
if st.sidebar.button("지도"):
    st.session_state["mode"] = "맛집 지도"
    st.rerun()
if st.sidebar.button("리뷰"):
    st.session_state["mode"] = "한 입 노트"
    st.rerun()
if st.sidebar.button("앨범"):
    st.session_state["mode"] = "오늘의 한 입 앨범"
    st.rerun()
# ✅ 4번: 통계 버튼 추가(지도/리뷰/앨범 버튼 밑)
if st.sidebar.button("📊 통계"):
    st.session_state["mode"] = "카테고리 통계"
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.markdown("#### 날짜별 사진 보기")
selected_date_sidebar = st.sidebar.date_input("날짜 선택", value=st.session_state["album_date"])
st.session_state["album_date"] = selected_date_sidebar

mode = st.session_state["mode"]
filter_mode = st.session_state["filter_mode"]


# ==========================
# 화면 1: 맛집 지도
# ==========================
if mode == "맛집 지도":
    st.subheader("맛집 지도")

    col_map, col_form = st.columns([3, 2])

    with col_form:
        st.markdown("#### 가게 정보 입력")

        with st.form("bookmark_form_map", clear_on_submit=True):
            name_input = st.text_input("가게 이름 *")
            address_input = st.text_input("주소 *", placeholder="예: 서울특별시 중구 세종대로 110")
            rating_input = st.slider("별점 (1 ~ 5)", min_value=1, max_value=5, value=5)
            recommend_label = st.radio("추천 여부", ["추천", "비추천"], index=0, horizontal=True)
            uploaded_file = st.file_uploader("대표 이미지 (선택, png/jpg/jpeg)", type=["png", "jpg", "jpeg"])

            # ✅ 카테고리: 등록할 때 선택 (업로드 아래)
            category_input = st.selectbox("카테고리", CATEGORIES, index=0)

            submitted = st.form_submit_button("저장하기")

            if submitted:
                if not name_input.strip():
                    st.error("가게 이름을 입력해주세요.")
                    st.stop()
                if not address_input.strip():
                    st.error("주소를 입력해주세요.")
                    st.stop()

                geo = geocode_address(address_input.strip())
                if geo is None:
                    st.error("주소를 찾지 못했어요. 더 구체적으로 입력해 주세요. (예: 도로명 + 건물번호)")
                    st.stop()

                lat, lon = geo
                st.session_state["clicked_lat"] = lat
                st.session_state["clicked_lon"] = lon

                bid = str(uuid.uuid4())
                saved_image_path = None
                if uploaded_file:
                    try:
                        img = Image.open(io.BytesIO(uploaded_file.read()))
                        img.thumbnail((1024, 1024))
                        saved_image_path = IMAGES_DIR / f"{bid}.png"
                        img.save(saved_image_path, format="PNG")
                        saved_image_path = str(saved_image_path)
                    except Exception as e:
                        st.warning(f"이미지 저장 중 오류 발생: {e}")
                        saved_image_path = None

                is_recommended = 1 if recommend_label == "추천" else 0

                insert_bookmark(
                    bid,
                    name_input.strip(),
                    address_input.strip(),
                    float(lat),
                    float(lon),
                    saved_image_path,
                    int(rating_input),
                    is_recommended,
                    category_input,
                    None,  # ✅ 메모는 리뷰에서만
                )
                st.success("저장 완료! 지도도 해당 위치로 이동했어요 🙂")
                st.rerun()

        st.caption("지도 클릭 좌표는 참고용입니다. 저장은 ‘주소 기준’으로 진행돼요.")

    with col_map:
        base_lat = st.session_state["clicked_lat"] if st.session_state["clicked_lat"] is not None else 37.5665
        base_lon = st.session_state["clicked_lon"] if st.session_state["clicked_lon"] is not None else 126.9780

        m = folium.Map(location=[base_lat, base_lon], zoom_start=13, tiles="OpenStreetMap")
        rows_filtered = apply_filter(get_all_bookmarks(), filter_mode)

        for bid, name, address, lat, lon, image_path, rating, is_recommended, category, memo in rows_filtered:
            name_esc = html.escape(name or "")
            address_esc = html.escape(address or "")
            category_esc = html.escape(category or "")

            popup_html = f"<b>{name_esc}</b><br>{address_esc}"
            if category_esc:
                popup_html += f"<br>카테고리: {category_esc}"
            if rating is not None:
                popup_html += f"<br>별점: {render_stars(rating)}"
            if image_path:
                data_uri = image_file_to_data_uri(image_path)
                if data_uri:
                    popup_html += f"<br><img src='{data_uri}' width='200' />"

            folium.Marker(
                location=[lat, lon],
                popup=folium.Popup(popup_html, max_width=320),
                icon=marker_icon(is_recommended),
            ).add_to(m)

        map_data = st_folium(m, width="100%", height=650)

        # 클릭 좌표(참고용)
        last_clicked = None
        if isinstance(map_data, dict):
            last_clicked = map_data.get("last_clicked") or map_data.get("last_clicked_point") or None
        if last_clicked and isinstance(last_clicked, dict):
            lat_val = last_clicked.get("lat")
            lng_val = last_clicked.get("lng")
            if lat_val is not None and lng_val is not None:
                st.session_state["clicked_lat"] = float(lat_val)
                st.session_state["clicked_lon"] = float(lng_val)


# ==========================
# 화면 2: 한 입 노트 (리뷰)
# ==========================
elif mode == "한 입 노트":
    st.subheader("한 입 노트")

    # ✅ 검색 1줄
    q = st.text_input("가게 검색", value=st.session_state.get("review_q", ""), placeholder="이름/주소로 검색")
    st.session_state["review_q"] = q

    rows = apply_filter(get_all_bookmarks(), filter_mode)

    # 검색 적용(이름/주소)
    if q.strip():
        qq = q.strip().lower()
        rows = [
            r for r in rows
            if (r[1] and qq in r[1].lower()) or (r[2] and qq in r[2].lower())
        ]

    if not rows:
        st.info("조건에 맞는 맛집이 없습니다.")
    else:
        for bid, name, address, lat, lon, image_path, rating, is_recommended, category, memo in rows:
            with st.container(border=True):
                top = st.columns([1.2, 4.8, 1.0])

                with top[0]:
                    if image_path and Path(image_path).exists():
                        try:
                            st.image(image_path, use_column_width=True)
                        except Exception:
                            st.caption("이미지 로드 실패")
                    else:
                        st.caption("이미지 없음")

                with top[1]:
                    st.markdown(f"### {name}")
                    st.caption(address)

                    rec_text = "추천" if is_recommended else "비추천"
                    # 카테고리는 한 줄에만 살짝(원하면 지워도 됨)
                    if category and str(category).strip():
                        st.write(f"{rec_text} · {render_stars(rating)} · {category}")
                    else:
                        st.write(f"{rec_text} · {render_stars(rating)}")

                with top[2]:
                    st.caption(" ")
                    if st.button("삭제", key=f"del-{bid}"):
                        delete_bookmark(bid)
                        st.session_state["edit_memo"].pop(bid, None)
                        st.session_state.pop(f"memo-edit-{bid}", None)
                        st.rerun()

                st.divider()

                # ✅ 메모(리뷰에서만)
                st.markdown("**메모**")
                is_edit = st.session_state.get("edit_memo", {}).get(bid, False)

                if not is_edit:
                    if memo and memo.strip():
                        preview_text = memo.replace("\n", "  \n")
                        st.markdown(preview_text, unsafe_allow_html=False)
                        if st.button("✏️ 메모 편집", key=f"edit-{bid}"):
                            st.session_state["edit_memo"][bid] = True
                            st.rerun()
                    else:
                        if st.button("+ 메모 추가", key=f"addmemo-{bid}"):
                            st.session_state["edit_memo"][bid] = True
                            st.rerun()

                else:
                    new_memo = st.text_area(
                        " ",
                        value=memo or "",
                        height=120,
                        key=f"memo-edit-{bid}",
                        placeholder="링크는 [이름](https://주소) 형식으로 쓰면 클릭돼요.",
                    )

                    action = st.columns([1, 1, 6])
                    with action[0]:
                        if st.button("💾 저장", key=f"save-{bid}"):
                            update_memo(bid, new_memo.strip() if new_memo.strip() else None)
                            st.session_state["edit_memo"][bid] = False
                            st.session_state.pop(f"memo-edit-{bid}", None)
                            st.rerun()

                    with action[1]:
                        if st.button("취소", key=f"cancel-{bid}"):
                            st.session_state["edit_memo"][bid] = False
                            st.session_state.pop(f"memo-edit-{bid}", None)
                            st.rerun()


# ==========================
# 화면 3: 오늘의 한 입 앨범
# ==========================
elif mode == "오늘의 한 입 앨범":
    st.subheader("오늘의 한 입 앨범")

    selected_date = st.session_state["album_date"]
    date_str = selected_date.isoformat()

    st.markdown(f"#### {date_str} 사진 업로드")

    with st.form("photo_upload_form"):
        photo_files = st.file_uploader(
            "사진 업로드 (여러 장 가능)", type=["png", "jpg", "jpeg"], accept_multiple_files=True
        )
        uploaded = st.form_submit_button("사진 저장")

        if uploaded:
            if not photo_files:
                st.warning("업로드할 사진을 선택해주세요.")
            else:
                count = 0
                for file in photo_files:
                    try:
                        img = Image.open(io.BytesIO(file.read()))
                        img.thumbnail((1920, 1920))
                        pid = str(uuid.uuid4())
                        filename = f"{date_str}_{pid}.png"
                        save_path = PHOTOS_DIR / filename
                        img.save(save_path, format="PNG")
                        insert_photo(pid, "", date_str, str(save_path))
                        count += 1
                    except Exception as e:
                        st.warning(f"사진 저장 중 오류 발생: {e}")
                if count > 0:
                    st.success(f"{count}장의 사진이 저장되었습니다.")
                    st.session_state["album_index"] = 0
                    st.rerun()

    st.divider()
    st.markdown(f"#### {date_str} 사진 모아보기")

    photos = get_photos_by_date(date_str)
    if not photos:
        st.info("이 날짜에는 아직 업로드된 사진이 없습니다.")
    else:
        idx = st.session_state.get("album_index", 0)
        idx = max(0, min(idx, len(photos) - 1))
        st.session_state["album_index"] = idx

        pid, store_name, d, image_path = photos[idx]

        st.write(f"총 {len(photos)}장 중 {idx + 1}번째")

        col_l, col_c, col_r = st.columns([1, 2, 1])
        with col_c:
            if Path(image_path).exists():
                st.image(image_path, use_column_width=True)
            else:
                st.write("[이미지 파일을 찾을 수 없습니다]")

        del_cols = st.columns([2, 1, 6])
        with del_cols[0]:
            confirm = st.checkbox("삭제 확인", key=f"delcheck-{pid}")
        with del_cols[1]:
            if st.button("삭제", key=f"delete-{pid}"):
                if not confirm:
                    st.warning("‘삭제 확인’을 체크해 주세요.")
                else:
                    delete_photo(pid)
                    photos2 = get_photos_by_date(date_str)
                    if not photos2:
                        st.session_state["album_index"] = 0
                    else:
                        st.session_state["album_index"] = min(idx, len(photos2) - 1)
                    st.rerun()

        col_prev, col_info, col_next = st.columns([1, 3, 1])
        with col_prev:
            if st.button("⬅ 이전"):
                st.session_state["album_index"] = (idx - 1) % len(photos)
                st.rerun()
        with col_info:
            dots = "".join("●" if i == idx else "○" for i in range(len(photos)))
            st.markdown(f"<div style='text-align:center;font-size:20px'>{dots}</div>", unsafe_allow_html=True)
        with col_next:
            if st.button("다음 ➡"):
                st.session_state["album_index"] = (idx + 1) % len(photos)
                st.rerun()


# ==========================
# 화면 4: 카테고리 통계
# ==========================
elif mode == "카테고리 통계":
    import pandas as pd
    import matplotlib.pyplot as plt
    from matplotlib import font_manager, rc

    st.markdown("### 📊 카테고리 통계")

    # ---------- 한글 폰트 ----------
    try:
        font_path = "C:/Windows/Fonts/malgun.ttf"
        font = font_manager.FontProperties(fname=font_path).get_name()
        rc("font", family=font)
        plt.rcParams["axes.unicode_minus"] = False
    except Exception:
        pass

    # ---------- 고정 카테고리 ----------
    categories = [
        "한식", "중식", "일식", "아시안",
        "양식", "패스트푸드",
        "카페/디저트", "술집", "미분류"
    ]

    # ---------- 데이터 ----------
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT category FROM bookmarks", conn)
    conn.close()

    if df.empty:
        counts = pd.Series(0, index=categories)
    else:
        counts = (
            df["category"]
            .fillna("미분류")
            .value_counts()
            .reindex(categories, fill_value=0)
        )

    labels = counts.index.tolist()
    values = counts.values.tolist()

    # ---------- 색상 ----------
    color_map = {
        "한식": "#4E79A7",
        "중식": "#F28E2B",
        "일식": "#59A14F",
        "아시안": "#E15759",
        "양식": "#9C755F",
        "패스트푸드": "#B07AA1",
        "카페/디저트": "#FF4FA3",
        "술집": "#4A4A4A",
        "미분류": "#BAB0AC",
    }
    colors = [color_map[l] for l in labels]

    # ---------- 차트 (조금 크게) ----------
    fig, ax = plt.subplots(
        figsize=(4.4, 2.8),   # 🔼 차트는 키움
        dpi=180
    )

    x = range(len(labels))
    ax.bar(x, values, color=colors, width=0.55)

    # ---------- 글씨는 작게 유지 ----------
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=4, color="#555555")
    ax.set_ylabel("횟수", fontsize=5)

    # 숫자 라벨 (0 제외, 작게)
    for i, v in enumerate(values):
      if v > 0:
        ax.text(i, v + 0.05, str(v), ha="center", va="bottom", fontsize=5)

    # y축 여유
    ymax = max(values) if values else 0
    ax.set_ylim(0, ymax + 1)

    # 테두리 제거
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    # 🔽 차트 전체를 아래로 내림
    plt.subplots_adjust(top=0.72, bottom=0.32)

    # ---------- 가운데 정렬 ----------
    col_l, col_c, col_r = st.columns([1, 2, 1])
    with col_c:
      st.pyplot(fig)


