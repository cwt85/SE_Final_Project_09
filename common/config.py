# common/config.py
# 集中管理設定：從專案根目錄的 .env 讀取，其他檔案都從這裡 import
import os
from pathlib import Path

from dotenv import load_dotenv

# 專案根目錄（common/ 的上一層）
BASE_DIR = Path(__file__).resolve().parent.parent

# 讀取 .env，把裡面的設定放進環境變數（已存在的環境變數不會被覆蓋）
load_dotenv(BASE_DIR / ".env")

# ---------- 資料庫模式 ----------
# 本地模式：連自己電腦上的 Docker 資料庫，單純測試用，資料只有自己看得到
# 雲端模式：連 AWS 上的共用資料庫，資料會真的寫進去，全組共用
MODE_LOCAL = "local"
MODE_CLOUD = "cloud"
MODE_LABELS = {MODE_LOCAL: "本地模式", MODE_CLOUD: "雲端模式"}

DATABASE_URLS = {
	# 本地：沿用 DATABASE_URL 這個名稱，預設連 docker-compose 的資料庫（port 5433）
	MODE_LOCAL: os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5433/ims"),
	# 雲端：沒設定就是 None，登入頁的雲端選項會變成無法選擇
	MODE_CLOUD: os.getenv("CLOUD_DATABASE_URL") or None,
}

# Session cookie 的簽章金鑰：用來防止使用者自己竄改 cookie 冒充別人
# 沒設定時用開發用的預設值，正式上線一定要在 .env 設定
SESSION_SECRET = os.getenv("SESSION_SECRET", "dev-only-insecure-secret")
