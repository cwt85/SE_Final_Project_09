# space_booking/routes.py
# 模組②：空間／物品預約借用
# 網址都以 /booking 開頭。整個模組都要登入。
#
# 借用單狀態流程（詳見 README.md）：
#   pending ──通過──→ approved ──領用──→ checked_out ──歸還──→ returned
#      ├──退件──→ rejected
#      └──申請人取消──→ cancelled
#
# 資料格式注意事項：
#   - 日期、時間：表單送來的是字串（"2026-11-24"、"13:00"），一律先轉成 Python 的
#     date / time 物件再交給 psycopg，它會自動對應到資料庫的 DATE / TIME 欄位。
#   - TIME 欄位沒有時區；「現在幾點」一律問資料庫並明確指定 Asia/Taipei，
#     不用 Python 的 datetime.now()，避免伺服器電腦時區不同造成判斷錯誤。
#   - TIMESTAMPTZ 欄位（審核／借出／歸還時間）一律在 SQL 裡用 now() 寫入，
#     顯示時用 AT TIME ZONE 'Asia/Taipei' 轉成台灣時間。
from datetime import date, time, timedelta
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse

from common.auth import AdminUser, LoginUser, require_login
from common.db import DB
from common.occupancy import find_conflicts, get_week_occupancy, week_range
from common.templating import render

# dependencies=[...] 會套用到這個 router 底下的「所有」網址：沒登入一律導向登入頁
router = APIRouter(prefix="/booking", tags=["② 預約借用"], dependencies=[Depends(require_login)])

# ---------- 常數 ----------
# 開放借用的時間範圍（週曆也只畫這段）
OPEN_TIME = time(7, 0)
CLOSE_TIME = time(22, 0)

# 借用單狀態的中文名稱
STATUS_LABELS = {
	"pending": "待審核", "approved": "已核准", "rejected": "已退件",
	"checked_out": "已借出", "returned": "已歸還", "cancelled": "已取消",
}
CATEGORY_LABELS = {"key": "鑰匙", "device": "設備", "other": "其他"}

# 管理頁的分頁：(網址參數, 顯示名稱, 要查的狀態；None = 全部)
ADMIN_TABS = [
	("pending", "待審核", "pending"),
	("approved", "待領用", "approved"),
	("checked_out", "待歸還", "checked_out"),
	("all", "全部紀錄", None),
]

# PostgreSQL「交易層級鎖」的編號（隨便選一個不會和別人撞的數字）。
# 為什麼要鎖？兩個管理員同時核准同一時段的兩張單，可能都先檢查「沒衝突」再寫入，
# 結果兩張都過。先拿到這把鎖的人做完（commit）之後，下一個人才能開始檢查，就不會重複核准。
# 交易結束（commit 或 rollback）時鎖會自動釋放，不用手動解鎖。
BOOKING_LOCK_KEY = 2_0001


# =========================================================
# 小工具
# =========================================================
def redirect(url: str, **params) -> RedirectResponse:
	"""表單送出後導回列表頁（303 讓瀏覽器改用 GET，按 F5 不會重複送出）。"""
	query = urlencode({k: v for k, v in params.items() if v})
	return RedirectResponse(f"{url}?{query}" if query else url, status_code=303)


def parse_date(text: str | None) -> date | None:
	"""'2026-11-24' → date；格式錯誤回傳 None。"""
	try:
		return date.fromisoformat((text or "").strip())
	except ValueError:
		return None


def parse_time(text: str | None) -> time | None:
	"""'13:00' 或 '13:00:00' → time（秒數一律捨去）；格式錯誤回傳 None。"""
	try:
		return time.fromisoformat((text or "").strip()).replace(second=0, microsecond=0)
	except ValueError:
		return None


def minutes(t: time) -> int:
	"""time → 從 00:00 起算的分鐘數，方便計算週曆上的位置。"""
	return t.hour * 60 + t.minute


async def db_now(db) -> tuple[date, time]:
	"""向資料庫問「台灣現在的日期和時間」。"""
	cur = await db.execute(
		"""SELECT (now() AT TIME ZONE 'Asia/Taipei')::date    AS today,
		          (now() AT TIME ZONE 'Asia/Taipei')::time(0) AS now_time"""
	)
	row = await cur.fetchone()
	return row["today"], row["now_time"]


async def lock_bookings(db) -> None:
	"""取得借用模組的交易鎖（說明見 BOOKING_LOCK_KEY）。要放在「檢查衝突」之前呼叫。"""
	await db.execute("SELECT pg_advisory_xact_lock(%s)", (BOOKING_LOCK_KEY,))


# =========================================================
# 查詢
# =========================================================
async def bookable_rooms(db) -> list[dict]:
	"""開放借用的空間（給下拉選單用）。"""
	cur = await db.execute(
		"SELECT id, room_code, name, capacity FROM rooms WHERE is_bookable ORDER BY room_code"
	)
	return await cur.fetchall()


async def item_options(db, room_id: int) -> list[dict]:
	"""
	某空間可以借的物品：所有還能借的設備／其他物品，加上「這間教室自己的」鑰匙。
	（不能在借 M101 的單子上借 M102 的鑰匙）
	"""
	cur = await db.execute(
		"""SELECT id, name, category, total_quantity
		   FROM items
		   WHERE is_active
		     AND (category <> 'key' OR room_id = %s)
		   ORDER BY (category = 'key') DESC, id   -- 鑰匙排最前面""",
		(room_id,),
	)
	return await cur.fetchall()


async def item_shortages(
	db, day: date, start: time, end: time, requested: dict[int, int],
	exclude_booking_id: int | None = None,
) -> list[str]:
	"""
	檢查物品在這個時段夠不夠借。requested = {item_id: 數量}。
	和教室一樣，只有 approved / checked_out 的借用單才算「已經被借走」。
	回傳不夠的物品說明；空 list 代表都夠。
	"""
	if not requested:
		return []
	cur = await db.execute(
		"""SELECT i.id, i.name, i.total_quantity,
		          -- 同一天、時間重疊、已核准或已借出的單子，總共借走幾個
		          COALESCE((
		              SELECT SUM(bi.quantity)
		              FROM booking_items bi
		              JOIN bookings b ON b.id = bi.booking_id
		              WHERE bi.item_id = i.id
		                AND b.status IN ('approved', 'checked_out')
		                AND b.booking_date = %(day)s
		                AND b.start_time < %(end)s
		                AND %(start)s < b.end_time
		                -- 審核時要排除自己；用 IS DISTINCT FROM 是因為 exclude 為 NULL 時
		                -- 「b.id <> NULL」會變成 NULL，整筆被濾掉
		                AND b.id IS DISTINCT FROM %(exclude)s
		          ), 0) AS in_use
		   FROM items i
		   WHERE i.id = ANY(%(ids)s)
		   ORDER BY i.id""",
		{"day": day, "start": start, "end": end,
		 "exclude": exclude_booking_id, "ids": list(requested)},
	)
	problems = []
	for row in await cur.fetchall():
		left = row["total_quantity"] - row["in_use"]
		if requested[row["id"]] > left:
			problems.append(f"{row['name']}：這個時段只剩 {max(left, 0)} 個，申請了 {requested[row['id']]} 個")
	return problems


async def checkout_shortages(db, booking_id: int) -> list[str]:
	"""
	登記借出前，確認物品「實際上」還在架上：
	其他已借出（checked_out）還沒歸還的單子，不管哪一天的，都佔著實體物品。
	"""
	cur = await db.execute(
		"""SELECT i.name, i.total_quantity, bi.quantity,
		          COALESCE((
		              SELECT SUM(bi2.quantity)
		              FROM booking_items bi2
		              JOIN bookings b2 ON b2.id = bi2.booking_id
		              WHERE bi2.item_id = bi.item_id
		                AND b2.status = 'checked_out'
		                AND b2.id <> bi.booking_id
		          ), 0) AS out_now
		   FROM booking_items bi
		   JOIN items i ON i.id = bi.item_id
		   WHERE bi.booking_id = %s
		   ORDER BY i.id""",
		(booking_id,),
	)
	problems = []
	for row in await cur.fetchall():
		left = row["total_quantity"] - row["out_now"]
		if row["quantity"] > left:
			problems.append(f"{row['name']}：目前架上只剩 {max(left, 0)} 個（其他人借出未還），需要 {row['quantity']} 個")
	return problems


async def fetch_bookings(db, user_id: int | None = None, status: str | None = None) -> list[dict]:
	"""
	查借用單列表（含物品與經手人）。
	user_id / status 傳 None 代表不篩選。結果依日期、開始時間由早到晚排序。
	"""
	cur = await db.execute(
		"""SELECT b.id, b.user_id, b.room_id, b.booking_date, b.start_time, b.end_time,
		          b.purpose, b.status, b.review_comment,
		          r.room_code, r.name AS room_name,
		          u.full_name AS applicant, u.username AS applicant_username,
		          -- 把這張單借的所有物品組成一個字串，例如「M101 鑰匙 ×1、投影筆 ×1」
		          -- （欄位不能取名叫 items：查詢結果是 dict，row.items 會拿到 dict 的方法）
		          (SELECT string_agg(i.name || ' ×' || bi.quantity, '、' ORDER BY i.id)
		             FROM booking_items bi JOIN items i ON i.id = bi.item_id
		            WHERE bi.booking_id = b.id) AS item_list,
		          -- TIMESTAMPTZ 轉成台灣時間的文字，顯示時不用再處理時區
		          to_char(b.created_at     AT TIME ZONE 'Asia/Taipei', 'YYYY-MM-DD HH24:MI') AS created_text,
		          to_char(b.reviewed_at    AT TIME ZONE 'Asia/Taipei', 'YYYY-MM-DD HH24:MI') AS reviewed_text,
		          to_char(b.checked_out_at AT TIME ZONE 'Asia/Taipei', 'YYYY-MM-DD HH24:MI') AS checked_out_text,
		          to_char(b.returned_at    AT TIME ZONE 'Asia/Taipei', 'YYYY-MM-DD HH24:MI') AS returned_text,
		          rv.full_name AS reviewer_name,
		          co.full_name AS checked_out_name,
		          rt.full_name AS returned_name
		   FROM bookings b
		   JOIN rooms r ON r.id = b.room_id
		   JOIN users u ON u.id = b.user_id
		   LEFT JOIN users rv ON rv.id = b.reviewed_by
		   LEFT JOIN users co ON co.id = b.checked_out_by
		   LEFT JOIN users rt ON rt.id = b.returned_by
		   -- 參數是 NULL 時條件恆成立 = 不篩選；::int / ::text 是告訴資料庫 NULL 的型別
		   WHERE (%(user_id)s::int  IS NULL OR b.user_id = %(user_id)s)
		     AND (%(status)s::text IS NULL OR b.status  = %(status)s)
		   ORDER BY b.booking_date, b.start_time, b.id""",
		{"user_id": user_id, "status": status},
	)
	return await cur.fetchall()


# =========================================================
# 週曆
# =========================================================
def build_calendar(monday: date, occupancy: list[dict], pending: list[dict], user_id: int) -> list[dict]:
	"""
	把占用資料整理成 7 天，每天一串「方塊」，給模板畫週曆。
	方塊的位置用百分比：top = 開始時間在營業時間中的比例，height = 長度的比例。
	"""
	day_start, day_end = minutes(OPEN_TIME), minutes(CLOSE_TIME)
	span = day_end - day_start
	days = {monday + timedelta(days=i): [] for i in range(7)}

	def add(day: date, start: time, end: time, kind: str, title: str):
		# 超出營業時間的部分切掉；完全在範圍外就不畫
		s = max(minutes(start), day_start)
		e = min(minutes(end), day_end)
		if day in days and s < e:
			days[day].append({
				"kind": kind,
				"title": title,
				"time_text": f"{start:%H:%M}–{end:%H:%M}",
				"top": round((s - day_start) / span * 100, 3),
				"height": round((e - s) / span * 100, 3),
			})

	for row in occupancy:
		if row["source"] == "course":
			add(row["occupy_date"], row["start_time"], row["end_time"], "course", f"上課：{row['title']}")
		else:
			mine = "（你的）" if row["owner_id"] == user_id else ""
			add(row["occupy_date"], row["start_time"], row["end_time"], "booking", f"借用：{row['title']}{mine}")
	for row in pending:
		# 別人的待審核單只顯示「審核中」，不顯示事由
		title = f"審核中：{row['purpose'] or '借用'}（你的）" if row["user_id"] == user_id else "審核中"
		add(row["booking_date"], row["start_time"], row["end_time"], "pending", title)

	weekday_names = "一二三四五六日"
	return [
		{"date": d, "label": f"週{weekday_names[d.weekday()]}", "events": events}
		for d, events in days.items()
	]


async def render_new_form(
	request: Request, db, user: dict, room_id: int | None, week_day: date | None,
	form: dict, error: str | None = None, problems: list[str] | None = None,
	status_code: int = 200,
):
	"""畫出預約頁：空間選單、該空間當週借用狀況、預約表單。GET 和送出失敗時共用。"""
	today, _ = await db_now(db)
	rooms = await bookable_rooms(db)
	room = next((r for r in rooms if r["id"] == room_id), None)
	if room_id is not None and room is None and error is None:
		error = "這個空間不存在或不開放借用，請重新選擇"

	monday, sunday = week_range(week_day or today)
	calendar, options = [], []
	if room:
		occupancy = await get_week_occupancy(db, room["id"], monday)
		cur = await db.execute(
			"""SELECT id, user_id, booking_date, start_time, end_time, purpose
			   FROM bookings
			   WHERE room_id = %s AND status = 'pending' AND booking_date BETWEEN %s AND %s""",
			(room["id"], monday, sunday),
		)
		calendar = build_calendar(monday, occupancy, await cur.fetchall(), user["id"])
		options = await item_options(db, room["id"])

	# 週曆左側的時間刻度：每小時一格
	hours = [f"{h:02d}:00" for h in range(OPEN_TIME.hour, CLOSE_TIME.hour)]
	return render(
		request, "space_booking/new.html", status_code=status_code,
		rooms=rooms, room=room, form=form, error=error, problems=problems or [],
		calendar=calendar, hours=hours, item_options=options, today=today,
		monday=monday, sunday=sunday,
		prev_week=monday - timedelta(days=7), next_week=monday + timedelta(days=7),
		open_time=f"{OPEN_TIME:%H:%M}", close_time=f"{CLOSE_TIME:%H:%M}",
		CATEGORY_LABELS=CATEGORY_LABELS,
	)


# =========================================================
# 一般使用者
# =========================================================
@router.get("")
async def my_bookings(request: Request, user: LoginUser, db: DB,
                      msg: str | None = None, error: str | None = None):
	"""我的借用紀錄（新的日期排前面）。"""
	bookings = await fetch_bookings(db, user_id=user["id"])
	bookings.reverse()
	return render(request, "space_booking/index.html", bookings=bookings,
	              STATUS_LABELS=STATUS_LABELS, msg=msg, error=error)


@router.get("/new")
async def new_booking(request: Request, user: LoginUser, db: DB,
                      room_id: int | None = None, week: str | None = None):
	"""預約表單。空間查詢模組的「預約這個空間」會帶 ?room_id= 過來；?week= 是要看哪一週。"""
	return await render_new_form(request, db, user, room_id, parse_date(week), form={})


@router.post("/new")
async def create_booking(request: Request, user: LoginUser, db: DB):
	"""
	送出預約。物品欄位是動態的（qty_<物品id>），所以直接讀整份表單。
	檢查順序：空間 → 日期時間格式 → 物品 → （上鎖）時段衝突 → 物品數量 → 寫入。
	"""
	data = await request.form()
	room_id = data.get("room_id", "")
	form = {
		"booking_date": data.get("booking_date", ""),
		"start_time": data.get("start_time", ""),
		"end_time": data.get("end_time", ""),
		"purpose": data.get("purpose", "").strip(),
		"qty": {},  # 使用者填的物品數量，送出失敗時要填回表單
	}
	room_id = int(room_id) if room_id.isdigit() else None
	day = parse_date(form["booking_date"])
	start = parse_time(form["start_time"])
	end = parse_time(form["end_time"])

	async def fail(message: str, problems: list[str] | None = None, status_code: int = 400):
		# 送出失敗：保留使用者填的資料，回到同一頁顯示錯誤
		return await render_new_form(request, db, user, room_id, day, form,
		                             error=message, problems=problems, status_code=status_code)

	# ---- 1. 空間 ----
	rooms = await bookable_rooms(db)
	if room_id not in {r["id"] for r in rooms}:
		return await fail("請選擇開放借用的空間")

	# ---- 2. 日期、時間 ----
	today, now_time = await db_now(db)
	if day is None or start is None or end is None:
		return await fail("請填寫正確的日期與時間")
	if not start < end:  # 對應資料表的 CHECK (start_time < end_time)
		return await fail("結束時間必須晚於開始時間")
	if start < OPEN_TIME or end > CLOSE_TIME:
		return await fail(f"借用時間須在 {OPEN_TIME:%H:%M}–{CLOSE_TIME:%H:%M} 之間")
	if day < today or (day == today and start <= now_time):
		return await fail("不能預約已經過去的時段")
	if len(form["purpose"]) > 200:
		return await fail("借用事由請在 200 字以內")

	# ---- 3. 物品（可多項）----
	allowed = {row["id"]: row for row in await item_options(db, room_id)}
	requested: dict[int, int] = {}
	for key, value in data.items():
		if not key.startswith("qty_"):
			continue
		value = str(value).strip()
		form["qty"][key] = value
		if value == "":
			continue  # 沒填 = 不借
		if not value.isdigit():  # isdigit() 會擋掉負數、小數、文字
			return await fail("物品數量必須是正整數")
		qty = int(value)
		if qty == 0:
			continue  # 填 0（或 00）= 不借；不能寫進資料庫，因為 CHECK (quantity > 0)
		item_id = key.removeprefix("qty_")
		if not item_id.isdigit() or int(item_id) not in allowed:
			return await fail("借用物品不正確，請重新選擇")
		item = allowed[int(item_id)]
		if qty > item["total_quantity"]:  # 不能超過物品總數
			return await fail(f"{item['name']} 最多只能借 {item['total_quantity']} 個")
		requested[item["id"]] = qty

	# ---- 4. 上鎖後檢查衝突（教室＋排課）與物品數量 ----
	await lock_bookings(db)
	conflicts = await find_conflicts(db, room_id, day, start, end)
	if conflicts:
		problems = [
			f"{'上課' if c['source'] == 'course' else '借用'}：{c['title']}"
			f"（{c['start_time']:%H:%M}–{c['end_time']:%H:%M}）"
			for c in conflicts
		]
		return await fail("這個時段已經被占用，請換一個時間", problems, status_code=409)
	shortages = await item_shortages(db, day, start, end, requested)
	if shortages:
		return await fail("借用物品數量不足", shortages, status_code=409)

	# ---- 5. 寫入：先新增借用單拿到 id，再新增物品明細（同一個交易，失敗會全部取消）----
	cur = await db.execute(
		"""INSERT INTO bookings (user_id, room_id, booking_date, start_time, end_time, purpose)
		   VALUES (%s, %s, %s, %s, %s, %s)
		   RETURNING id""",
		(user["id"], room_id, day, start, end, form["purpose"] or None),
	)
	booking_id = (await cur.fetchone())["id"]
	if requested:
		async with db.cursor() as cur:
			await cur.executemany(
				"INSERT INTO booking_items (booking_id, item_id, quantity) VALUES (%s, %s, %s)",
				[(booking_id, item_id, qty) for item_id, qty in requested.items()],
			)
	return redirect("/booking", msg="已送出預約申請，請等候管理員審核")


@router.post("/{booking_id}/cancel")
async def cancel_booking(booking_id: int, user: LoginUser, db: DB):
	"""申請人取消自己「待審核」的借用單。WHERE 同時檢查本人與狀態，別人的單或已審核的單都改不到。"""
	cur = await db.execute(
		"""UPDATE bookings SET status = 'cancelled'
		   WHERE id = %s AND user_id = %s AND status = 'pending'
		   RETURNING id""",
		(booking_id, user["id"]),
	)
	if await cur.fetchone() is None:
		return redirect("/booking", error="只能取消自己尚在審核中的借用單")
	return redirect("/booking", msg="已取消借用申請")


# =========================================================
# 管理員：審核、借出、歸還
# =========================================================
@router.get("/admin")
async def booking_admin(request: Request, user: AdminUser, db: DB, tab: str = "pending",
                        msg: str | None = None, error: str | None = None):
	"""管理員：依分頁列出待審核／待領用／待歸還／全部的借用單。"""
	tabs = {key: (label, status) for key, label, status in ADMIN_TABS}
	if tab not in tabs:
		tab = "pending"
	bookings = await fetch_bookings(db, status=tabs[tab][1])
	if tab == "all":
		bookings.reverse()  # 全部紀錄：新的排前面

	# 待審核的單先幫管理員檢查一次衝突和物品數量，有問題直接在畫面上提醒
	for b in bookings:
		b["warnings"] = []
		if b["status"] == "pending":
			for c in await find_conflicts(db, b["room_id"], b["booking_date"], b["start_time"], b["end_time"]):
				b["warnings"].append(
					f"時段衝突（{'上課' if c['source'] == 'course' else '借用'}：{c['title']} "
					f"{c['start_time']:%H:%M}–{c['end_time']:%H:%M}）"
				)
			cur = await db.execute(
				"SELECT item_id, quantity FROM booking_items WHERE booking_id = %s", (b["id"],)
			)
			requested = {r["item_id"]: r["quantity"] for r in await cur.fetchall()}
			b["warnings"] += await item_shortages(
				db, b["booking_date"], b["start_time"], b["end_time"], requested, exclude_booking_id=b["id"]
			)

	# 各分頁的筆數
	cur = await db.execute("SELECT status, count(*) AS n FROM bookings GROUP BY status")
	counts = {r["status"]: r["n"] for r in await cur.fetchall()}
	today, now_time = await db_now(db)
	return render(
		request, "space_booking/admin.html",
		bookings=bookings, tab=tab, tabs=ADMIN_TABS, counts=counts, total=sum(counts.values()),
		STATUS_LABELS=STATUS_LABELS, msg=msg, error=error, today=today, now_time=now_time,
	)


async def load_booking(db, booking_id: int) -> dict | None:
	"""讀一張借用單，並用 FOR UPDATE 鎖住這一列，避免同時被別人改。"""
	cur = await db.execute(
		"""SELECT id, room_id, booking_date, start_time, end_time, status
		   FROM bookings WHERE id = %s FOR UPDATE""",
		(booking_id,),
	)
	return await cur.fetchone()


@router.post("/admin/{booking_id}/review")
async def review_booking(
	booking_id: int,
	user: AdminUser,
	db: DB,
	action: str = Form(...),
	comment: str = Form(""),
	tab: str = Form("pending"),
):
	"""審核：通過（approve）或退件（reject），可加註審核意見。"""
	back = "/booking/admin"
	comment = comment.strip() or None
	if action not in ("approve", "reject"):
		return redirect(back, tab=tab, error="不明的審核動作")

	await lock_bookings(db)
	b = await load_booking(db, booking_id)
	if b is None or b["status"] != "pending":
		return redirect(back, tab=tab, error=f"借用單 #{booking_id} 不是待審核狀態，可能已被處理")

	if action == "approve":
		# 審核通過前要再檢查一次：pending 不算占用，可能有別人的單先被核准、或排課後來加進來
		today, now_time = await db_now(db)
		if b["booking_date"] < today or (b["booking_date"] == today and b["end_time"] <= now_time):
			return redirect(back, tab=tab, error=f"借用單 #{booking_id} 的時段已經過去，只能退件")
		conflicts = await find_conflicts(db, b["room_id"], b["booking_date"], b["start_time"], b["end_time"],
		                                 exclude_source="booking", exclude_id=booking_id)
		if conflicts:
			names = "、".join(f"{c['title']}（{c['start_time']:%H:%M}–{c['end_time']:%H:%M}）" for c in conflicts)
			return redirect(back, tab=tab, error=f"借用單 #{booking_id} 與 {names} 時段衝突，無法通過")
		cur = await db.execute(
			"SELECT item_id, quantity FROM booking_items WHERE booking_id = %s", (booking_id,)
		)
		requested = {r["item_id"]: r["quantity"] for r in await cur.fetchall()}
		shortages = await item_shortages(db, b["booking_date"], b["start_time"], b["end_time"],
		                                 requested, exclude_booking_id=booking_id)
		if shortages:
			return redirect(back, tab=tab, error=f"借用單 #{booking_id} 物品不足：" + "；".join(shortages))

	new_status = "approved" if action == "approve" else "rejected"
	# WHERE 再確認一次 status = 'pending'，保證狀態只能照流程往前走
	await db.execute(
		"""UPDATE bookings
		   SET status = %s, review_comment = %s, reviewed_by = %s, reviewed_at = now()
		   WHERE id = %s AND status = 'pending'""",
		(new_status, comment, user["id"], booking_id),
	)
	return redirect(back, tab=tab, msg=f"借用單 #{booking_id} 已{STATUS_LABELS[new_status]}")


@router.post("/admin/{booking_id}/checkout")
async def checkout_booking(booking_id: int, user: AdminUser, db: DB, tab: str = Form("approved")):
	"""領用：申請人來拿鑰匙和物品時，由管理員登記借出。"""
	back = "/booking/admin"
	await lock_bookings(db)
	b = await load_booking(db, booking_id)
	if b is None or b["status"] != "approved":
		return redirect(back, tab=tab, error=f"借用單 #{booking_id} 不是「已核准」狀態，無法登記借出")
	shortages = await checkout_shortages(db, booking_id)
	if shortages:
		return redirect(back, tab=tab, error=f"借用單 #{booking_id} 無法借出：" + "；".join(shortages))
	await db.execute(
		"""UPDATE bookings
		   SET status = 'checked_out', checked_out_by = %s, checked_out_at = now()
		   WHERE id = %s AND status = 'approved'""",
		(user["id"], booking_id),
	)
	return redirect(back, tab=tab, msg=f"借用單 #{booking_id} 已登記借出")


@router.post("/admin/{booking_id}/return")
async def return_booking(booking_id: int, user: AdminUser, db: DB, tab: str = Form("checked_out")):
	"""歸還：管理員確認東西都還回來後登記歸還。"""
	back = "/booking/admin"
	cur = await db.execute(
		"""UPDATE bookings
		   SET status = 'returned', returned_by = %s, returned_at = now()
		   WHERE id = %s AND status = 'checked_out'
		   RETURNING id""",
		(user["id"], booking_id),
	)
	if await cur.fetchone() is None:
		return redirect(back, tab=tab, error=f"借用單 #{booking_id} 不是「已借出」狀態，無法登記歸還")
	return redirect(back, tab=tab, msg=f"借用單 #{booking_id} 已登記歸還")
