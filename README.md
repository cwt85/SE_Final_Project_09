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
2. 登入檢查和資料庫連線一律用 `common/` 提供的 `user: LoginUser`／`user: AdminUser`、`db: DB`，不要自己另外寫（用法見 [`common/README.md`](common/README.md)）。
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

## 本地模式與雲端模式

登入頁上方有切換開關，導覽列右上角會一直顯示目前的模式。

| | 本地模式 | 雲端模式 |
|---|---|---|
| 資料庫 | 自己電腦的 Docker（port 5433） | AWS 主機上的 PostgreSQL（透過 SSH 通道，port 5434） |
| 用途 | 開發、測試，資料只有自己看得到 | **資料會真的寫入**，全組共用、demo 用 |
| 需要 | `docker compose up -d` | SSH 通道 + `.env` 的 `CLOUD_DATABASE_URL` |

- **切換模式會自動登出**：兩邊是不同的資料庫，同一個 id 可能是不同的人。
- 兩邊的測試帳號一樣（見下方），但之後各自新增的資料互不相通。

### 使用雲端模式

AWS 上的資料庫**不對外開放**，只能從主機內部連。所以要先開一條 SSH 通道，把你電腦的 port 5434 接到主機內部的 PostgreSQL：

```bash
# 開一個新的終端機執行，開著不要關（關掉就連不上）
ssh -N -L 5434:127.0.0.1:5432 <帳號>@<AWS 主機 IP> -i <你的 key>
```

主機帳號（依模組分配）：

| 模組 | 主機帳號 |
|---|---|
| ① 空間查詢 | `s113213005-droid` |
| ③ 課程排課 | `wenyufennn` |

然後在 `.env` 加上（密碼和主機資訊請向組長索取，**不要 commit**）：

```
CLOUD_DATABASE_URL=postgresql://ims:<密碼>@localhost:5434/ims
```

重新啟動網站後，登入頁就能選「雲端模式」。如果通道沒開，頁面會顯示「連不上雲端資料庫」；把通道開起來後重新整理就會恢復，**不用重啟網站**。

### 組員的主機帳號能做什麼

為了安全，組員帳號的權限被限制在最小範圍：

| 可以 | 不可以 |
|---|---|
| 開 SSH 通道連 PostgreSQL（上面的指令） | 登入 shell、執行任何指令、sudo |
| 用 SFTP 上傳／下載 demo 目錄的檔案 | 看到 demo 目錄以外的任何檔案 |
| 刪除、替換 demo 目錄裡任何人的檔案 | 轉接到 PostgreSQL 以外的服務 |

```bash
# 用 SFTP 管理 demo 目錄（登入後就在 /demo）
sftp -i <你的私鑰> <帳號>@<AWS 主機 IP>
```

> 用 SFTP 上傳的檔案，其他組員**不能直接覆寫**，但可以先刪除再重新上傳。

## 測試帳號

| 帳號 | 密碼 | 角色 |
|---|---|---|
| `admin` | `admin123` | 管理員 |
| `teacher1` / `teacher2` | `teacher1123` / `teacher2123` | 老師 |
| `student1` / `student2` | `student1123` / `student2123` | 一般使用者 |
| `newbie` | `newbie123` | 待審核（還不能登入） |
