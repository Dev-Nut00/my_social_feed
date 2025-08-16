import os
import uuid
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

# --------------------------
# 상수(경로/스키마)
# --------------------------
APP_TITLE = "My Social Feed"
DATA_DIR = Path("data")
USERS_CSV = DATA_DIR / "users.csv"
POSTS_CSV = DATA_DIR / "posts.csv"
LIKES_CSV = DATA_DIR / "likes.csv"

# 각 CSV 파일의 컬럼 스키마 정의
USERS_COLUMNS = ["user_id", "user_password", "username", "username_lc", "created_at"]
POSTS_COLUMNS = ["post_id", "author_id", "content", "created_at", "is_retweet", "retweet_of_post_id"]
LIKES_COLUMNS = ["post_id", "user_id", "created_at"]

# ======================================================================
# 데이터 유틸리티: CSV 파일 생성/로드/쓰기
# ======================================================================

def ensure_csv(path: Path, columns: list[str]) -> None:
    """지정한 경로에 CSV 파일이 없으면 '헤더만 있는 빈 파일'을 생성합니다.
    - path: 생성할 CSV 파일 경로
    - columns: 헤더로 사용할 컬럼 리스트
    """
    path.parent.mkdir(parents=True, exist_ok=True)  # data/ 폴더 생성(이미 있으면 무시)
    if not path.exists():
        df = pd.DataFrame(columns=columns)
        df.to_csv(path, index=False)


def bootstrap_data_files() -> None:
    """앱 시작 시 필요한 CSV 파일 3종(users/posts/likes)을 보장합니다."""
    ensure_csv(USERS_CSV, USERS_COLUMNS)
    ensure_csv(POSTS_CSV, POSTS_COLUMNS)
    ensure_csv(LIKES_CSV, LIKES_COLUMNS)


@st.cache_data(show_spinner=False)
def load_users() -> pd.DataFrame:
    """users.csv를 로드하여 DataFrame으로 반환합니다.
    - @st.cache_data: 동일 입력에 대해 결과를 캐시하여 디스크 접근 최소화
    - 반환 직전 NaN은 공백 문자열로 치환해 UI/저장 로직 단순화
    """
    return pd.read_csv(USERS_CSV, dtype=str).fillna("")


@st.cache_data(show_spinner=False)
def load_posts() -> pd.DataFrame:
    """posts.csv를 로드합니다.
    - 정렬 편의를 위해 내부 사용 컬럼('_created_at_dt')을 추가합니다.
    - CSV에는 저장하지 않으며 캐시 상태에서만 사용합니다.
    """
    df = pd.read_csv(POSTS_CSV, dtype=str).fillna("")
    if not df.empty:
        df["_created_at_dt"] = pd.to_datetime(df["created_at"], errors="coerce")
    return df


@st.cache_data(show_spinner=False)
def load_likes() -> pd.DataFrame:
    """likes.csv를 로드합니다."""
    return pd.read_csv(LIKES_CSV, dtype=str).fillna("")


def clear_data_caches():
    """캐시된 users/posts/likes 데이터를 무효화합니다.
    - CSV에 변경이 생긴 뒤 호출하여 새로고침 없이도 최신 데이터 반영
    - st.rerun()과 조합하여 즉시 UI 업데이트
    """
    load_users.clear()
    load_posts.clear()
    load_likes.clear()


def now_iso() -> str:
    """현재 시간을 ISO8601(초 단위) 문자열로 반환합니다."""
    return datetime.now().isoformat(timespec="seconds")


def append_row(path: Path, row: dict, columns: list[str]) -> None:
    """CSV 파일에 한 행을 '안전하게' 추가합니다.
    - columns 순서를 강제하여 컬럼 순서 변동으로 인한 꼬임 방지
    - 파일이 비어있다면 헤더 포함, 아니면 헤더 없이 append
    """
    df = pd.DataFrame([row], columns=columns)
    df.to_csv(
        path,
        mode="a",
        header=not path.exists() or os.path.getsize(path) == 0,
        index=False,
    )


def overwrite_df(path: Path, df: pd.DataFrame) -> None:
    """CSV 파일 전체를 덮어씁니다. (예: 좋아요 취소 등)"""
    df.to_csv(path, index=False)


# ======================================================================
# 도메인 로직: 사용자/게시글/좋아요/리트윗
# ======================================================================

def username_exists(username: str) -> bool:
    """주어진 사용자명이 이미 존재하는지(대소문자 무시) 체크합니다."""
    users = load_users()
    return not users[users["username_lc"] == username.lower()].empty


def create_user(username: str, password: str) -> tuple[bool, str]:
    """회원가입 처리
    - 유효성 검증(공백 체크, 중복 체크) 후 users.csv에 추가
    - 반환: (성공여부, 메시지)
    """
    if not username.strip():
        return False, "사용자명을 입력해주세요."
    if not password.strip():
        return False, "비밀번호를 입력해주세요."
    if username_exists(username):
        return False, "이미 존재하는 사용자명입니다."

    user = {
        "user_id": uuid.uuid4().hex,            # 내부 참조용 UUID
        "user_password": password,               # ⚠ 교육용 평문 저장 (실서비스 금지)
        "username": username,                    # 화면 표시용 이름
        "username_lc": username.lower(),         # 중복/검색 대비 소문자 버전
        "created_at": now_iso(),
    }
    append_row(USERS_CSV, user, USERS_COLUMNS)
    clear_data_caches()
    return True, "회원가입이 완료되었습니다. 로그인해주세요."


def verify_login(username: str, password: str):
    """로그인 인증
    - username(대소문자 무시)와 password가 모두 일치하는 사용자 행을 찾습니다.
    - 성공 시 해당 사용자 row(dict)를, 실패 시 None을 반환합니다.
    """
    users = load_users()
    mask = (users["username_lc"] == username.lower()) & (users["user_password"] == password)
    row = users[mask]
    if row.empty:
        return None
    return row.iloc[0].to_dict()


def add_post(author_id: str, content: str, retweet_of_post_id: str | None = None) -> tuple[bool, str]:
    """게시글/리트윗 추가
    - 일반 글: content 필수, 길이 280자 제한
    - 리트윗: content 없이 retweet_of_post_id만 저장
    - 반환: (성공여부, 메시지)
    """
    content = content.strip()
    if not content and not retweet_of_post_id:
        return False, "내용을 입력해주세요."
    if len(content) > 280:
        return False, "내용은 최대 280자까지 가능합니다."

    post = {
        "post_id": uuid.uuid4().hex,
        "author_id": author_id,
        "content": content,
        "created_at": now_iso(),
        "is_retweet": "True" if retweet_of_post_id else "False",
        "retweet_of_post_id": retweet_of_post_id or "",
    }
    append_row(POSTS_CSV, post, POSTS_COLUMNS)
    clear_data_caches()
    return True, "게시글이 등록되었습니다."


def has_liked(post_id: str, user_id: str) -> bool:
    """해당 사용자가 특정 게시글에 좋아요를 눌렀는지 여부를 반환합니다."""
    likes = load_likes()
    return not likes[(likes["post_id"] == post_id) & (likes["user_id"] == user_id)].empty


def toggle_like(post_id: str, user_id: str) -> None:
    """좋아요 토글
    - 이미 눌렀으면 취소(행 삭제), 아니면 추가(행 삽입)
    - 저장 후 캐시 무효화
    """
    likes = load_likes()
    mask = (likes["post_id"] == post_id) & (likes["user_id"] == user_id)
    if mask.any():
        # 좋아요 취소: 해당 행 제거 후 전체 저장
        likes = likes[~mask]
        overwrite_df(LIKES_CSV, likes)
    else:
        # 좋아요 추가: 한 행 append
        new_row = {"post_id": post_id, "user_id": user_id, "created_at": now_iso()}
        append_row(LIKES_CSV, new_row, LIKES_COLUMNS)
    clear_data_caches()


def already_retweeted(target_post_id: str, user_id: str) -> bool:
    """동일 사용자가 동일 게시글을 이미 리트윗했는지(중복 방지) 체크합니다."""
    posts = load_posts()
    if posts.empty:
        return False
    mask = (
        (posts["author_id"] == user_id)
        & (posts["is_retweet"] == "True")
        & (posts["retweet_of_post_id"] == target_post_id)
    )
    return posts[mask].shape[0] > 0


# ======================================================================
# UI 컴포넌트: 로그인/회원가입, 작성폼, 피드, 사이드바
# ======================================================================

def show_login_box():
    """로그인/회원가입 탭 UI.
    - 로그인 성공 시 session_state["user"]에 사용자 dict 저장 후 st.rerun()
    - 회원가입은 create_user() 호출
    """
    st.subheader("🔐 로그인 / 회원가입")
    tabs = st.tabs(["로그인", "회원가입"])

    # --- 로그인 탭 ---
    with tabs[0]:
        with st.form("login_form", clear_on_submit=False):
            username = st.text_input("사용자명", key="login_username")
            password = st.text_input("비밀번호", type="password", key="login_password")
            submitted = st.form_submit_button("로그인")
        if submitted:
            user = verify_login(username, password)
            if user:
                st.session_state["user"] = user
                st.success(f"환영합니다, {user['username']}님!")
                st.rerun()  # 로그인 직후 화면 리프레시
            else:
                st.error("사용자명 또는 비밀번호가 올바르지 않습니다.")

    # --- 회원가입 탭 ---
    with tabs[1]:
        with st.form("signup_form", clear_on_submit=True):
            new_username = st.text_input("사용자명", key="signup_username")
            new_password = st.text_input("비밀번호", type="password", key="signup_password")
            submitted = st.form_submit_button("회원가입")
        if submitted:
            ok, msg = create_user(new_username, new_password)
            if ok:
                st.success(msg)
            else:
                st.error(msg)


def user_by_id(user_id: str) -> str:
    """user_id로 users.csv에서 표시 이름(username)을 찾아 반환합니다.
    - 삭제/유실 등으로 못 찾으면 '알수없음' 반환
    """
    users = load_users()
    row = users[users["user_id"] == user_id]
    if row.empty:
        return "알수없음"
    return str(row.iloc[0]["username"])


def post_by_id(post_id: str) -> dict | None:
    """post_id로 posts.csv에서 게시글 한 건을 dict로 반환합니다. 없으면 None."""
    posts = load_posts()
    row = posts[posts["post_id"] == post_id]
    if row.empty:
        return None
    return row.iloc[0].to_dict()


def like_count(post_id: str) -> int:
    """해당 게시글의 좋아요 개수를 반환합니다."""
    likes = load_likes()
    return int(likes[likes["post_id"] == post_id].shape[0])


def show_compose_box(current_user: dict):
    st.subheader("📝 새 글 작성")

    # 기본값을 별도 세션 변수에서 관리
    if "compose_default" not in st.session_state:
        st.session_state["compose_default"] = ""

    content = st.text_area(
        "무슨 일이 일어나고 있나요?",
        key="compose_content",
        height=120,
        max_chars=280,
        value=st.session_state["compose_default"],   # 초기값 설정
        placeholder="최대 280자",
    )

    cols = st.columns([1, 1, 6])

    if cols[0].button("게시", key="btn_post"):
        ok, msg = add_post(current_user["user_id"], content)
        if ok:
            st.success(msg)
            # 다음에 text_area를 다시 그릴 때 빈 값으로 시작하게 만듦
            st.session_state["compose_default"] = ""
            st.rerun()
        else:
            st.warning(msg)

    cols[1].button("피드 새로고침", key="btn_refresh", on_click=lambda: st.rerun())



def render_post_card(post: dict, current_user: dict | None):
    """피드 내 한 개의 게시글 카드 렌더링.
    - 일반 글과 리트윗을 구분 표시
    - 좋아요/리트윗 버튼은 각 게시글별 고유 key를 사용(중복 키 방지)
    """
    # 상단 메타 영역(작성자/시간)
    author_name = user_by_id(post["author_id"])
    created_at = post.get("created_at", "")

    is_rt = (post.get("is_retweet") == "True")
    rt_src_id = post.get("retweet_of_post_id") or ""

    st.markdown("---")
    if is_rt:
        # 리트윗인 경우: 인용 표시 형태로 원본 글을 함께 보여줍니다.
        st.markdown(f"🔁 **{author_name}** 님이 리트윗했습니다 · {created_at}")
        src = post_by_id(rt_src_id)
        if src is None:
            st.write("> [원본 게시글이 삭제되었습니다]")
        else:
            src_author = user_by_id(src["author_id"])
            st.write(f"> **@{src_author}**: {src['content']} \n> _{src.get('created_at','')}_")
    else:
        # 일반 글
        st.markdown(f"**{author_name}** · {created_at}")
        st.write(post["content"])

    # 하단 인터랙션(좋아요/리트윗)
    pid = post["post_id"]
    lc = like_count(pid)
    liked = current_user and has_liked(pid, current_user["user_id"])  # 사용자가 이미 좋아요 했는지
    col_like, col_rt, col_meta = st.columns([1, 1, 6])

    # 좋아요 버튼: 누른 상태에 따라 하트 아이콘 변경
    like_label = f"{'❤️' if liked else '🤍'} 좋아요 ({lc})"
    if col_like.button(like_label, key=f"like_{pid}"):
        if current_user:
            toggle_like(pid, current_user["user_id"])  # 토글 후 캐시 무효화
            st.rerun()
        else:
            st.warning("로그인이 필요합니다.")

    # 리트윗 버튼: 이미 리트윗한 경우 비활성화하여 중복 방지
    already_rt = current_user and already_retweeted(pid, current_user["user_id"])
    rt_label = "✅ 리트윗됨" if already_rt else "🔁 리트윗"
    if col_rt.button(rt_label, key=f"rt_{pid}", disabled=already_rt):
        if current_user:
            # 리트윗은 원본 연결만 저장(내용은 비움)
            ok, msg = add_post(current_user["user_id"], content="", retweet_of_post_id=pid)
            if ok:
                st.success("리트윗 완료!")
                st.rerun()
            else:
                st.warning(msg)
        else:
            st.warning("로그인이 필요합니다.")

    # 디버깅/확인용 메타(운영 시 제거 가능)
    col_meta.caption(f"post_id: {pid}")


def show_feed(current_user: dict | None):
    """최신순 피드 렌더링.
    - 캐시에 존재하는 '_created_at_dt'가 있으면 그것으로 정렬(정확한 시간 비교)
    - 없으면 created_at 문자열 기준 정렬(백업)
    """
    st.subheader("📰 최신 피드")
    posts = load_posts()
    if posts.empty:
        st.info("아직 게시글이 없습니다. 첫 글을 작성해보세요!")
        return

    # 최신순 정렬
    if "_created_at_dt" in posts.columns:
        posts = posts.sort_values("_created_at_dt", ascending=False)
    else:
        posts = posts.sort_values("created_at", ascending=False)

    # 한 행씩 카드 렌더링
    for _, row in posts.iterrows():
        render_post_card(row.to_dict(), current_user)


def sidebar(current_user: dict | None):
    """사이드바: 데이터 새로고침 / 로그인 상태 표기 / 로그아웃 처리"""
    with st.sidebar:
        st.header("⚙️ 설정")

        # 단순 새로고침: 서버 상태 재평가를 유도
        if st.button("📁 데이터 새로고침", key="sidebar_refresh"):
            st.rerun()

        # 로그인 상태 표시 및 로그아웃
        if current_user:
            st.success(f"로그인: {current_user['username']}")
            if st.button("로그아웃", key="btn_logout"):
                st.session_state.pop("user", None)
                st.rerun()


# ======================================================================
# 메인 진입점
# ======================================================================

def main():
    """앱 엔트리 포인트.
    - 페이지 설정 → 데이터 파일 보장 → 세션 사용자 확인 → UI 분기
    """
    st.set_page_config(page_title=APP_TITLE, page_icon="🗨️", layout="centered")
    st.title("🗨️ My Social Feed")
    st.caption("테스트용 유사 SNS")

    # 필수 CSV 파일 생성 보장
    bootstrap_data_files()

    # 세션에서 로그인 사용자 조회
    current_user = st.session_state.get("user")

    # 사이드바 먼저 렌더링(새로고침/로그아웃 등)
    sidebar(current_user)

    # 본문: 로그인 여부에 따라 분기
    if not current_user:
        show_login_box()
        st.divider()
        st.info("로그인 후 피드를 이용할 수 있어요.")
    else:
        show_compose_box(current_user)
        show_feed(current_user)


if __name__ == "__main__":
    main()