# common/occupancy.py
# 「教室占用」的共用查詢：借用模組和排課模組都用這裡的函式，
# 這就是投影片上「排課與空間借用整合」的關鍵。
#
# 資料來源是資料庫的 VIEW room_occupancy，它把
#   已核准／已借出的借用單 (bookings) + 所有上課時段 (course_sessions)
# 合成同一張表。詳見 docs/database.md 第 5 節。
from datetime import date, time, timedelta


def week_range(any_day: date) -> tuple[date, date]:
	"""給任意一天，回傳那一週的週一和週日。"""
	monday = any_day - timedelta(days=any_day.weekday())  # weekday()：週一=0 … 週日=6
	return monday, monday + timedelta(days=6)


async def find_conflicts(
	db,
	room_id: int,
	day: date,
	start: time,
	end: time,
	exclude_source: str | None = None,
	exclude_id: int | None = None,
) -> list[dict]:
	"""
	找出和指定時段重疊的占用。回傳空 list 代表沒有衝突，可以安排。

	重疊的條件：已有的開始 < 新的結束，而且 新的開始 < 已有的結束
	（剛好接在一起，例如 10:00 結束、10:00 開始，不算衝突）

	修改既有資料時，要用 exclude_source / exclude_id 排除自己，否則會跟自己衝突：
	  exclude_source="booking" 或 "course"，exclude_id=那一筆的 id
	"""
	cur = await db.execute(
		"""
		SELECT source, source_id, title, occupy_date, start_time, end_time
		FROM room_occupancy
		WHERE room_id = %(room_id)s
		  AND occupy_date = %(day)s
		  AND start_time < %(end)s
		  AND %(start)s < end_time
		  -- 排除自己；COALESCE 是為了不傳 exclude 時（NULL）也能正確判斷
		  AND NOT COALESCE(source = %(ex_src)s AND source_id = %(ex_id)s, FALSE)
		ORDER BY start_time
		""",
		{"room_id": room_id, "day": day, "start": start, "end": end,
		 "ex_src": exclude_source, "ex_id": exclude_id},
	)
	return await cur.fetchall()


async def get_week_occupancy(db, room_id: int, any_day: date) -> list[dict]:
	"""取得某教室在 any_day 所在那一週的所有占用，給週曆畫面使用。"""
	monday, sunday = week_range(any_day)
	cur = await db.execute(
		"""
		SELECT source, source_id, title, occupy_date, start_time, end_time, owner_id
		FROM room_occupancy
		WHERE room_id = %s AND occupy_date BETWEEN %s AND %s
		ORDER BY occupy_date, start_time
		""",
		(room_id, monday, sunday),
	)
	return await cur.fetchall()
