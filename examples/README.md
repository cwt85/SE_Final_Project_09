# examples/ — 老師提供的範例程式（僅供參考）

這些是課程提供的教學範例，**不屬於正式專案**，也不會被 `main.py` 載入。

| 檔案 | 示範內容 | 正式專案中對應的位置 |
|---|---|---|
| `main.py` | 資料庫查詢、模板、CRUD（students 表） | 各模組的 `routes.py` |
| `sessionLogin.py` | 用 session 做登入 | `common/auth.py`、`common/routes.py` |
| `routerUse.py` | 用 `APIRouter` 拆分網址 | 各模組的 `routes.py` + 根目錄 `main.py` |
| `0.readme.txt` | 範例的原始說明 | — |

> ⚠ 這裡的程式**無法直接執行**：`students` 資料表已經被正式 schema 取代，而且範例引用的 `routes/r.py`、`templates/` 等資料夾也不存在。
