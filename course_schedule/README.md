# course_schedule/ — 模組③ 課程排課

負責人：＿＿＿wenyufennn＿＿＿

讓老師登記想排課的時段（課程、日期、時段、希望的教室），以週曆檢視所有排課；管理員可以調整所有課程、查看衝突、用拖拉的方式改時間。

## 需求清單

- [x] 登入才能使用（整個 router 都已加上 `require_login`）
- [x] 老師可以登記想要排課的時段（課程、日期、區間、希望的教室）
  - [x] 新增課程、修改課程、刪除課程
  - [x] 以清單方式列出自己的課程
  - [x] **只能調整自己的課程** 
  - [x] 管理員可以增刪調整所有課程，並將課程**指派給老師**
(備註：指派功能：管理員編輯頁面多一個 授課老師 欄位，老師的頁面後沒有這個欄位)
- [x] 可以用**週曆**形式檢視所有目前排課的狀態
(備註：course_schedule/routes.py中的_ensure_enroll_table函式，是學生端的額外功能，用來儲存學生自己選課的資料，學生只能看到自己選的課。
      雲端資料庫帳號若無建表權限，需請cwt在common資料夾的資料庫中額外手動建立)
- [x] 管理員可以列出所有老師課程中**時間衝突**的課程清單
- [x] 管理員可以透過滑鼠 **drag & drop** 修改課程的日期時間
- [x] **整合**：週曆上同時顯示該教室的借用占用（`common.occupancy.get_week_occupancy`）

## 檔案說明

| 檔案 | 用途 |
|---|---|
| `routes.py` | 這個模組的所有網址（`/schedule` 開頭） |
| `templates/course_schedule/` | 這個模組的頁面 |
| `static/` | （需要時自己建立）放 CSS／JS，網址是 `/static/course_schedule/檔名`，**新增資料夾後要重啟伺服器** |

## 網址

| 網址 | 說明 | 權限 | 狀態 |
|---|---|---|---|
| `GET /schedule` | 課程清單（老師：自己的；管理員：全部） | 登入 | 基本版 ✅ |
| `GET /schedule/calendar` | 排課週曆 | 登入 | TODO |
| `GET /schedule/conflicts` | 衝突清單 | 管理員 | TODO |

## 使用的資料表

本模組**負責** `courses`、`course_sessions`；**只讀** `rooms`、`users`。
欄位說明見 [`docs/database.md`](../docs/database.md) 第 4.7、4.8 節。

- **課程**（`courses`）：課名、授課老師。「指派給老師」就是修改 `teacher_id`。
- **上課時段**（`course_sessions`）：每一次上課一列。drag & drop 改時間，就是更新某一列的 `session_date`、`start_time`、`end_time`。

## 實作提示

- **「只能調整自己的課程」一定要在後端檢查**：修改或刪除前先查出那門課，確認 `course.teacher_id == user["id"]` 或 `user["role"] == "admin"`，否則回 403。不能只靠畫面上把按鈕藏起來。
- **衝突清單的 SQL** 已經寫好並測試過，在 [`docs/database.md`](../docs/database.md) 第 5.3 節。測試資料裡刻意放了兩組衝突（教室衝突、老師衝堂）。
- **週曆和 drag & drop** 建議用 [FullCalendar](https://fullcalendar.io/)（`timeGridWeek` 檢視、`editable: true`）。拖拉結束時會觸發 `eventDrop`，在裡面用 `fetch()` 把新的日期時間 POST 到後端（例如 `POST /schedule/sessions/{id}/move`），後端回傳 JSON 即可。
- **每週重複的課**：新增課程時提供「每週重複 N 週」，後端用迴圈一次新增 N 列 `course_sessions`。
- 排課**允許**時段衝突（老師填的是「希望」），由管理員事後看衝突清單再調整，所以新增時不要擋，但可以顯示警告。
