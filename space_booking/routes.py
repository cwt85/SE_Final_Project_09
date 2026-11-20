# space_booking/routes.py
# 模組②：空間／物品預約借用
# 網址都以 /booking 開頭。整個模組都要登入。
from fastapi import APIRouter, Depends, Request

from common.auth import require_admin, require_login
from common.db import getDB
from common.templating import render

# dependencies=[...] 會套用到這個 router 底下的「所有」網址：沒登入一律導向登入頁
router = APIRouter(prefix="/booking", tags=["② 預約借用"], dependencies=[Depends(require_login)])


@router.get("")
async def my_bookings(request: Request, user=Depends(require_login), db=Depends(getDB)):
	"""我的借用紀錄。"""
	cur = await db.execute(
		"""SELECT b.id, b.booking_date, b.start_time, b.end_time, b.purpose, b.status,
		          b.review_comment, r.room_code, r.name AS room_name,
		          -- 把這張單借的所有物品組成一個字串，例如「M101 鑰匙 ×1、投影筆 ×1」
		          string_agg(i.name || ' ×' || bi.quantity, '、' ORDER BY i.id) AS item_list
		   FROM bookings b
		   JOIN rooms r ON r.id = b.room_id
		   LEFT JOIN booking_items bi ON bi.booking_id = b.id
		   LEFT JOIN items i ON i.id = bi.item_id
		   WHERE b.user_id = %s
		   GROUP BY b.id, r.id
		   ORDER BY b.booking_date DESC, b.start_time DESC""",
		(user["id"],),
	)
	return render(request, "space_booking/index.html", bookings=await cur.fetchall())


@router.get("/new")
async def new_booking(request: Request, room_id: int | None = None):
	"""預約表單。空間查詢模組的「預約這個空間」會帶 ?room_id= 過來。"""
	# TODO: 選空間 → 顯示當週借用狀況（common.occupancy.get_week_occupancy）
	#       → 填日期、時段、物品 → 送出前用 common.occupancy.find_conflicts 檢查衝突
	return render(request, "space_booking/new.html", room_id=room_id)


@router.get("/admin")
async def booking_admin(request: Request, user=Depends(require_admin)):
	"""管理員：審核、登記借出、確認歸還。"""
	# TODO: 列出待審核／待領用／待歸還的借用單
	return render(request, "space_booking/admin.html")
