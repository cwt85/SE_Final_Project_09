# space_query/routes.py
# 模組①：管院空間查詢
# 網址都以 /spaces 開頭。瀏覽「不需要登入」；編輯教室資料要管理員。
from urllib.parse import quote

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from psycopg.errors import ForeignKeyViolation, UniqueViolation

from common.auth import AdminUser
from common.db import DB
from common.templating import render

router = APIRouter(prefix="/spaces", tags=["① 空間查詢"])


@router.get("")
async def room_list(request: Request, db: DB):
	"""空間列表（公開）。"""
	cur = await db.execute(
		"""SELECT r.id, r.room_code, r.name, r.room_type, r.capacity, r.is_bookable,
		          r.map_x, r.map_y, r.floor_plan_id,
		          f.floor
		   FROM rooms r
		   LEFT JOIN floor_plans f ON f.id = r.floor_plan_id   -- 還沒放上平面圖的教室也要列出
		   ORDER BY r.room_code"""
	)
	rooms = await cur.fetchall()

	fp_cur = await db.execute(
		"""SELECT id, building, floor, image_url
		   FROM floor_plans
		   ORDER BY floor"""
	)
	floor_plans = await fp_cur.fetchall()

	return render(
		request,
		"space_query/index.html",
		rooms=rooms,
		floor_plans=floor_plans,
	)


# ⚠ 所有 /admin 相關的網址必須寫在 /{room_id} 前面：
#    FastAPI 由上往下比對網址，寫在後面的話 "admin" 會被當成 room_id 去轉整數而失敗
@router.get("/admin")
async def room_admin(
	request: Request,
	user: AdminUser,
	db: DB,
	msg: str | None = None,
	error: str | None = None,
):
	"""教室資料管理列表（管理員）。"""
	cur = await db.execute(
		"""SELECT r.id, r.room_code, r.name, r.room_type, r.capacity, r.is_bookable,
		          r.map_x, r.map_y,
		          f.floor
		   FROM rooms r
		   LEFT JOIN floor_plans f ON f.id = r.floor_plan_id
		   ORDER BY r.room_code"""
	)
	rooms = await cur.fetchall()
	return render(
		request,
		"space_query/admin.html",
		rooms=rooms,
		msg=msg,
		error=error,
	)


@router.get("/admin/new")
async def room_new_page(request: Request, user: AdminUser, db: DB):
	"""新增空間表單頁（管理員）。"""
	fp_cur = await db.execute("SELECT id, building, floor, image_url FROM floor_plans ORDER BY floor")
	floor_plans = await fp_cur.fetchall()
	return render(
		request,
		"space_query/form.html",
		room=None,
		floor_plans=floor_plans,
	)


@router.post("/admin/new")
async def room_new(
	request: Request,
	user: AdminUser,
	db: DB,
	room_code: str = Form(...),
	name: str = Form(...),
	room_type: str = Form("classroom"),
	capacity: int | None = Form(None),
	is_bookable: str | None = Form(None),
	equipment: str = Form(""),
	description: str = Form(""),
	panorama_url: str = Form(""),
	floor_plan_id: str = Form(""),
	map_x: str = Form(""),
	map_y: str = Form(""),
):
	"""處理新增空間（管理員）。"""
	fp_id = int(floor_plan_id.strip()) if floor_plan_id.strip() else None
	mx = float(map_x.strip()) if map_x.strip() else None
	my = float(map_y.strip()) if map_y.strip() else None
	bookable_val = (is_bookable == "true")

	form_data = {
		"room_code": room_code.strip(),
		"name": name.strip(),
		"room_type": room_type,
		"capacity": capacity,
		"is_bookable": bookable_val,
		"equipment": equipment.strip(),
		"description": description.strip(),
		"panorama_url": panorama_url.strip(),
		"floor_plan_id": fp_id,
		"map_x": mx,
		"map_y": my,
	}

	error = None
	if not form_data["room_code"] or not form_data["name"]:
		error = "空間編號與空間名稱不可為空白！"

	if error is None:
		try:
			await db.execute(
				"""INSERT INTO rooms (
				       room_code, name, room_type, capacity, equipment,
				       description, panorama_url, floor_plan_id, map_x, map_y, is_bookable
				   ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
				(
					form_data["room_code"],
					form_data["name"],
					form_data["room_type"],
					form_data["capacity"],
					form_data["equipment"] or None,
					form_data["description"] or None,
					form_data["panorama_url"] or None,
					form_data["floor_plan_id"],
					form_data["map_x"],
					form_data["map_y"],
					form_data["is_bookable"],
				),
			)
			return RedirectResponse("/spaces/admin?msg=" + quote(f"已成功新增空間 {form_data['room_code']}"), status_code=303)
		except UniqueViolation:
			error = f"空間代號「{form_data['room_code']}」已經存在，請使用其他代號！"

	fp_cur = await db.execute("SELECT id, building, floor, image_url FROM floor_plans ORDER BY floor")
	floor_plans = await fp_cur.fetchall()
	return render(
		request,
		"space_query/form.html",
		status_code=400,
		room=None,
		floor_plans=floor_plans,
		form=form_data,
		error=error,
	)


@router.get("/admin/{room_id}/edit")
async def room_edit_page(room_id: int, request: Request, user: AdminUser, db: DB):
	"""編輯空間表單頁（管理員）。"""
	cur = await db.execute("SELECT * FROM rooms WHERE id = %s", (room_id,))
	room = await cur.fetchone()
	if room is None:
		raise HTTPException(status_code=404, detail="找不到這個空間")

	fp_cur = await db.execute("SELECT id, building, floor, image_url FROM floor_plans ORDER BY floor")
	floor_plans = await fp_cur.fetchall()

	return render(
		request,
		"space_query/form.html",
		room=room,
		floor_plans=floor_plans,
	)


@router.post("/admin/{room_id}/edit")
async def room_edit(
	room_id: int,
	request: Request,
	user: AdminUser,
	db: DB,
	room_code: str = Form(...),
	name: str = Form(...),
	room_type: str = Form("classroom"),
	capacity: int | None = Form(None),
	is_bookable: str | None = Form(None),
	equipment: str = Form(""),
	description: str = Form(""),
	panorama_url: str = Form(""),
	floor_plan_id: str = Form(""),
	map_x: str = Form(""),
	map_y: str = Form(""),
):
	"""處理修改空間（管理員）。"""
	fp_id = int(floor_plan_id.strip()) if floor_plan_id.strip() else None
	mx = float(map_x.strip()) if map_x.strip() else None
	my = float(map_y.strip()) if map_y.strip() else None
	bookable_val = (is_bookable == "true")

	form_data = {
		"id": room_id,
		"room_code": room_code.strip(),
		"name": name.strip(),
		"room_type": room_type,
		"capacity": capacity,
		"is_bookable": bookable_val,
		"equipment": equipment.strip(),
		"description": description.strip(),
		"panorama_url": panorama_url.strip(),
		"floor_plan_id": fp_id,
		"map_x": mx,
		"map_y": my,
	}

	error = None
	if not form_data["room_code"] or not form_data["name"]:
		error = "空間編號與空間名稱不可為空白！"

	if error is None:
		try:
			await db.execute(
				"""UPDATE rooms
				   SET room_code = %s,
				       name = %s,
				       room_type = %s,
				       capacity = %s,
				       equipment = %s,
				       description = %s,
				       panorama_url = %s,
				       floor_plan_id = %s,
				       map_x = %s,
				       map_y = %s,
				       is_bookable = %s,
				       updated_at = now()
				   WHERE id = %s""",
				(
					form_data["room_code"],
					form_data["name"],
					form_data["room_type"],
					form_data["capacity"],
					form_data["equipment"] or None,
					form_data["description"] or None,
					form_data["panorama_url"] or None,
					form_data["floor_plan_id"],
					form_data["map_x"],
					form_data["map_y"],
					form_data["is_bookable"],
					room_id,
				),
			)
			return RedirectResponse("/spaces/admin?msg=" + quote(f"已成功更新空間 {form_data['room_code']}"), status_code=303)
		except UniqueViolation:
			error = f"空間代號「{form_data['room_code']}」已經有人使用，請換一個代號！"

	fp_cur = await db.execute("SELECT id, building, floor, image_url FROM floor_plans ORDER BY floor")
	floor_plans = await fp_cur.fetchall()
	return render(
		request,
		"space_query/form.html",
		status_code=400,
		room=form_data,
		floor_plans=floor_plans,
		error=error,
	)


@router.post("/admin/{room_id}/delete")
async def room_delete(room_id: int, request: Request, user: AdminUser, db: DB):
	"""處理刪除空間（管理員）。"""
	cur = await db.execute("SELECT room_code FROM rooms WHERE id = %s", (room_id,))
	row = await cur.fetchone()
	room_code = row["room_code"] if row else f"ID {room_id}"

	try:
		await db.execute("DELETE FROM rooms WHERE id = %s", (room_id,))
		return RedirectResponse("/spaces/admin?msg=" + quote(f"已成功刪除空間 {room_code}"), status_code=303)
	except ForeignKeyViolation:
		return RedirectResponse(
			"/spaces/admin?error=" + quote(f"無法刪除「{room_code}」：該教室已被預約或已排定課程。若不再開放，請透過「編輯」關閉「開放預約借用」。"),
			status_code=303,
		)


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
