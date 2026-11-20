# common/db.py
# 資料庫連線池：程式啟動時建立、關閉時釋放；每個請求透過 getDB 借一條連線
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from psycopg_pool import AsyncConnectionPool
from psycopg.rows import dict_row

from common.config import DATABASE_URL


# Lifespan context manager for FastAPI：程式啟動時建立連線池，關閉時釋放
@asynccontextmanager
async def lifespan(app: FastAPI):
	app.state.pool = AsyncConnectionPool(
		conninfo=DATABASE_URL,
		kwargs={"row_factory": dict_row},  # 查詢結果用 dict 回傳，例如 row["name"]
		open=False,
	)
	await app.state.pool.open()
	print("✅ Connected to DB")

	yield  # App runs here

	# Shutdown logic
	await app.state.pool.close()
	print("🛑 Disconnected from DB")


# 給 FastAPI 的 Depends 使用：每個請求從連線池借一條連線
# 請求順利結束會自動 commit；途中發生例外則自動 rollback
async def getDB(request: Request):
	async with request.app.state.pool.connection() as conn:
		yield conn
