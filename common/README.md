# common/ — 共用模組

三個模組**都會用到**的東西放這裡：資料庫連線、登入與權限、帳號註冊與審核、共用版面、教室占用查詢。

> ⚠ 這個資料夾的修改會影響所有人。改之前請先在群組說一聲，改完請通知大家 `git pull`。

## 檔案說明

| 檔案 | 用途 |
|---|---|
| `config.py` | 讀取 `.env` 的設定（`DATABASE_URL`、`SESSION_SECRET`） |
| `db.py` | 資料庫連線池；`getDB` 給 `Depends` 使用 |
| `auth.py` | 密碼雜湊、登入狀態、權限檢查（`require_login`、`require_admin`、`require_teacher`） |
| `templating.py` | 共用的 Jinja2 設定；`render()` 會自動把登入者放進模板 |
| `occupancy.py` | **整合用**：教室占用與時段衝突查詢，借用和排課模組都要用 |
| `routes.py` | 共用網址：首頁、登入、登出、註冊、帳號審核 |
| `templates/common/` | `base.html`（導覽列和版面）、登入、註冊、帳號管理、錯誤頁 |
| `static/style.css` | 全站共用樣式 |

## 共用網址

| 網址 | 說明 | 權限 |
|---|---|---|
| `GET /` | 首頁 | 公開 |
| `GET/POST /login` | 登入（`?next=` 登入後跳回原頁） | 公開 |
| `GET /logout` | 登出 | 公開 |
| `GET/POST /register` | 註冊（新帳號是「待審核」狀態） | 公開 |
| `GET /admin/users` | 帳號列表與審核 | 管理員 |
| `POST /admin/users/{id}/status` | 核准／退回／停用 | 管理員 |
| `POST /admin/users/{id}/role` | 修改角色 | 管理員 |

## 在你的模組裡怎麼用

### 1. 權限檢查

```python
from fastapi import APIRouter, Depends, Request
from common.auth import require_login, require_admin, require_teacher
from common.db import getDB
from common.templating import render

router = APIRouter(prefix="/xxx")

@router.get("/page")
async def page(request: Request, user=Depends(require_login), db=Depends(getDB)):
    # 能執行到這裡，代表一定已經登入
    # user = {"id": 4, "username": "student1", "full_name": "陳同學", "role": "user"}
    cur = await db.execute("SELECT * FROM rooms WHERE id = %s", (1,))
    room = await cur.fetchone()
    return render(request, "xxx/page.html", room=room)
```

| 寫法 | 誰可以進來 | 不符合時 |
|---|---|---|
| `Depends(require_login)` | 任何已登入的人 | 導向登入頁，登入後跳回來 |
| `Depends(require_teacher)` | 老師、管理員 | 403 錯誤頁 |
| `Depends(require_admin)` | 管理員 | 403 錯誤頁 |
| `current_user(request)` | 不檢查，回傳使用者或 `None` | — |

> **畫面上把按鈕藏起來不等於安全**，有人可以直接輸入網址。每個需要權限的網址都一定要加 `Depends(...)`。

### 2. 模板

所有頁面都繼承 `common/base.html`，這樣導覽列就會自動出現：

```jinja
{% extends "common/base.html" %}
{% block title %}頁面標題{% endblock %}
{% block head %}<link rel="stylesheet" href="/static/你的模組/xxx.css">{% endblock %}
{% block content %}
  <h1>內容</h1>
  {% if user %}哈囉 {{ user.full_name }}{% endif %}
{% endblock %}
{% block scripts %}<script src="/static/你的模組/xxx.js"></script>{% endblock %}
```

可以直接用的 CSS class：`button`、`table-wrap`、`alert alert-ok`、`alert alert-error`、`badge badge-<狀態>`、`muted`、`todo`。

### 3. 教室占用與衝突檢查（借用、排課必用）

```python
from common.occupancy import find_conflicts, get_week_occupancy, week_range

# 新增借用前檢查衝突；回傳空 list = 沒衝突
conflicts = await find_conflicts(db, room_id, day, start, end)

# 修改既有資料時要排除自己，否則會跟自己衝突
conflicts = await find_conflicts(db, room_id, day, start, end,
                                 exclude_source="course", exclude_id=session_id)

# 某教室某一週的所有占用（借用＋排課），畫週曆用
rows = await get_week_occupancy(db, room_id, some_date)
```

## 常見陷阱

- **SQL 欄位不要取名叫 `items`、`keys`、`values`、`get`、`update`。** 查詢結果是 Python 的 dict，這些名字剛好是 dict 內建的方法，模板裡寫 `row.items` 會拿到方法而不是資料。要用的話請用 `AS` 改名，例如 `AS item_list`。
- **SQL 一律用參數**（`%s`），不要用 f-string 把變數拼進 SQL，否則會有 SQL injection 漏洞。
- **表單送出後用 `RedirectResponse(..., status_code=303)` 導回列表頁**，避免使用者按 F5 時重複送出。
- **Session 裡的使用者資料是登入當下的快照。** 管理員改了某人的角色，那個人要重新登入才會生效。
