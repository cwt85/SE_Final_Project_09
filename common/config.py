# common/config.py
# 集中管理設定：從專案根目錄的 .env 讀取，其他檔案都從這裡 import
import os
from pathlib import Path

from dotenv import load_dotenv

# 專案根目錄（common/ 的上一層）
BASE_DIR = Path(__file__).resolve().parent.parent

# 讀取 .env，把裡面的設定放進環境變數
load_dotenv(BASE_DIR / ".env")

# 資料庫連線字串；預設連到 docker-compose 啟動的資料庫（主機 port 5433）
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5433/ims")

# Session cookie 的簽章金鑰：用來防止使用者自己竄改 cookie 冒充別人
# 沒設定時用開發用的預設值，正式上線一定要在 .env 設定
SESSION_SECRET = os.getenv("SESSION_SECRET", "dev-only-insecure-secret")
