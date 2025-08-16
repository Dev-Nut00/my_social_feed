# 🧵 My Social Feed (plaintext password version)

**주의:** 학습/로컬용으로만 사용하세요. 비밀번호는 `users.csv`의 `user_password`에 **평문**으로 저장됩니다.

## USERS_CSV 스키마
```
["user_id", "user_password", "username", "username_lc", "created_at"]
```

## 실행
```bash
pip install -r requirements.txt
streamlit run app.py
```
