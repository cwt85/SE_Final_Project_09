# common/routes.py
# 共用功能的網址：首頁、登入、登出、註冊、帳號審核
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from psycopg.errors import UniqueViolation

from common.auth import (
	ROLE_LABELS, hash_password, login_user, logout_user, require_admin, verify_password,
)
from common.db import getDB
from common.templating import render

router = APIRouter(tags=["共用"])


def safe_next(next_url: str | None) -> str:
	"""
	只允許跳回本站的相對路徑，避免「開放式重新導向」漏洞
	（例如有人做一個 /login?next=https://壞網站 的連結騙使用者點）。
	"""
	if next_url and next_url.startswith("/") and not next_url.startswith("//"):
		return next_url
	return "/"


# ---------- 首頁 ----------
@router.get("/")
async def home(request: Request):
	return render(request, "common/home.html")


# ---------- 登入／登出 ----------
@router.get("/login")
async def login_page(request: Request, next: str = "/", msg: str | None = None):
	return render(request, "common/login.html", next=next, msg=msg)


@router.post("/login")
async def login(
	request: Request,
	username: str = Form(...),
	password: str = Form(...),
	next: str = Form("/"),
	db=Depends(getDB),
):
	cur = await db.execute("SELECT * FROM users WHERE username = %s", (username.strip(),))
	row = await cur.fetchone()

	# 帳號不存在和密碼錯誤顯示同一個訊息，避免別人藉此猜出哪些帳號存在
	if row is None or not verify_password(password, row["password_hash"]):
		error = "帳號或密碼錯誤"
	elif row["status"] == "pending":
		error = "帳號尚在審核中，請等候管理員核准"
	elif row["status"] in ("rejected", "disabled"):
		error = "帳號已被退回或停用，請洽管理員"
	else:
		login_user(request, row)
		return RedirectResponse(safe_next(next), status_code=303)

	return render(request, "common/login.html", status_code=401,
	              next=next, error=error, username=username)


@router.get("/logout")
async def logout(request: Request):
	logout_user(request)
	return RedirectResponse("/", status_code=303)


# ---------- 註冊 ----------
@router.get("/register")
async def register_page(request: Request):
	return render(request, "common/register.html", form={})


@router.post("/register")
async def register(
	request: Request,
	username: str = Form(...),
	full_name: str = Form(...),
	email: str = Form(""),
	password: str = Form(...),
	password2: str = Form(...),
	db=Depends(getDB),
):
	form = {"username": username.strip(), "full_name": full_name.strip(), "email": email.strip()}

	# 基本檢查（瀏覽器端也有檢查，但後端一定要再檢查一次，因為瀏覽器端可以被繞過）
	error = None
	if not form["username"] or not form["full_name"]:
		error = "帳號和姓名不可空白"
	elif len(password) < 6:
		error = "密碼至少 6 個字元"
	elif password != password2:
		error = "兩次輸入的密碼不一致"

	if error is None:
		try:
			# 新帳號一律是一般使用者、待審核；角色由管理員在審核時調整
			await db.execute(
				"""INSERT INTO users (username, password_hash, full_name, email)
				   VALUES (%s, %s, %s, %s)""",
				(form["username"], hash_password(password), form["full_name"], form["email"] or None),
			)
		except UniqueViolation:
			error = "這個帳號已經有人使用"

	if error:
		return render(request, "common/register.html", status_code=400, form=form, error=error)
	return RedirectResponse("/login?msg=註冊成功，請等候管理員審核", status_code=303)


# ---------- 帳號審核（管理員） ----------
@router.get("/admin/users")
async def user_list(request: Request, user=Depends(require_admin), db=Depends(getDB)):
	# 待審核的排最前面，方便管理員處理
	cur = await db.execute(
		"""SELECT id, username, full_name, email, role, status, created_at
		   FROM users
		   ORDER BY (status = 'pending') DESC, id"""
	)
	return render(request, "common/users.html", users=await cur.fetchall())


@router.post("/admin/users/{user_id}/status")
async def set_user_status(
	user_id: int,
	status: str = Form(...),
	user=Depends(require_admin),
	db=Depends(getDB),
):
	# 只接受這幾種狀態（資料庫也有 CHECK 限制，這裡先擋可以給比較清楚的錯誤）
	if status not in ("active", "rejected", "disabled") or user_id == user["id"]:
		return RedirectResponse("/admin/users", status_code=303)  # 不能改自己的狀態
	await db.execute(
		"""UPDATE users SET status = %s, approved_by = %s, approved_at = now()
		   WHERE id = %s""",
		(status, user["id"], user_id),
	)
	return RedirectResponse("/admin/users", status_code=303)


@router.post("/admin/users/{user_id}/role")
async def set_user_role(
	user_id: int,
	role: str = Form(...),
	user=Depends(require_admin),
	db=Depends(getDB),
):
	if role in ROLE_LABELS and user_id != user["id"]:  # 不能改自己的角色，避免把自己降級鎖死
		await db.execute("UPDATE users SET role = %s WHERE id = %s", (role, user_id))
	return RedirectResponse("/admin/users", status_code=303)
