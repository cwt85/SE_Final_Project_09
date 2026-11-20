# common/db.py
# 資料庫連線池：程式啟動時建立、關閉時釋放；每個請求透過 getDB 借一條連線。
#
# 支援兩種模式（見 common/config.py）：
#   本地模式 → 自己電腦的 Docker 資料庫
#   雲端模式 → AWS 共用資料庫（透過 SSH 通道）
# 每種模式各有一個連線池；getDB 依照 session 裡記錄的模式，決定從哪個池借連線。
# 各模組完全不用管現在是哪個模式，照常寫 db=Depends(getDB) 就好。
import asyncio
from contextlib import asynccontextmanager

from typing import Annotated

from fastapi import Depends, FastAPI, Request
from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool
from psycopg.rows import dict_row

from common.config import DATABASE_URLS, MODE_LOCAL

# 等不到連線多久就放棄（秒）。雲端沒開 SSH 通道時，5 秒後就會顯示錯誤頁，而不是一直轉圈
POOL_TIMEOUT = 5


def _make_pool(url: str) -> AsyncConnectionPool:
	return AsyncConnectionPool(
		conninfo=url,
		kwargs={"row_factory": dict_row},  # 查詢結果用 dict 回傳，例如 row["name"]
		# min_size=0：有請求才建立連線，閒置時不在背景一直嘗試連線
		# （雲端沒開 SSH 通道時，背景重試只會越等越久，見 reset_pool）
		min_size=0,
		max_size=5,
		timeout=POOL_TIMEOUT,
		# 借出連線前先確認它還活著（例如 SSH 通道斷過，舊連線就已經失效）；
		# 失效的會自動丟掉換新的，避免把壞掉的連線交給請求
		check=AsyncConnectionPool.check_connection,
		open=False,
	)


@asynccontextmanager
async def lifespan(app: FastAPI):
	# 只替有設定網址的模式建立連線池
	app.state.pools = {mode: _make_pool(url) for mode, url in DATABASE_URLS.items() if url}
	for mode, pool in app.state.pools.items():
		# wait=False：不等連線成功就繼續啟動，
		# 這樣雲端沒開 SSH 通道時，網站照樣能用本地模式啟動
		await pool.open(wait=False)
	print(f"✅ DB pools ready: {', '.join(app.state.pools)}")

	yield  # App runs here

	for pool in app.state.pools.values():
		await pool.close()
	print("🛑 Disconnected from DB")


async def reset_pool(app: FastAPI, mode: str) -> None:
	"""
	把某個模式的連線池換成全新的。連不上資料庫時由 main.py 的錯誤處理呼叫。

	為什麼要換新的？連線池連線失敗後會「越等越久才重試」（1、2、4、8… 秒），
	實測 SSH 通道恢復後要約 30 秒才連得回來。換一個新的池子就沒有累積的等待時間，
	通道一恢復，下一個請求馬上就能連上。
	"""
	old = app.state.pools.get(mode)
	new = _make_pool(DATABASE_URLS[mode])
	await new.open(wait=False)
	app.state.pools[mode] = new
	if old is not None:
		# 舊池子在背景慢慢關，不讓使用者等
		asyncio.create_task(old.close())


def available_modes(request: Request) -> list[str]:
	"""目前有設定的模式，例如 ["local", "cloud"]。"""
	return list(request.app.state.pools)


def get_mode(request: Request) -> str:
	"""目前這個使用者選的模式；沒選過或選的模式不能用，就用本地模式。"""
	mode = request.session.get("db_mode", MODE_LOCAL)
	return mode if mode in request.app.state.pools else MODE_LOCAL


# 依照目前模式，從對應的連線池借一條連線
# 函式順利結束會自動 commit；途中發生例外則自動 rollback
async def getDB(request: Request):
	pool = request.app.state.pools[get_mode(request)]
	async with pool.connection() as conn:
		yield conn


# ===== 各模組請用這個取得資料庫連線 =====
#   async def page(request: Request, db: DB):
#
# 為什麼不直接寫 db=Depends(getDB)？
# FastAPI 預設會在「回應已經送給瀏覽器之後」才結束 yield 型的 dependency，
# 也就是 commit 發生在使用者看到「成功」之後；萬一 commit 失敗（例如雲端網路斷線），
# 使用者以為存好了，資料其實沒存進去。
# scope="function" 讓 commit 在送出回應「之前」完成，失敗時使用者會看到錯誤頁。
DB = Annotated[AsyncConnection, Depends(getDB, scope="function")]
