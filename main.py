# main.py
# 程式進入點：把共用功能和三個模組組裝成一個網站。
# 啟動：uv run fastapi dev main.py  → 瀏覽器開 http://127.0.0.1:8000
#
# 這個檔案只負責「組裝」，功能請寫在各模組資料夾裡，
# 避免三個人同時改這個檔案造成 git 衝突。
from urllib.parse import quote

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from psycopg import OperationalError
from psycopg_pool import PoolTimeout
from starlette.middleware.sessions import SessionMiddleware

from common.auth import LoginRequired
from common.config import BASE_DIR, MODE_CLOUD, SESSION_SECRET
from common.db import get_mode, lifespan, reset_pool
from common.templating import render

# 各模組的 router
from common.routes import router as common_router
from space_query.routes import router as space_query_router
from space_booking.routes import router as space_booking_router
from course_schedule.routes import router as course_schedule_router

app = FastAPI(title="管院空間系統", lifespan=lifespan)

# ---------- Session：用簽章過的 cookie 記住「誰登入了」 ----------
app.add_middleware(
	SessionMiddleware,
	secret_key=SESSION_SECRET,
	max_age=8 * 60 * 60,   # 8 小時沒操作就要重新登入
	same_site="lax",       # 降低 CSRF（跨站偽造請求）風險
	https_only=False,      # 正式上線改用 HTTPS 時設成 True
)

# ---------- 掛上各模組的網址 ----------
app.include_router(common_router)            # /、/login、/register、/admin/users
app.include_router(space_query_router)       # /spaces...
app.include_router(space_booking_router)     # /booking...
app.include_router(course_schedule_router)   # /schedule...

# ---------- 靜態檔案（CSS、JS、圖片） ----------
# 每個模組的 static/ 對應到 /static/<模組名稱>/，例如
#   space_query/static/floorplans/1F.png → /static/space_query/floorplans/1F.png
for module in ("common", "space_query", "space_booking", "course_schedule"):
	static_dir = BASE_DIR / module / "static"
	if static_dir.is_dir():  # 模組有 static/ 資料夾才掛載
		app.mount(f"/static/{module}", StaticFiles(directory=static_dir), name=f"static_{module}")


# ---------- 錯誤處理 ----------
@app.exception_handler(LoginRequired)
async def handle_login_required(request: Request, exc: LoginRequired):
	"""沒登入 → 導向登入頁，並記住原本要去的頁面，登入後跳回來。"""
	return RedirectResponse(f"/login?next={quote(exc.next_url)}", status_code=303)


@app.exception_handler(PoolTimeout)        # 等不到可用連線（例如一開始就沒開 SSH 通道）
@app.exception_handler(OperationalError)   # 連線途中斷掉（例如使用中 SSH 通道被關掉）
async def handle_db_unavailable(request: Request, exc: Exception):
	"""連不上資料庫 → 顯示原因與解法，而不是一直轉圈或噴 500。"""
	mode = get_mode(request)
	# 換一個新的連線池，這樣資料庫恢復後重新整理就能馬上連上（原因見 common/db.py 的 reset_pool）
	await reset_pool(request.app, mode)
	if mode == MODE_CLOUD:
		message = ("連不上雲端資料庫。請確認 SSH 通道已開啟：ssh -N -L 5434:127.0.0.1:5432 <AWS 主機>，"
		           "或到登入頁切換回本地模式。")
	else:
		message = "連不上本地資料庫。請確認 Docker 已啟動：docker compose up -d"
	return render(request, "common/error.html", status_code=503, message=message)


@app.exception_handler(StarletteHTTPException)
async def handle_http_error(request: Request, exc: StarletteHTTPException):
	"""403、404 等錯誤顯示成友善的錯誤頁，而不是一串 JSON。"""
	messages = {403: "你沒有權限使用這個功能", 404: "找不到這個頁面"}
	# 自己寫的 detail（例如「找不到這個空間」）優先；否則用上面的預設訊息
	message = exc.detail if isinstance(exc.detail, str) and exc.detail not in ("Not Found", "Forbidden") \
		else messages.get(exc.status_code, "發生錯誤")
	return render(request, "common/error.html", status_code=exc.status_code,
	              message=message)
