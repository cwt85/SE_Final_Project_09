# 管院空間系統（軟體工程期末專案）

三個模組：① 管院空間查詢　② 空間／物品預約借用　③ 課程排課
技術：FastAPI + Jinja2 + PostgreSQL，套件管理用 uv。
資料庫設計請看 [`docs/database.md`](docs/database.md)。

---

## 專案結構

```
project_code/
├── main.py              # 程式進入點：只負責把各模組組裝起來
├── common/              # 共用：DB 連線、登入/權限、註冊/審核、共用版面、占用查詢
├── space_query/         # 模組① 管院空間查詢   → /spaces
├── space_booking/       # 模組② 空間/物品借用   → /booking
├── course_schedule/     # 模組③ 課程排課       → /schedule
├── sql/                 # 建表與測試資料（Docker 自動執行）
├── docs/                # 設計文件
├── examples/            # 老師的範例程式（不會被執行）
├── docker-compose.yml   # 資料庫 + Adminer
└── .env                 # 密碼等設定（不進 git，從 .env.example 複製）
```

每個資料夾都有自己的 `README.md`，說明用途、需求清單和實作提示。

每個模組資料夾的結構都一樣：

```
模組名稱/
├── README.md                 # 需求清單、網址、使用的資料表
├── routes.py                 # 這個模組的所有網址
├── templates/模組名稱/*.html  # 頁面（多一層模組名稱，避免和別人的 index.html 撞名）
└── static/                   # CSS/JS/圖片 → /static/模組名稱/...
```

### 分工規則

1. **只改自己的模組資料夾**。要改 `common/`、`main.py`、`sql/01_schema.sql` 時，先在群組說一聲。
2. 登入檢查一律用 `common/auth.py` 提供的 `require_login`、`require_admin`，不要自己另外寫。
3. 每個人都要有自己的 commit 紀錄（這是評分項目），請小量、常常 commit。

---

## 環境需求

- [Docker Desktop](https://www.docker.com/products/docker-desktop/)（跑資料庫）
- [uv](https://docs.astral.sh/uv/)（跑 Python）

## 第一次設定

```bash
# 1. 建立自己的設定檔，然後打開 .env 改密碼
#    POSTGRES_PASSWORD 和 DATABASE_URL 裡的密碼要一致
cp .env.example .env

# 2. 啟動資料庫（第一次會下載 image，需要一點時間）
docker compose up -d

# 3. 安裝 Python 套件
uv sync
```

第一次啟動資料庫時，Docker 會依檔名順序自動執行 `sql/` 資料夾裡的腳本：

1. `01_schema.sql`：建立資料表
2. `02_seed.sql`：放入測試資料

## 常用指令

| 想做的事 | 指令 |
|---|---|
| 啟動資料庫 | `docker compose up -d` |
| 停止資料庫（資料保留） | `docker compose stop` |
| 看資料庫狀態 | `docker compose ps` |
| 看資料庫 log | `docker compose logs db` |
| 用指令列操作資料庫 | `docker compose exec db psql -U postgres -d ims` |
| **清空並重建資料庫** | `docker compose down -v` 然後 `docker compose up -d` |
| 啟動網站 | `uv run fastapi dev main.py`，然後開 <http://127.0.0.1:8000> |

> **Windows 注意**：請用 `fastapi dev` 啟動。`fastapi run` 在 Windows 上會出現 `ProactorEventLoop` 錯誤，這是 psycopg 的限制，部署到 Linux 主機則不受影響。

> **改了 `sql/` 裡的檔案，資料庫卻沒變？**
> 因為初始化腳本**只在資料庫第一次建立時執行一次**。資料存在 Docker volume 裡，之後重新啟動不會再跑。
> 要套用新的 SQL，就用上表的「清空並重建資料庫」（`-v` 代表連 volume 一起刪掉，**資料會全部消失**）。

## 連線資訊

| 項目 | 值 |
|---|---|
| Host / Port（從你的電腦連） | `localhost` / `5433` |
| 資料庫名稱 | `ims` |
| 帳號 | `postgres` |
| 密碼 | `.env` 裡的 `POSTGRES_PASSWORD` |
| Adminer（網頁管理介面） | <http://localhost:8080>，System 選 PostgreSQL，Server 填 `db` |

> port 用 **5433** 而不是預設的 5432，是為了避開電腦上原本安裝的 PostgreSQL。

## 測試帳號

| 帳號 | 密碼 | 角色 |
|---|---|---|
| `admin` | `admin123` | 管理員 |
| `teacher1` / `teacher2` | `teacher1123` / `teacher2123` | 老師 |
| `student1` / `student2` | `student1123` / `student2123` | 一般使用者 |
| `newbie` | `newbie123` | 待審核（還不能登入） |
