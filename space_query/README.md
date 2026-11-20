# space_query/ — 模組① 管院空間查詢

負責人：＿＿s113213005-droid＿＿＿＿

讓任何人（**不需登入**）瀏覽管院的空間資訊，包含 360° 全景照片和平面圖位置；管理員可以維護教室資料。

## 需求清單

- [ ] 管理員帳號可以**新增、刪除、修改**教室資料
  - 教室基本資訊參考：<https://www.ibs.ncnu.edu.tw/index.php/resources/space-classroom>
- [x] 不需登入就可以查詢、瀏覽空間資訊（列表、詳細頁已完成基本版）
  - [ ] 360° 全景照片瀏覽，使用 [Pannellum](https://pannellum.org/)
  - [ ] 管院平面圖，標示教室位置
- [ ] **整合**：詳細頁的「預約這個空間」按鈕會連到 `/booking/new?room_id=`（按鈕已放好）

## 檔案說明

| 檔案 | 用途 |
|---|---|
| `routes.py` | 這個模組的所有網址（`/spaces` 開頭） |
| `templates/space_query/` | 這個模組的頁面 |
| `static/floorplans/` | 各樓層平面圖，網址是 `/static/space_query/floorplans/檔名` |
| `static/panoramas/` | 360° 全景照片，網址是 `/static/space_query/panoramas/檔名` |

## 網址

| 網址 | 說明 | 權限 | 狀態 |
|---|---|---|---|
| `GET /spaces` | 空間列表 | 公開 | 基本版 ✅ |
| `GET /spaces/{id}` | 空間詳細資訊 | 公開 | 基本版 ✅ |
| `GET /spaces/admin` | 教室資料管理 | 管理員 | TODO |

## 使用的資料表

本模組**負責維護** `rooms`、`floor_plans`。欄位說明見 [`docs/database.md`](../docs/database.md) 第 4.2、4.3 節。

> `rooms` 是三個模組共用的表。如果要**新增或修改欄位**，請先和組員討論，並同步修改 `sql/01_schema.sql`。

## 實作提示

- **平面圖標示**：`map_x`、`map_y` 存的是百分比（0–100）。做法是把平面圖放進一個 `position: relative` 的容器，每個教室用一個 `position: absolute; left: {{ room.map_x }}%; top: {{ room.map_y }}%` 的標記疊在圖上，這樣不論螢幕大小，標記都會對準位置。
- **Pannellum**：在模板的 `{% block head %}` 載入它的 CSS 和 JS，然後：
  ```js
  pannellum.viewer('panorama', { type: 'equirectangular', panorama: '{{ room.panorama_url }}', autoLoad: true });
  ```
- **刪除教室要小心**：已經有借用單或排課的教室，資料庫的外鍵會擋住刪除。可以改用 `is_bookable = FALSE`，讓它不再開放借用就好。
