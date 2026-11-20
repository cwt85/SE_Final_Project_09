# space_query/routes.py
# 模組①：管院空間查詢
# 網址都以 /spaces 開頭。瀏覽「不需要登入」；編輯教室資料要管理員。
from fastapi import APIRouter, HTTPException, Request

from common.auth import AdminUser
from common.db import DB
from common.templating import render

router = APIRouter(prefix="/spaces", tags=["① 空間查詢"])


@router.get("")
async def room_list(request: Request, db: DB):
	"""空間列表（公開）。"""
	cur = await db.execute(
		"""SELECT r.id, r.room_code, r.name, r.room_type, r.capacity, r.is_bookable,
		          f.floor
		   FROM rooms r
		   LEFT JOIN floor_plans f ON f.id = r.floor_plan_id   -- 還沒放上平面圖的教室也要列出
		   ORDER BY r.room_code"""
	)
	return render(request, "space_query/index.html", rooms=await cur.fetchall())


# ⚠ /admin 必須寫在 /{room_id} 前面：FastAPI 由上往下比對網址，
#    寫在後面的話 "admin" 會被當成 room_id 去轉整數而失敗
@router.get("/admin")
async def room_admin(request: Request, user: AdminUser):
	"""教室資料管理（管理員）。"""
	# TODO: 新增／修改／刪除教室
	return render(request, "space_query/admin.html")


@router.get("/{room_id}")
async def room_detail(room_id: int, request: Request, db: DB):
	"""單一空間的詳細資訊（公開）。"""
	cur = await db.execute(
		"""SELECT r.*, f.floor, f.image_url AS floor_plan_url
		   FROM rooms r
		   LEFT JOIN floor_plans f ON f.id = r.floor_plan_id
		   WHERE r.id = %s""",
		(room_id,),
	)
	room = await cur.fetchone()
	if room is None:
		raise HTTPException(status_code=404, detail="找不到這個空間")
	return render(request, "space_query/detail.html", room=room)
