# 🧵 My Social Feed (Streamlit + CSV)

간단한 텍스트 기반 소셜 피드 앱입니다. 로그인(닉네임), 글 작성/보기, 좋아요, 리트윗 기능을 지원하며 모든 데이터는 CSV 파일로 저장됩니다.

## 🚀 실행 방법 (로컬)

```bash
git clone <your-repo-url>
cd <repo>
pip install -r requirements.txt
streamlit run app.py
```

## 🗂 데이터 구조 (CSV)

- `data/users.csv`: `user_id, username, username_lc, created_at`
- `data/posts.csv`: `post_id, user_id, content, created_at, retweet_of`
- `data/likes.csv`: `post_id, user_id, created_at`

## 🧩 기능

- 로그인/회원가입(닉네임 기반)
- 글 작성 (최대 280자)
- 메인 피드 (최신 순)
- 좋아요(토글)
- 리트윗(중복 방지, 자기 글 리트윗 불가)

## ☁️ Streamlit Cloud 배포

1. GitHub에 업로드
2. Streamlit Cloud에서 새 앱 생성 → `app.py` 지정
3. Python 버전은 기본(3.11) 그대로 사용
4. `requirements.txt` 포함 여부 확인

## ⚠️ 주의사항

- 동시다발적인 다중 사용자 쓰기 상황에서 CSV는 충돌이 날 수 있습니다. 본 미니 프로젝트에서는 단일 인스턴스/학습용 사용을 가정합니다.
- 버튼 키는 `post_id` 기반으로 고유하게 부여하여 DuplicateWidgetID 문제를 피했습니다.
- 파일 쓰기는 임시 파일로 저장 후 `os.replace`로 원자적 치환을 수행합니다.
"# my_social_feed" 
