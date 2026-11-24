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
async def conflicts(request: Request, user: AdminUser, db: DB):
	"""管理員：時間衝突的課程清單。"""
	cur = await db.execute(
		"""SELECT a.id AS session_a, ca.name AS course_a,   -- 衝突場次A的ID和場次A所屬課程名稱
		          b.id AS session_b, cb.name AS course_b,   -- 衝突場次B的ID和場次B所屬課程名稱
		          a.session_date, r.room_code,   -- 課程日期（兩場次在同一天）和場次A的教室代碼
				  -- 優先判斷是否為相同教室；若非相同教室則視為同一位老師衝堂
		          CASE WHEN a.room_id = b.room_id THEN '教室衝突' ELSE '老師衝堂' END AS conflict_type
		   FROM course_sessions a
		   -- 自我連接（Self-Join）比對不同課程場次兩兩之間是否時間重疊
		   JOIN course_sessions b
		     ON a.id < b.id   -- 避免自己跟自己比對，並排除 (A, B) 與 (B, A) 重複配對
			 --若允許「前堂 10:00 結束、下堂 10:00 開始」緊鄰排課，使用嚴格小於（<）不會誤判為衝突
		    AND a.session_date = b.session_date   -- 僅比對同一天的課程
		    AND a.start_time < b.end_time   -- 區間重疊條件1：A 開始早於 B 結束
		    AND b.start_time < a.end_time   -- 區間重疊條件2：B 開始早於 A 結束
		   JOIN courses ca ON ca.id = a.course_id   -- 取得場次A的課程資訊（含授課老師)
		   JOIN courses cb ON cb.id = b.course_id   -- 取得場次B的課程資訊（含授課老師)
		   JOIN rooms r ON r.id = a.room_id   -- 取得場次A的教室資訊
		   -- 篩選出至少符合「同一間教室」或「同一位老師」其中一項的衝突組合
		   WHERE a.room_id = b.room_id
		      OR ca.teacher_id = cb.teacher_id
			-- 依課程日期與場次A的開始時間由早到晚排序
		   ORDER BY a.session_date, a.start_time"""   
	)
	return render(request, "course_schedule/conflicts.html", conflicts=await cur.fetchall())
