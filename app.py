import os
import io
import re
import zipfile
import uuid
from datetime import datetime
from pathlib import Path
from collections import Counter

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
COMMENTS_CSV = DATA_DIR / "comments.csv"
FOLLOWS_CSV = DATA_DIR / "follows.csv"
REPORTS_CSV = DATA_DIR / "reports.csv"

# ▶ 최신 스키마 (Stage2 반영)
USERS_COLUMNS = [
    "user_id", "user_password", "username", "username_lc",
    "created_at", "bio", "avatar_url", "is_admin"
]
POSTS_COLUMNS = ["post_id", "author_id", "content", "created_at", "is_retweet", "retweet_of_post_id"]
LIKES_COLUMNS = ["post_id", "user_id", "created_at"]
COMMENTS_COLUMNS = ["comment_id", "post_id", "author_id", "content", "created_at", "parent_comment_id"]
FOLLOWS_COLUMNS = ["follower_id", "followee_id", "created_at"]
REPORTS_COLUMNS = ["report_id", "target_type", "target_id", "reporter_id", "reason", "created_at", "resolved"]

PAGE_SIZE = 10  # 피드 페이지 크기
HASHTAG_RE = re.compile(r"#(\w+)")

# ======================================================================
# 데이터 유틸리티: CSV 파일 생성/로드/쓰기
# ======================================================================

def ensure_csv(path: Path, columns: list[str]) -> None:
    """지정한 경로에 CSV 파일이 없으면 '헤더만 있는 빈 파일'을 생성합니다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        df = pd.DataFrame(columns=columns)
        df.to_csv(path, index=False)

def upgrade_csv_schema(path: Path, required_cols: list[str]) -> None:
    """기존 CSV에 필요한 컬럼이 없으면 추가하고, 컬럼 순서를 정리합니다."""
    if not path.exists():
        return
    df = pd.read_csv(path, dtype=str)
    changed = False

    # 누락 컬럼 생성
    for col in required_cols:
        if col not in df.columns:
            df[col] = ""
            changed = True

    # 컬럼 순서 정렬: required 먼저, 나머지 뒤
    ordered = required_cols + [c for c in df.columns if c not in required_cols]
    if list(df.columns) != ordered:
        df = df[ordered]
        changed = True

    if changed:
        df = df.fillna("")
        df.to_csv(path, index=False)

def bootstrap_data_files() -> None:
    """앱 시작 시 필요한 CSV들 생성/스키마 업그레이드."""
    ensure_csv(USERS_CSV, USERS_COLUMNS)
    ensure_csv(POSTS_CSV, POSTS_COLUMNS)
    ensure_csv(LIKES_CSV, LIKES_COLUMNS)
    ensure_csv(COMMENTS_CSV, COMMENTS_COLUMNS)
    ensure_csv(FOLLOWS_CSV, FOLLOWS_COLUMNS)
    ensure_csv(REPORTS_CSV, REPORTS_COLUMNS)

    upgrade_csv_schema(USERS_CSV, USERS_COLUMNS)
    upgrade_csv_schema(POSTS_CSV, POSTS_COLUMNS)
    upgrade_csv_schema(LIKES_CSV, LIKES_COLUMNS)
    upgrade_csv_schema(COMMENTS_CSV, COMMENTS_COLUMNS)
    upgrade_csv_schema(FOLLOWS_CSV, FOLLOWS_COLUMNS)
    upgrade_csv_schema(REPORTS_CSV, REPORTS_COLUMNS)

@st.cache_data(show_spinner=False)
def load_users() -> pd.DataFrame:
    return pd.read_csv(USERS_CSV, dtype=str).fillna("")

@st.cache_data(show_spinner=False)
def load_posts() -> pd.DataFrame:
    df = pd.read_csv(POSTS_CSV, dtype=str).fillna("")
    if not df.empty:
        df["_created_at_dt"] = pd.to_datetime(df["created_at"], errors="coerce")
    return df

@st.cache_data(show_spinner=False)
def load_likes() -> pd.DataFrame:
    return pd.read_csv(LIKES_CSV, dtype=str).fillna("")

@st.cache_data(show_spinner=False)
def load_comments() -> pd.DataFrame:
    return pd.read_csv(COMMENTS_CSV, dtype=str).fillna("")

@st.cache_data(show_spinner=False)
def load_follows() -> pd.DataFrame:
    return pd.read_csv(FOLLOWS_CSV, dtype=str).fillna("")

@st.cache_data(show_spinner=False)
def load_reports() -> pd.DataFrame:
    return pd.read_csv(REPORTS_CSV, dtype=str).fillna("")

def clear_data_caches():
    """캐시된 users/posts/likes/comments/follows/reports 데이터를 무효화합니다."""
    load_users.clear()
    load_posts.clear()
    load_likes.clear()
    load_comments.clear()
    load_follows.clear()
    load_reports.clear()

def now_iso() -> str:
    """현재 시간을 ISO8601(초 단위) 문자열로 반환합니다."""
    return datetime.now().isoformat(timespec="seconds")

def append_row(path: Path, row: dict, columns: list[str]) -> None:
    """CSV 파일에 한 행을 '안전하게' 추가합니다."""
    df = pd.DataFrame([row], columns=columns)
    df.to_csv(
        path,
        mode="a",
        header=not path.exists() or os.path.getsize(path) == 0,
        index=False,
    )

def overwrite_df(path: Path, df: pd.DataFrame) -> None:
    """CSV 파일 전체를 덮어씁니다."""
    df.to_csv(path, index=False)

# ======================================================================
# 도메인 로직: 사용자/게시글/좋아요/리트윗/댓글/팔로우/신고
# ======================================================================

def username_exists(username: str) -> bool:
    users = load_users()
    return not users[users["username_lc"] == username.lower()].empty

def create_user(username: str, password: str) -> tuple[bool, str]:
    """회원가입 처리"""
    if not username.strip():
        return False, "사용자명을 입력해주세요."
    if not password.strip():
        return False, "비밀번호를 입력해주세요."
    if username_exists(username):
        return False, "이미 존재하는 사용자명입니다."
    user = {
        "user_id": uuid.uuid4().hex,
        "user_password": password,   
        "username": username,
        "username_lc": username.lower(),
        "created_at": now_iso(),
        "bio": "",
        "avatar_url": "",
        "is_admin": "False",
    }
    append_row(USERS_CSV, user, USERS_COLUMNS)
    clear_data_caches()
    return True, "회원가입이 완료되었습니다. 로그인해주세요."

def verify_login(username: str, password: str):
    users = load_users()
    mask = (users["username_lc"] == username.lower()) & (users["user_password"] == password)
    row = users[mask]
    if row.empty:
        return None
    return row.iloc[0].to_dict()

def add_post(author_id: str, content: str, retweet_of_post_id: str | None = None) -> tuple[bool, str]:
    content = (content or "").strip()
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
    likes = load_likes()
    return not likes[(likes["post_id"] == post_id) & (likes["user_id"] == user_id)].empty

def toggle_like(post_id: str, user_id: str) -> None:
    likes = load_likes()
    mask = (likes["post_id"] == post_id) & (likes["user_id"] == user_id)
    if mask.any():
        likes = likes[~mask]
        overwrite_df(LIKES_CSV, likes)
    else:
        new_row = {"post_id": post_id, "user_id": user_id, "created_at": now_iso()}
        append_row(LIKES_CSV, new_row, LIKES_COLUMNS)
    clear_data_caches()

def already_retweeted(target_post_id: str, user_id: str) -> bool:
    posts = load_posts()
    if posts.empty:
        return False
    mask = (
        (posts["author_id"] == user_id)
        & (posts["is_retweet"] == "True")
        & (posts["retweet_of_post_id"] == target_post_id)
    )
    return posts[mask].shape[0] > 0

# --------------------------
# 댓글
# --------------------------
def add_comment(post_id: str, author_id: str, content: str, parent_comment_id: str = "") -> tuple[bool, str]:
    content = (content or "").strip()
    if not content:
        return False, "댓글 내용을 입력해주세요."
    if len(content) > 280:
        return False, "댓글은 최대 280자까지 가능합니다."
    row = {
        "comment_id": uuid.uuid4().hex,
        "post_id": post_id,
        "author_id": author_id,
        "content": content,
        "created_at": now_iso(),
        "parent_comment_id": parent_comment_id or "",
    }
    append_row(COMMENTS_CSV, row, COMMENTS_COLUMNS)
    clear_data_caches()
    return True, "댓글이 등록되었습니다."

def comments_by_post(post_id: str) -> pd.DataFrame:
    df = load_comments()
    return df[df["post_id"] == post_id].sort_values("created_at")

# --------------------------
# 팔로우
# --------------------------
def is_following(follower_id: str, followee_id: str) -> bool:
    if follower_id == followee_id:
        return True
    f = load_follows()
    return not f[(f["follower_id"] == follower_id) & (f["followee_id"] == followee_id)].empty

def toggle_follow(follower_id: str, followee_id: str) -> None:
    if follower_id == followee_id:
        return
    f = load_follows()
    mask = (f["follower_id"] == follower_id) & (f["followee_id"] == followee_id)
    if mask.any():
        f = f[~mask]
        overwrite_df(FOLLOWS_CSV, f)
    else:
        row = {"follower_id": follower_id, "followee_id": followee_id, "created_at": now_iso()}
        append_row(FOLLOWS_CSV, row, FOLLOWS_COLUMNS)
    clear_data_caches()

def followee_ids(user_id: str) -> list[str]:
    f = load_follows()
    rows = f[f["follower_id"] == user_id]
    ids = set(rows["followee_id"].tolist())
    ids.add(user_id)  # 자기 글은 항상 보이도록
    return list(ids)

# --------------------------
# 프로필
# --------------------------
def update_profile(user_id: str, bio: str, avatar_url: str) -> None:
    users = load_users()
    mask = (users["user_id"] == user_id)
    if not mask.any():
        return
    users.loc[mask, "bio"] = str(bio or "")
    users.loc[mask, "avatar_url"] = str(avatar_url or "")
    overwrite_df(USERS_CSV, users)
    clear_data_caches()

def is_admin(user: dict | None) -> bool:
    if not user:
        return False
    return str(user.get("is_admin", "")).lower() == "true"

# --------------------------
# 신고/모더레이션
# --------------------------
def add_report(target_type: str, target_id: str, reporter_id: str, reason: str) -> tuple[bool, str]:
    target_type = (target_type or "").lower()
    if target_type not in ("post", "comment"):
        return False, "잘못된 대상 유형입니다."
    reason = (reason or "").strip()
    if not reason:
        return False, "신고 사유를 입력해주세요."
    row = {
        "report_id": uuid.uuid4().hex,
        "target_type": target_type,
        "target_id": target_id,
        "reporter_id": reporter_id,
        "reason": reason,
        "created_at": now_iso(),
        "resolved": "False",
    }
    append_row(REPORTS_CSV, row, REPORTS_COLUMNS)
    clear_data_caches()
    return True, "신고가 접수되었습니다."

def list_reports(only_open: bool = True) -> pd.DataFrame:
    r = load_reports()
    if only_open:
        r = r[r["resolved"].str.lower() != "true"]
    return r.sort_values("created_at", ascending=False)

def resolve_report(report_id: str) -> None:
    r = load_reports()
    mask = (r["report_id"] == report_id)
    if mask.any():
        r.loc[mask, "resolved"] = "True"
        overwrite_df(REPORTS_CSV, r)
        clear_data_caches()

def delete_post(post_id: str) -> None:
    posts = load_posts()
    posts = posts[posts["post_id"] != post_id]
    overwrite_df(POSTS_CSV, posts)

    likes = load_likes()
    likes = likes[likes["post_id"] != post_id]
    overwrite_df(LIKES_CSV, likes)

    if COMMENTS_CSV.exists():
        cdf = pd.read_csv(COMMENTS_CSV, dtype=str).fillna("")
        cdf = cdf[cdf["post_id"] != post_id]
        cdf.to_csv(COMMENTS_CSV, index=False)

    clear_data_caches()

def delete_comment(comment_id: str) -> None:
    if not COMMENTS_CSV.exists():
        return
    cdf = pd.read_csv(COMMENTS_CSV, dtype=str).fillna("")
    cdf = cdf[cdf["comment_id"] != comment_id]
    cdf.to_csv(COMMENTS_CSV, index=False)
    clear_data_caches()

# --------------------------
# 해시태그/검색
# --------------------------
def extract_hashtags(text: str) -> list[str]:
    if not text:
        return []
    return [m.lower() for m in HASHTAG_RE.findall(text)]

def filter_posts_by_query(df_posts: pd.DataFrame, query: str) -> pd.DataFrame:
    """쿼리 규칙:
       - 빈 문자열/None: 필터 없음
       - '@이름' : 해당 사용자 글
       - '#태그' : 해당 해시태그 포함 글
       - 그 외    : 내용 부분 문자열 검색(대소문자 무시)
    """
    if not query:
        return df_posts
    q = query.strip()
    posts = df_posts.copy()
    users = load_users()

    # 작성자(@username)
    if q.startswith("@"):
        uname = q[1:].lower()
        author_ids = users[users["username_lc"] == uname]["user_id"].tolist()
        return posts[posts["author_id"].isin(author_ids)]

    # 해시태그(#tag)
    if q.startswith("#"):
        tag = q[1:].lower()
        mask = posts["content"].fillna("").apply(lambda t: tag in extract_hashtags(t))
        return posts[mask]

    # 일반 텍스트 검색
    ql = q.lower()
    return posts[posts["content"].fillna("").str.lower().str.contains(ql, na=False)]

def trending_hashtags(df_posts: pd.DataFrame, topk: int = 10) -> list[tuple[str, int]]:
    tags = []
    for _, r in df_posts.iterrows():
        tags.extend(extract_hashtags(r.get("content", "")))
    cnt = Counter(tags)
    return cnt.most_common(topk)

# ======================================================================
# UI 컴포넌트
# ======================================================================

def show_login_box():
    """로그인/회원가입 UI"""
    st.subheader("🔐 로그인 / 회원가입")
    tabs = st.tabs(["로그인", "회원가입"])

    with tabs[0]:
        with st.form("login_form", clear_on_submit=False):
            username = st.text_input("사용자명", key="login_username")
            password = st.text_input("비밀번호", type="password", key="login_password")
            submitted = st.form_submit_button("로그인", use_container_width=True)
        if submitted:
            user = verify_login(username, password)
            if user:
                st.session_state["user"] = user
                st.success(f"환영합니다, {user['username']}님!")
                st.rerun()
            else:
                st.error("사용자명 또는 비밀번호가 올바르지 않습니다.")

    with tabs[1]:
        with st.form("signup_form", clear_on_submit=True):
            new_username = st.text_input("사용자명", key="signup_username")
            new_password = st.text_input("비밀번호", type="password", key="signup_password")
            submitted = st.form_submit_button("회원가입", use_container_width=True)
        if submitted:
            ok, msg = create_user(new_username, new_password)
            if ok:
                st.success(msg)
            else:
                st.error(msg)

def user_by_id(user_id: str) -> str:
    """user_id로 표시 이름 반환"""
    users = load_users()
    row = users[users["user_id"] == user_id]
    if row.empty:
        return "알수없음"
    return str(row.iloc[0]["username"])

def post_by_id(post_id: str) -> dict | None:
    posts = load_posts()
    row = posts[posts["post_id"] == post_id]
    if row.empty:
        return None
    return row.iloc[0].to_dict()

def like_count(post_id: str) -> int:
    likes = load_likes()
    return int(likes[likes["post_id"] == post_id].shape[0])

def show_compose_box(current_user: dict):
    """글 작성 폼 (SessionState 충돌 방지)"""
    st.subheader("📝 새 글 작성")

    # 기본값을 별도 세션 키에서 관리 (위젯 키 직접 변경 금지)
    if "compose_default" not in st.session_state:
        st.session_state["compose_default"] = ""

    content = st.text_area(
        "무슨 일이 일어나고 있나요?",
        key="compose_content",
        height=120,
        max_chars=280,
        value=st.session_state["compose_default"],
        placeholder="최대 280자",
    )

    cols = st.columns([1, 1, 6])
    if cols[0].button("게시", key="btn_post"):
        ok, msg = add_post(current_user["user_id"], content)
        if ok:
            st.success(msg)
            st.session_state["compose_default"] = ""  # 다음 렌더에서 초기화
            st.rerun()
        else:
            st.warning(msg)

    cols[1].button("피드 새로고침", key="btn_refresh", on_click=lambda: st.rerun())

def render_post_card(post: dict, current_user: dict | None):
    """피드의 게시글 카드 렌더링"""
    author_name = user_by_id(post["author_id"])
    created_at = post.get("created_at", "")

    is_rt = (post.get("is_retweet") == "True")
    rt_src_id = post.get("retweet_of_post_id") or ""

    st.markdown("---")
    if is_rt:
        # 리트윗 표시 + 원본 인용
        st.markdown(f"🔁 **{author_name}** 님이 리트윗했습니다 · {created_at}")
        src = post_by_id(rt_src_id)
        if src is None:
            st.markdown("> [원본 게시글이 삭제되었습니다]")
        else:
            src_author = user_by_id(src["author_id"])
            st.markdown(
                f"> **@{src_author}**: {src['content']}  \n> _{src.get('created_at','')}_"
            )
    else:
        st.markdown(f"**{author_name}** · {created_at}")
        st.write(post["content"])

    # --- 팔로우/언팔로우 (작성자 우측) ---
    if current_user and current_user["user_id"] != post["author_id"]:
        fcol1, fcol2, _ = st.columns([1,1,6])
        followed = is_following(current_user["user_id"], post["author_id"])
        flabel = "언팔로우" if followed else "팔로우"
        if fcol1.button(flabel, key=f"follow_{post['post_id']}"):
            toggle_follow(current_user["user_id"], post["author_id"])
            st.rerun()

    # --- 신고/삭제 ---
    ctrl_cols = st.columns([1,1,6])
    if current_user:
        with ctrl_cols[0].popover("신고", use_container_width=True):
            reason = st.text_input("사유", key=f"rp_{post['post_id']}")
            if st.button("신고 접수", key=f"rp_btn_{post['post_id']}"):
                ok, msg = add_report("post", post["post_id"], current_user["user_id"], reason)
                if ok:
                    st.success(msg); st.rerun()
                else:
                    st.warning(msg)

    if current_user and (current_user["user_id"] == post["author_id"] or is_admin(current_user)):
        if ctrl_cols[1].button("삭제", key=f"del_{post['post_id']}"):
            delete_post(post["post_id"])
            st.success("게시글이 삭제되었습니다.")
            st.rerun()

    # 하단 인터랙션(좋아요/리트윗)
    pid = post["post_id"]
    lc = like_count(pid)
    liked = bool(current_user and has_liked(pid, current_user["user_id"]))
    col_like, col_rt, col_meta = st.columns([1, 1, 6])

    like_label = f"{'❤️' if liked else '🤍'} 좋아요 ({lc})"
    if col_like.button(like_label, key=f"like_{pid}"):
        if current_user:
            toggle_like(pid, current_user["user_id"])
            st.rerun()
        else:
            st.warning("로그인이 필요합니다.")

    already_rt = bool(current_user and already_retweeted(pid, current_user["user_id"]))
    rt_label = "✅ 리트윗됨" if already_rt else "🔁 리트윗"
    if col_rt.button(rt_label, key=f"rt_{pid}", disabled=already_rt):
        if current_user:
            ok, msg = add_post(current_user["user_id"], content="", retweet_of_post_id=pid)
            if ok:
                st.success("리트윗 완료!"); st.rerun()
            else:
                st.warning(msg)
        else:
            st.warning("로그인이 필요합니다.")

    col_meta.caption(f"post_id: {pid}")

    # ----- 댓글 영역 -----
    with st.expander("💬 댓글 보기 / 쓰기", expanded=False):
        cdf = comments_by_post(pid)
        if cdf.empty:
            st.caption("아직 댓글이 없습니다.")
        else:
            for _, cr in cdf.iterrows():
                cauthor = user_by_id(cr["author_id"])
                st.markdown(f"- **{cauthor}** · _{cr['created_at']}_  \n{cr['content']}")

        if current_user:
            ckey_in = f"cmt_input_{pid}"
            ckey_btn = f"cmt_btn_{pid}"
            ccontent = st.text_input("댓글 작성", key=ckey_in, max_chars=280, placeholder="댓글을 입력하세요")
            if st.button("등록", key=ckey_btn):
                ok, msg = add_comment(pid, current_user["user_id"], ccontent)
                if ok:
                    st.success(msg); st.rerun()
                else:
                    st.warning(msg)
        else:
            st.caption("댓글 작성은 로그인 후 이용할 수 있습니다.")

def show_feed(current_user: dict | None, query: str = "", page: int = 0):
    """최신순 피드 + 검색/해시태그 필터 + 페이지네이션 + 팔로잉 모드"""
    st.subheader("📰 최신 피드")
    posts = load_posts()
    if posts.empty:
        st.info("아직 게시글이 없습니다. 첫 글을 작성해보세요!")
        return

    # 최신순
    if "_created_at_dt" in posts.columns:
        posts = posts.sort_values("_created_at_dt", ascending=False)
    else:
        posts = posts.sort_values("created_at", ascending=False)

    # 팔로잉 모드
    mode = st.session_state.get("feed_mode", "전체")
    if mode == "팔로잉" and current_user:
        ids = set(followee_ids(current_user["user_id"]))
        posts = posts[posts["author_id"].isin(ids)]

    # 검색/필터
    posts = filter_posts_by_query(posts, query)

    total = posts.shape[0]
    start = page * PAGE_SIZE
    end = start + PAGE_SIZE
    page_posts = posts.iloc[start:end]

    if total == 0:
        st.info("조건에 맞는 게시글이 없습니다.")
        return

    st.caption(f"총 {total}개 중 {start+1}–{min(end, total)} 표시")

    for _, row in page_posts.iterrows():
        render_post_card(row.to_dict(), current_user)

    nav_cols = st.columns([1,1,6])
    if nav_cols[0].button("⬅ 이전", disabled=(start <= 0), key=f"prev_{page}_{query}_{mode}"):
        st.session_state["page"] = max(0, page - 1); st.rerun()
    if nav_cols[1].button("다음 ➡", disabled=(end >= total), key=f"next_{page}_{query}_{mode}"):
        st.session_state["page"] = page + 1; st.rerun()

def sidebar(current_user: dict | None):
    """사이드바: 검색/모드/트렌딩/프로필/모더레이션"""
    with st.sidebar:
        st.header("⚙️ 설정")

        # 검색어
        q = st.text_input("검색 (@사용자, #태그, 텍스트)", key="query", placeholder="예: #python, @alice, 데이터")
        if "page" not in st.session_state:
            st.session_state["page"] = 0
        if st.session_state.get("last_query") != q:
            st.session_state["page"] = 0
            st.session_state["last_query"] = q

        # 피드 모드
        mode = st.radio("피드 모드", ["전체", "팔로잉"], key="feed_mode", horizontal=True)

        # 트렌딩 해시태그
        posts_all = load_posts()
        tags = trending_hashtags(posts_all, topk=10) if not posts_all.empty else []
        if tags:
            st.markdown("**📈 트렌딩 해시태그**")
            for tag, cnt in tags:
                if st.button(f"#{tag} ({cnt})", key=f"tagbtn_{tag}"):
                    st.session_state["query"] = f"#{tag}"
                    st.session_state["page"] = 0
                    st.rerun()

        # 프로필
        st.markdown("---")
        st.subheader("👤 프로필")
        if current_user:
            users = load_users()
            me = users[users["user_id"] == current_user["user_id"]].iloc[0].to_dict()
            with st.form("profile_form", clear_on_submit=False):
                st.text(f"아이디: @{me['username']}")
                bio = st.text_area("소개", value=me.get("bio",""), height=80, key="profile_bio")
                avatar_url = st.text_input("아바타 URL", value=me.get("avatar_url",""), key="profile_avatar")
                if st.form_submit_button("저장", use_container_width=True):
                    update_profile(current_user["user_id"], bio, avatar_url)
                    st.success("프로필이 저장되었습니다.")
                    st.rerun()
        else:
            st.info("로그인 후 프로필을 설정할 수 있습니다.")


        # 새로고침/로그인/로그아웃
        st.markdown("---")
        if st.button("📁 데이터 새로고침", key="sidebar_refresh"):
            st.rerun()
        if current_user:
            st.success(f"로그인: {current_user['username']}")
            if st.button("로그아웃", key="btn_logout"):
                st.session_state.pop("user", None)
                st.rerun()

        # 모더레이션(관리자)
        if is_admin(current_user):
            st.markdown("---")
            st.subheader("🛡️ 신고 관리 (관리자)")
            reports = list_reports(only_open=True)
            if reports.empty:
                st.caption("열린 신고가 없습니다.")
            else:
                for _, r in reports.iterrows():
                    st.markdown(
                        f"- **{r['target_type']}** · 대상: `{r['target_id']}` · "
                        f"신고자: `{user_by_id(r['reporter_id'])}` · 사유: {r['reason']} · {r['created_at']}"
                    )
                    cols = st.columns([1,1,2,4])
                    if r["target_type"] == "post":
                        if cols[0].button("게시글 삭제", key=f"mod_del_post_{r['report_id']}"):
                            delete_post(r["target_id"])
                            resolve_report(r["report_id"])
                            st.success("삭제 및 신고 처리"); st.rerun()
                    elif r["target_type"] == "comment":
                        if cols[0].button("댓글 삭제", key=f"mod_del_cmt_{r['report_id']}"):
                            delete_comment(r["target_id"])
                            resolve_report(r["report_id"])
                            st.success("삭제 및 신고 처리"); st.rerun()
                    if cols[1].button("신고만 처리", key=f"mod_resolve_{r['report_id']}"):
                        resolve_report(r["report_id"])
                        st.info("신고를 처리했습니다."); st.rerun()

# ======================================================================
# 메인
# ======================================================================

def main():
    """앱 엔트리 포인트"""
    st.set_page_config(page_title=APP_TITLE, page_icon="🗨️", layout="centered")
    st.title("🗨️ with us")
    st.caption("SNS형식의 대회/스터디 구인서비스")

    bootstrap_data_files()

    current_user = st.session_state.get("user")
    sidebar(current_user)

    # 본문 분기
    if not current_user:
        show_login_box()
        st.divider()
        st.info("로그인 후 피드를 이용할 수 있어요.")
    else:
        show_compose_box(current_user)

    # 피드 (로그인 여부 무관)
    page = int(st.session_state.get("page", 0))
    query = st.session_state.get("query", "")
    show_feed(current_user, query=query, page=page)

if __name__ == "__main__":
    main()