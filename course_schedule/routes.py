# course_schedule/routes.py
# 模組③：課程排課
# 網址都以 /schedule 開頭。整個模組都要登入。
from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from common.auth import ROLE_ADMIN, ROLE_TEACHER, ROLE_USER, AdminUser, LoginUser, require_login
from common.db import DB
from common.occupancy import find_conflicts, get_week_occupancy
from common.templating import render

# dependencies=[...] 會套用到這個 router 底下的「所有」網址：沒登入一律導向登入頁
router = APIRouter(prefix="/schedule", tags=["③ 課程排課"], dependencies=[Depends(require_login)])

ROLE_STUDENT = ROLE_USER   # 一般使用者就是學生


# ---------- 共用輔助 ----------

async def _ensure_enroll_table(db):
	"""模組自己建選課表，不必改 sql/ 資料夾。"""
	await db.execute("""CREATE TABLE IF NOT EXISTS course_enrollments (
	  course_id  integer NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
	  student_id integer NOT NULL REFERENCES users(id),
	  created_at timestamptz NOT NULL DEFAULT now(),
	  PRIMARY KEY (course_id, student_id))""")


def _require_student(user):
	if user["role"] != ROLE_STUDENT:
		raise HTTPException(status_code=403)


def _forbid_student(user):
	if user["role"] == ROLE_STUDENT:
		raise HTTPException(status_code=403)


async def _form_options(db):
	"""表單的下拉選單資料：所有教室、所有老師。"""
	cur = await db.execute("SELECT id, room_code FROM rooms ORDER BY room_code")
	rooms = await cur.fetchall()
	# 'teacher' 要和 users.role 實際的值一致
	cur = await db.execute("SELECT id, full_name FROM users WHERE role = 'teacher' ORDER BY full_name")
	teachers = await cur.fetchall()
	return rooms, teachers


async def _get_course_or_403(db, course_id: int, user):
	"""取得課程並做權限檢查。找不到 → 404；不是管理員且不是自己的課 → 403。"""
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
	d2 = d1 + timedelta(weeks=weeks - 1)   # 最後一週的日期
	return {"code": course_code.strip() or None, "name": name.strip(), "room_id": room_id,
	        "d1": d1, "d2": d2, "t1": t1, "t2": t2}, None


async def _create_sessions(db, course_id: int, f: dict) -> int:
	"""從開始日期起每隔 7 天建立一筆上課時段；回傳有衝突的時段數（只警告，不阻擋）。"""
	warn = 0
	day = f["d1"]
	while day <= f["d2"]:
		cur = await db.execute(
			"""INSERT INTO course_sessions (course_id, room_id, session_date, start_time, end_time)
			   VALUES (%s, %s, %s, %s, %s) RETURNING id""",
			(course_id, f["room_id"], day, f["t1"], f["t2"]),
		)
		session_id = (await cur.fetchone())["id"]
		found = await find_conflicts(db, f["room_id"], day, f["t1"], f["t2"],
		                             exclude_source="course", exclude_id=session_id)
		if found:
			warn += 1
		day += timedelta(days=7)
	return warn


# ---------- 課程清單 ----------

@router.get("")
async def course_list(request: Request, user: LoginUser, db: DB, warn: int = 0):
	"""課程清單：學生看自己選的課，老師看自己的課，管理員看全部。"""
	await _ensure_enroll_table(db)
	is_admin = user["role"] == ROLE_ADMIN
	is_student = user["role"] == ROLE_STUDENT
	cur = await db.execute(
		"""SELECT c.id, c.course_code, c.name, u.full_name AS teacher_name,
		          count(s.id) AS session_count,
		          min(s.session_date) AS first_date,
		          max(s.session_date) AS last_date
		   FROM courses c
		   JOIN users u ON u.id = c.teacher_id
		   LEFT JOIN course_sessions s ON s.course_id = c.id
		   WHERE (%(is_student)s AND c.id IN
		            (SELECT course_id FROM course_enrollments WHERE student_id = %(uid)s))
		      OR (NOT %(is_student)s AND (%(is_admin)s OR c.teacher_id = %(uid)s))
		   GROUP BY c.id, u.full_name
		   ORDER BY c.course_code""",
		{"is_admin": is_admin, "uid": user["id"], "is_student": is_student},
	)
	return render(request, "course_schedule/index.html", courses=await cur.fetchall(),
	              is_admin=is_admin, is_student=is_student, warn=warn)


# ---------- 週曆 ----------

@router.get("/calendar")
async def calendar(request: Request, user: LoginUser, db: DB):
	"""週曆：只有管理員可以拖曳；教室下拉選單用來疊加借用占用。"""
	cur = await db.execute("SELECT id, room_code FROM rooms ORDER BY room_code")
	return render(request, "course_schedule/calendar.html",
	              is_admin=user["role"] == ROLE_ADMIN,
	              is_teacher=user["role"] == ROLE_TEACHER,
	              is_student=user["role"] == ROLE_STUDENT,
	              rooms=await cur.fetchall())


@router.get("/events")
async def events(user: LoginUser, db: DB, room_id: int = 0, start: str = ""):
	"""週曆事件：學生只看自己選的課；老師自己的課標橘色；選了教室就疊上該教室當週的借用。"""
	await _ensure_enroll_table(db)
	cur = await db.execute(
		"""SELECT s.id, c.teacher_id, c.course_code, c.name, r.room_code, u.full_name,
		          s.session_date, s.start_time, s.end_time
		   FROM course_sessions s
		   JOIN courses c ON c.id = s.course_id
		   JOIN rooms r ON r.id = s.room_id
		   JOIN users u ON u.id = c.teacher_id
		   WHERE (NOT %(is_student)s
		      OR c.id IN (SELECT course_id FROM course_enrollments WHERE student_id = %(uid)s))
		     AND (%(room_id)s = 0 OR s.room_id = %(room_id)s)""",
		{"is_student": user["role"] == ROLE_STUDENT, "uid": user["id"], "room_id": room_id},
	)
	out = []
	for r in await cur.fetchall():
		mine = user["role"] == ROLE_TEACHER and r["teacher_id"] == user["id"]
		code = r["course_code"] or ""
		tip = (f"{code} {r['name']}\n教室：{r['room_code']}\n老師：{r['full_name']}\n"
		       f"{r['start_time']:%H:%M}～{r['end_time']:%H:%M}")
		ev = {"id": r["id"],
		      "title": f"{code} {r['name']}",
		      "start": f"{r['session_date']}T{r['start_time']}",
		      "end": f"{r['session_date']}T{r['end_time']}",
		      "extendedProps": {"tip": tip, "code": code or r["name"][:6], "name": r["name"],
		                        "room": r["room_code"], "teacher": r["full_name"]}}
		if mine:
			ev["backgroundColor"] = ev["borderColor"] = "#e67e22"
		out.append(ev)

	# 選了教室才疊上該教室當週的借用（課程已畫過，所以略過 source == "course"）
	if room_id:
		try:
			any_day = datetime.fromisoformat(start).date() if start else date.today()
		except ValueError:
			any_day = date.today()
		any_day = any_day + timedelta(days=3)   # 確保落在該週中間，避免週界線誤差
		for o in await get_week_occupancy(db, room_id, any_day):
			if o["source"] == "course":
				continue
			out.append({
				"id": f"b{o['source_id']}",
				"title": o["title"],
				"start": f"{o['occupy_date']}T{o['start_time']}",
				"end": f"{o['occupy_date']}T{o['end_time']}",
				"editable": False,   # 借用不能拖曳
				"backgroundColor": "#95a5a6", "borderColor": "#95a5a6",
				"extendedProps": {"tip": f"借用：{o['title']}\n{o['start_time']:%H:%M}～{o['end_time']:%H:%M}",
				                  "code": "借用", "name": o["title"], "room": "",
				                  "teacher": "", "overlap": False},
			})
	return JSONResponse(out)


@router.post("/sessions/{session_id}/move")
async def session_move(session_id: int, request: Request, user: AdminUser, db: DB):
	"""管理員拖曳後，更新單一時段的日期與時間（後端驗證管理員）。"""
	data = await request.json()
	try:
		start = datetime.fromisoformat(data["start"])
		end = datetime.fromisoformat(data["end"])
	except (KeyError, ValueError):
		raise HTTPException(status_code=400, detail="時間格式不正確")
	if start.date() != end.date() or end <= start:
		raise HTTPException(status_code=400, detail="時段必須在同一天內")
	cur = await db.execute("SELECT room_id FROM course_sessions WHERE id = %s", (session_id,))
	s = await cur.fetchone()
	if s is None:
		raise HTTPException(status_code=404, detail="找不到這個時段")
	await db.execute(
		"UPDATE course_sessions SET session_date = %s, start_time = %s, end_time = %s WHERE id = %s",
		(start.date(), start.time(), end.time(), session_id),
	)
	# 排除自己後檢查衝突，只回報，不阻擋
	found = await find_conflicts(db, s["room_id"], start.date(), start.time(), end.time(),
	                             exclude_source="course", exclude_id=session_id)
	return JSONResponse({"ok": True, "conflict": bool(found)})


# ---------- 衝突清單 ----------

@router.get("/conflicts")
async def conflicts(request: Request, user: AdminUser, db: DB):
	"""管理員：時間衝突的課程清單（SQL 見 docs/database.md 5.3）。"""
	cur = await db.execute(
		"""SELECT a.id AS session_a, ca.name AS course_a,
		          b.id AS session_b, cb.name AS course_b,
		          a.session_date, r.room_code,
		          CASE WHEN a.room_id = b.room_id THEN '教室衝突' ELSE '老師衝堂' END AS conflict_type
		   FROM course_sessions a
		   JOIN course_sessions b
		     ON a.id < b.id
		    AND a.session_date = b.session_date
		    AND a.start_time < b.end_time
		    AND b.start_time < a.end_time
		   JOIN courses ca ON ca.id = a.course_id
		   JOIN courses cb ON cb.id = b.course_id
		   JOIN rooms r ON r.id = a.room_id
		   WHERE a.room_id = b.room_id
		      OR ca.teacher_id = cb.teacher_id
		   ORDER BY a.session_date, a.start_time"""
	)
	return render(request, "course_schedule/conflicts.html", conflicts=await cur.fetchall())


# ---------- 學生選課（固定路徑，放在 /{course_id}/... 之前） ----------

@router.get("/enroll")
async def enroll_page(request: Request, user: LoginUser, db: DB, q: str = ""):
	"""學生：列出所有課程，關鍵字搜尋課號、課名、老師。"""
	_require_student(user)
	await _ensure_enroll_table(db)
	q = q.strip()
	cur = await db.execute(
		"""SELECT c.id, c.course_code, c.name, u.full_name AS teacher_name,
		          count(s.id) AS session_count,
		          min(s.session_date) AS first_date, max(s.session_date) AS last_date,
		          EXISTS (SELECT 1 FROM course_enrollments e
		                  WHERE e.course_id = c.id AND e.student_id = %(uid)s) AS enrolled
		   FROM courses c
		   JOIN users u ON u.id = c.teacher_id
		   LEFT JOIN course_sessions s ON s.course_id = c.id
		   WHERE %(q)s = '' OR c.name ILIKE %(like)s OR c.course_code ILIKE %(like)s
		         OR u.full_name ILIKE %(like)s
		   GROUP BY c.id, u.full_name
		   ORDER BY c.course_code""",
		{"uid": user["id"], "q": q, "like": f"%{q}%"},
	)
	return render(request, "course_schedule/enroll.html", courses=await cur.fetchall(), q=q)


@router.post("/enroll")
async def enroll_submit(request: Request, user: LoginUser, db: DB):
	"""依勾選結果加選。"""
	_require_student(user)
	await _ensure_enroll_table(db)
	form = await request.form()
	for cid in form.getlist("course_ids"):
		if cid.isdigit():
			await db.execute(
				"""INSERT INTO course_enrollments (course_id, student_id)
				   SELECT id, %s FROM courses WHERE id = %s ON CONFLICT DO NOTHING""",
				(user["id"], int(cid)),
			)
	return RedirectResponse("/schedule", status_code=303)


# ---------- 新增課程（老師／管理員） ----------

@router.get("/new")
async def course_new_form(request: Request, user: LoginUser, db: DB):
	"""顯示空白的新增表單。"""
	_forbid_student(user)
	rooms, teachers = await _form_options(db)
	return render(request, "course_schedule/form.html", course=None, form={}, rooms=rooms,
	              teachers=teachers, is_admin=user["role"] == ROLE_ADMIN, error=None)


@router.post("/new")
async def course_new(request: Request, user: LoginUser, db: DB,
                     course_code: str = Form(""), name: str = Form(""), room_id: int = Form(...),
                     start_date: str = Form(""), weeks: int = Form(1),
                     start_time: str = Form(""), end_time: str = Form(""),
                     teacher_id: int | None = Form(None)):
	"""處理新增表單送出。"""
	_forbid_student(user)
	is_admin = user["role"] == ROLE_ADMIN
	f, error = _parse_form(course_code, name, room_id, start_date, weeks, start_time, end_time)
	if error:
		rooms, teachers = await _form_options(db)
		return render(request, "course_schedule/form.html", course=None, form=await request.form(),
		              rooms=rooms, teachers=teachers, is_admin=is_admin, error=error)
	# 只有管理員能指派老師；老師一律是自己
	owner_id = teacher_id if (is_admin and teacher_id) else user["id"]
	cur = await db.execute(
		"""INSERT INTO courses (course_code, name, teacher_id, created_by)
		   VALUES (%s, %s, %s, %s) RETURNING id""",
		(f["code"], f["name"], owner_id, user["id"]),
	)
	course_id = (await cur.fetchone())["id"]
	warn = await _create_sessions(db, course_id, f)
	return RedirectResponse(f"/schedule?warn={warn}", status_code=303)


# ---------- 修改課程 ----------

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


@router.post("/{course_id}/edit")
async def course_edit(course_id: int, user: LoginUser, db: DB,
                      course_code: str = Form(""), name: str = Form(""),
                      teacher_id: int | None = Form(None),
                      room_id: int | None = Form(None),
                      start_time: str = Form(""), end_time: str = Form("")):
	"""課號、課名、老師，並把教室與上課時間統一套用到每一堂（日期不變）。"""
	course = await _get_course_or_403(db, course_id, user)
	if not name.strip():
		raise HTTPException(status_code=400, detail="請填寫課名")
	owner_id = teacher_id if (user["role"] == ROLE_ADMIN and teacher_id) else course["teacher_id"]
	await db.execute(
		"""UPDATE courses SET course_code = %s, name = %s, teacher_id = %s, updated_at = now()
		   WHERE id = %s""",
		(course_code.strip() or None, name.strip(), owner_id, course_id),
	)
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
	return RedirectResponse("/schedule", status_code=303)


# ---------- 刪除課程、退選 ----------

@router.post("/{course_id}/delete")
async def course_delete(course_id: int, user: LoginUser, db: DB):
	"""刪除課程。先刪子表 course_sessions，再刪 courses（外鍵限制）。"""
	await _get_course_or_403(db, course_id, user)
	await _ensure_enroll_table(db)
	await db.execute("DELETE FROM course_sessions WHERE course_id = %s", (course_id,))
	await db.execute("DELETE FROM courses WHERE id = %s", (course_id,))   # 選課紀錄會 CASCADE 一併刪除
	return RedirectResponse("/schedule", status_code=303)


@router.post("/{course_id}/unenroll")
async def unenroll(course_id: int, user: LoginUser, db: DB):
	_require_student(user)
	await _ensure_enroll_table(db)
	await db.execute("DELETE FROM course_enrollments WHERE course_id = %s AND student_id = %s",
	                 (course_id, user["id"]))
	return RedirectResponse("/schedule", status_code=303)