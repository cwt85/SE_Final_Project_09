# course_schedule/routes.py
# 模組③：課程排課
# 網址都以 /schedule 開頭。整個模組都要登入。
from fastapi import APIRouter, Depends, Request

from common.auth import ROLE_ADMIN, AdminUser, LoginUser, require_login
from common.db import DB
from common.templating import render

# dependencies=[...] 會套用到這個 router 底下的「所有」網址：沒登入一律導向登入頁
router = APIRouter(prefix="/schedule", tags=["③ 課程排課"], dependencies=[Depends(require_login)])


@router.get("")
async def course_list(request: Request, user: LoginUser, db: DB):
	"""課程清單：老師看到自己的課，管理員看到全部。"""
	is_admin = user["role"] == ROLE_ADMIN
	cur = await db.execute(
		"""SELECT c.id, c.course_code, c.name, u.full_name AS teacher_name,
		          count(s.id) AS session_count,          -- 共幾個上課時段
		          min(s.session_date) AS first_date,
		          max(s.session_date) AS last_date
		   FROM courses c
		   JOIN users u ON u.id = c.teacher_id
		   LEFT JOIN course_sessions s ON s.course_id = c.id
		   WHERE %(is_admin)s OR c.teacher_id = %(uid)s   -- 管理員看全部，老師只看自己的
		   GROUP BY c.id, u.full_name
		   ORDER BY c.course_code""",
		{"is_admin": is_admin, "uid": user["id"]},
	)
	return render(request, "course_schedule/index.html", courses=await cur.fetchall(), is_admin=is_admin)


@router.get("/calendar")
async def calendar(request: Request):
	"""週曆：檢視所有目前排課的狀態。"""
	# TODO: 週曆顯示；管理員可以 drag & drop 修改日期時間
	return render(request, "course_schedule/calendar.html")


@router.get("/conflicts")
async def conflicts(request: Request, user: AdminUser):
	"""管理員：時間衝突的課程清單。"""
	# TODO: 查詢 SQL 見 docs/database.md 第 5.3 節
	return render(request, "course_schedule/conflicts.html")
