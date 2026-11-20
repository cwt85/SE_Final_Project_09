# common/auth.py
# 共用的登入／權限工具。三個模組都從這裡 import，不要各自實作登入檢查。
#
# 用法（在任何模組的 routes.py）：
#   from common.auth import LoginUser, TeacherUser, AdminUser
#   from common.db import DB
#
#   @router.get("/xxx")
#   async def page(request: Request, user: LoginUser, db: DB):     # 要登入
#   async def page(request: Request, user: TeacherUser, db: DB):   # 要是老師或管理員
#   async def page(request: Request, user: AdminUser, db: DB):     # 要是管理員
#
# user 是一個 dict：{"id": 1, "username": "admin", "full_name": "系統管理員", "role": "admin"}
from typing import Annotated

import bcrypt
from fastapi import Depends, HTTPException, Request

# 角色常數，避免各模組把字串打錯
ROLE_ADMIN = "admin"
ROLE_TEACHER = "teacher"
ROLE_USER = "user"

# 角色的中文名稱，給畫面顯示用
ROLE_LABELS = {ROLE_ADMIN: "管理員", ROLE_TEACHER: "老師", ROLE_USER: "一般使用者"}


# ---------- 密碼雜湊 ----------
def hash_password(password: str) -> str:
	"""把明碼轉成 bcrypt 雜湊（註冊時用）。每次產生的結果都不同，因為會加入隨機 salt。"""
	return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
	"""檢查明碼和資料庫裡的雜湊是否相符（登入時用）。"""
	try:
		return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
	except ValueError:
		# 資料庫裡的雜湊格式不正確（例如手動填了明碼），一律視為失敗
		return False


# ---------- Session ----------
def login_user(request: Request, user_row: dict) -> None:
	"""登入成功後，把使用者基本資料存進 session（cookie）。"""
	request.session["user"] = {
		"id": user_row["id"],
		"username": user_row["username"],
		"full_name": user_row["full_name"],
		"role": user_row["role"],
	}


def logout_user(request: Request) -> None:
	"""登出：只移除使用者資料，保留其他設定（例如本地／雲端模式）。"""
	request.session.pop("user", None)


def current_user(request: Request) -> dict | None:
	"""取得目前登入的使用者；沒登入回傳 None。不需要登入的頁面也可以用。"""
	return request.session.get("user")


# ---------- 權限檢查（給 Depends 使用） ----------
class LoginRequired(Exception):
	"""沒登入時丟出這個例外，main.py 會把它轉成「導向登入頁」。"""

	def __init__(self, next_url: str):
		self.next_url = next_url  # 登入完要回到哪一頁


def require_login(request: Request) -> dict:
	"""必須登入；沒登入就導向登入頁，登入後會自動回到原本那一頁。"""
	user = current_user(request)
	if user is None:
		next_url = request.url.path
		if request.url.query:
			next_url += "?" + request.url.query
		raise LoginRequired(next_url)
	return user


def require_role(*roles: str):
	"""必須是指定角色之一，否則回 403。例如 require_role("admin", "teacher")。"""

	def checker(user: dict = Depends(require_login)) -> dict:
		if user["role"] not in roles:
			raise HTTPException(status_code=403, detail="權限不足")
		return user

	return checker


# 常用的組合，直接拿來用
require_admin = require_role(ROLE_ADMIN)
require_teacher = require_role(ROLE_TEACHER, ROLE_ADMIN)  # 管理員也能做老師能做的事


# ===== 各模組請用這些型別宣告「需要什麼身分」 =====
#   async def page(request: Request, user: AdminUser, db: DB):
#
# 請把 user 寫在 db 前面：FastAPI 依參數順序執行，
# 這樣沒權限的請求會先被擋下，不會白白去連資料庫
LoginUser = Annotated[dict, Depends(require_login)]      # 任何已登入的人
TeacherUser = Annotated[dict, Depends(require_teacher)]  # 老師或管理員
AdminUser = Annotated[dict, Depends(require_admin)]      # 管理員
