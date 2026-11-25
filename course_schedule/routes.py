# course_schedule/routes.py
# 模組③：課程排課
# 網址都以 /schedule 開頭。整個模組都要登入。
#date/time用來解析表單的日期與時間；timedelta用來「每次加7天」展開每週時段
from datetime import date, time, timedelta 

#Form（讀表單欄位)、HTTPException（丟出403/404）
from fastapi import APIRouter, Depends, Form, HTTPException, Request
#表單送出後導回列表頁（用303，避免使用者按F5重複送出）
from fastapi.responses import RedirectResponse

from common.auth import ROLE_ADMIN, AdminUser, LoginUser, require_login
from common.db import DB
#使用common提供的衝突檢查函式
from common.occupancy import find_conflicts
from common.templating import render

# dependencies=[...]會套用到這個router底下的「所有」網址：沒登入一律導向登入頁
router = APIRouter(prefix="/schedule", tags=["③ 課程排課"], dependencies=[Depends(require_login)])

@router.get("")
#多一個warn參數，接收網址的?warn=N（代表有幾個時段發生衝突）
async def course_list(request: Request, user: LoginUser, db: DB, warn: int = 0):
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
	#多傳warn給模板，index.html才能顯示衝突警告
	return render(request, "course_schedule/index.html",
	              courses=await cur.fetchall(), is_admin=is_admin, warn=warn)


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

async def _form_options(db):
	"""表單的下拉選單資料：所有教室、所有老師。"""
	cur = await db.execute("SELECT id, room_code FROM rooms ORDER BY room_code")
	rooms = await cur.fetchall()
	#'teacher' 要和 users.role 實際的值一致，不一樣就改這裡
	cur = await db.execute("SELECT id, full_name FROM users WHERE role = 'teacher' ORDER BY full_name")
	teachers = await cur.fetchall()
	return rooms, teachers


async def _get_course_or_403(db, course_id: int, user):
	"""取得課程並做權限檢查（編輯、刪除都會用）。
	找不到 → 404；不是管理員且不是自己的課 → 403。
	權限檢查寫在後端，就算有人手動輸入網址也擋得住。"""
	cur = await db.execute("SELECT id, course_code, name, teacher_id FROM courses WHERE id = %s", (course_id,))
	course = await cur.fetchone()
	if course is None:
		raise HTTPException(status_code=404, detail="找不到這門課程")
	if user["role"] != ROLE_ADMIN and course["teacher_id"] != user["id"]:
		raise HTTPException(status_code=403)
	return course


def _parse_form(course_code, name, room_id, start_date, weeks, start_time, end_time):
	"""把表單字串轉成 date / time 物件，並檢查內容。"""
	try:
		d1 = date.fromisoformat(start_date)
		t1, t2 = time.fromisoformat(start_time), time.fromisoformat(end_time)
	except ValueError:
		return None, "日期或時間格式不正確"
	if not name.strip():
		return None, "請填寫課名"
	if not 1 <= weeks <= 30:
		return None, "重複週數請填 1～30"
	if t2 <= t1:
		return None, "結束時間必須晚於開始時間"
	d2 = d1 + timedelta(weeks=weeks - 1)   # 最後一週的日期，_create_sessions 會用到
	return {"code": course_code.strip() or None, "name": name.strip(), "room_id": room_id,
	        "d1": d1, "d2": d2, "t1": t1, "t2": t2}, None


async def _create_sessions(db, course_id: int, f: dict) -> int:
	"""依開始、結束日期展開上課時段：從開始日期起每隔 7 天建立一筆。
	每建一筆就用 find_conflicts 檢查，有衝突只計數，不阻擋（排課允許衝突）。
	回傳「有衝突的時段數」，用來顯示警告。"""
	warn = 0
	day = f["d1"]
	while day <= f["d2"]:
		cur = await db.execute(
			"""INSERT INTO course_sessions (course_id, room_id, session_date, start_time, end_time)
			   VALUES (%s, %s, %s, %s, %s) RETURNING id""",
			(course_id, f["room_id"], day, f["t1"], f["t2"]),
		)
		session_id = (await cur.fetchone())["id"]
		# exclude_* 排除剛建立的自己，否則一定會跟自己衝突
		found = await find_conflicts(db, f["room_id"], day, f["t1"], f["t2"],
		                             exclude_source="course", exclude_id=session_id)
		if found:
			warn += 1
		day += timedelta(days=7)
	return warn

#新增課程
@router.get("/new")   # 一定要放在 /{course_id}/edit 之前，否則 "new" 會被當成 course_id
async def course_new_form(request: Request, user: LoginUser, db: DB):
	"""顯示空白的新增表單。"""
	rooms, teachers = await _form_options(db)
	return render(request, "course_schedule/form.html", course=None, form={}, rooms=rooms,
	              teachers=teachers, is_admin=user["role"] == ROLE_ADMIN, error=None)


@router.post("/new")
async def course_new(request: Request, user: LoginUser, db: DB,
                     course_code: str = Form(""), name: str = Form(""), room_id: int = Form(...),
                     start_date: str = Form(""), weeks: int = Form(1),
                     start_time: str = Form(""), end_time: str = Form(""),
                     teacher_id: int | None = Form(None)):   # 老師送出時沒有這欄，所以允許 None
	"""處理新增表單送出。"""
	is_admin = user["role"] == ROLE_ADMIN
	f, error = _parse_form(course_code, name, room_id, start_date, weeks, start_time, end_time)
	if error:
		# 驗證失敗：回到表單並保留使用者已填的內容
		rooms, teachers = await _form_options(db)
		return render(request, "course_schedule/form.html", course=None, form=await request.form(),
		              rooms=rooms, teachers=teachers, is_admin=is_admin, error=error)
	# 只有管理員能指派老師；老師一律是自己
	owner_id = teacher_id if (is_admin and teacher_id) else user["id"]
	cur = await db.execute(
		# created_by 是 NOT NULL，一定要填（記錄「誰建立的」）
		"""INSERT INTO courses (course_code, name, teacher_id, created_by)
		   VALUES (%s, %s, %s, %s) RETURNING id""",
		(f["code"], f["name"], owner_id, user["id"]),
	)
	course_id = (await cur.fetchone())["id"]
	warn = await _create_sessions(db, course_id, f)
	# 303 導回清單；warn 帶在網址讓清單顯示衝突警告
	return RedirectResponse(f"/schedule?warn={warn}", status_code=303)

#修改課程
@router.post("/{course_id}/edit")
async def course_edit(course_id: int, user: LoginUser, db: DB,
                      course_code: str = Form(""), name: str = Form(""),
                      teacher_id: int | None = Form(None),
                      room_id: int | None = Form(None),
                      start_time: str = Form(""), end_time: str = Form("")):
	"""一次儲存：課號、課名、老師，並把教室與上課時間統一套用到每一堂（日期不變）。"""
	course = await _get_course_or_403(db, course_id, user)
	if not name.strip():
		raise HTTPException(status_code=400, detail="請填寫課名")
	owner_id = teacher_id if (user["role"] == ROLE_ADMIN and teacher_id) else course["teacher_id"]
	await db.execute(
		"""UPDATE courses SET course_code = %s, name = %s, teacher_id = %s, updated_at = now()
		   WHERE id = %s""",
		(course_code.strip() or None, name.strip(), owner_id, course_id),
	)
	# 有填教室與時間才更新所有時段
	if room_id and start_time and end_time:
		try:
			t1, t2 = time.fromisoformat(start_time), time.fromisoformat(end_time)
		except ValueError:
			raise HTTPException(status_code=400, detail="時間格式不正確")
		if t2 <= t1:
			raise HTTPException(status_code=400, detail="結束時間必須晚於開始時間")
		await db.execute(
			"""UPDATE course_sessions SET room_id = %s, start_time = %s, end_time = %s
			   WHERE course_id = %s""",
			(room_id, t1, t2, course_id),
		)
	return RedirectResponse("/schedule", status_code=303)   # 儲存後回清單

@router.get("/{course_id}/edit")
async def course_edit_form(course_id: int, request: Request, user: LoginUser, db: DB):
	"""編輯課程：課號、課名、老師，加上統一的教室與上課時間。"""
	course = await _get_course_or_403(db, course_id, user)
	cur = await db.execute(
		"""SELECT room_id, start_time, end_time FROM course_sessions
		   WHERE course_id = %s ORDER BY session_date, start_time LIMIT 1""",
		(course_id,),
	)
	first = await cur.fetchone()
	form = dict(first) if first else {}
	rooms, teachers = await _form_options(db)
	return render(request, "course_schedule/form.html", course=course, form=form, rooms=rooms,
	              teachers=teachers, is_admin=user["role"] == ROLE_ADMIN, error=None)

#刪除課程
@router.post("/{course_id}/delete")
async def course_delete(course_id: int, user: LoginUser, db: DB):
	"""刪除課程。用 POST（不用 GET），避免被連結或瀏覽器預載誤觸。"""
	await _get_course_or_403(db, course_id, user)
	# 順序：先刪子表 course_sessions，再刪 courses（外鍵限制）
	await db.execute("DELETE FROM course_sessions WHERE course_id = %s", (course_id,))
	await db.execute("DELETE FROM courses WHERE id = %s", (course_id,))
	return RedirectResponse("/schedule", status_code=303)