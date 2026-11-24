# space_booking/ — 模組② 空間／物品預約借用

負責人：＿cwt85＿＿＿

讓登入的使用者預約教室並借用物品（鑰匙、投影筆、筆電…），由管理員審核、登記借出與歸還。

## 需求清單

- [x] 事先建置好測試用的空間資料（已在 `sql/02_seed.sql`，**不需實作空間的增刪改功能**）
- [x] 登入才能使用（整個 router 都已加上 `require_login`）
  - [x] 選擇空間，**以週為單位**列出當週該教室的借用狀況（排課、已核准借用、審核中三種顏色；可切換上／下週）
  - [x] 預約登記：空間編號、日期、時間區間、借用物品（**可多項**）
- [x] 管理員**審核通過或退件**，可加註審核意見
- [x] 領用／歸還
  - [x] 領用鑰匙與物品時，由管理員登記借出
  - [x] 歸還時由管理員確認並登記歸還
- [x] 可瀏覽借用紀錄（我的借用紀錄＋管理員「全部紀錄」，含審核／借出／歸還的經手人與時間）
- [x] **整合**：送出預約前用 `common.occupancy.find_conflicts` 檢查衝突，排課占用的時段也要擋下
- [x] 申請人可以取消自己「待審核」的借用單

## 檔案說明

| 檔案 | 用途 |
|---|---|
| `routes.py` | 這個模組的所有網址（`/booking` 開頭） |
| `templates/space_booking/` | 這個模組的頁面 |
| `static/booking.css` | 週曆、管理頁的樣式，網址是 `/static/space_booking/booking.css`（**新增 static 資料夾後要重啟伺服器**） |

## 網址

| 網址 | 說明 | 權限 | 狀態 |
|---|---|---|---|
| `GET /booking` | 我的借用紀錄 | 登入 | ✅ |
| `POST /booking/{id}/cancel` | 取消自己的待審核借用單 | 登入（本人） | ✅ |
| `GET /booking/new?room_id=&week=` | 預約表單＋該空間當週週曆（空間查詢頁會帶 `room_id` 過來；`week` 是該週任一天） | 登入 | ✅ |
| `POST /booking/new` | 送出預約 | 登入 | ✅ |
| `GET /booking/admin?tab=` | 審核、借出、歸還（`tab` = `pending`／`approved`／`checked_out`／`all`） | 管理員 | ✅ |
| `POST /booking/admin/{id}/review` | 審核：`action=approve`／`reject`，`comment` 選填 | 管理員 | ✅ |
| `POST /booking/admin/{id}/checkout` | 登記借出 | 管理員 | ✅ |
| `POST /booking/admin/{id}/return` | 登記歸還 | 管理員 | ✅ |

## 使用的資料表

本模組**負責** `items`、`bookings`、`booking_items`；**只讀** `rooms`、`users`。
欄位說明見 [`docs/database.md`](../docs/database.md) 第 4.4–4.6 節。

## 借用單狀態流程

```
                    ┌──退件──→ rejected
申請 → pending ─────┤
         │          └──通過──→ approved ──領用──→ checked_out ──歸還──→ returned
         └──申請人取消──→ cancelled
```

每次改變狀態時，記得一起填寫對應的欄位：

| 動作 | 更新的欄位 |
|---|---|
| 審核 | `status`、`review_comment`、`reviewed_by`、`reviewed_at` |
| 借出 | `status = 'checked_out'`、`checked_out_by`、`checked_out_at` |
| 歸還 | `status = 'returned'`、`returned_by`、`returned_at` |

## 實作提示

- **一次新增借用單和物品**：先 `INSERT INTO bookings ... RETURNING id` 拿到新的 id，再逐一新增 `booking_items`。同一個請求裡的 SQL 會在同一個交易中，任何一步失敗都會全部取消，不會只存一半。
- **衝突檢查要在後端做**：前端週曆顯示「已占用」只是方便使用者看，送出時後端一定要再用 `find_conflicts` 檢查一次。
- **只有 `approved`、`checked_out` 算占用教室**：`pending` 不算，所以兩個人可能同時申請同一時段。審核通過前也要再檢查一次衝突。

## 規則與資料格式（實作時的決定）

| 項目 | 規則 |
|---|---|
| 開放時間 | 07:00–22:00（`routes.py` 的 `OPEN_TIME`／`CLOSE_TIME`），週曆也只畫這段 |
| 日期／時間 | 表單字串先轉成 Python `date`／`time` 再交給資料庫；秒數一律捨去 |
| 「現在」 | 向資料庫問 `now() AT TIME ZONE 'Asia/Taipei'`，不用伺服器電腦的時鐘；不能預約已過去的時段 |
| 時間戳記 | `reviewed_at` 等 `TIMESTAMPTZ` 欄位一律在 SQL 用 `now()` 寫入，顯示時轉成台灣時間 |
| 不開放的空間 | `rooms.is_bookable = FALSE`（例如 M203）不會出現在選單，也無法送出 |
| 鑰匙 | 只能借「這間教室」的鑰匙（`items.room_id` 要等於借用空間） |
| 物品數量 | 1 ～ `total_quantity`；填空白或 0 = 不借（`booking_items` 有 `CHECK (quantity > 0)`） |
| 物品是否夠借 | 申請與審核時：同一天、時間重疊、`approved`／`checked_out` 的單合計不能超過總數 |
| 登記借出時 | 另外檢查「實體庫存」：其他 `checked_out` 還沒歸還的單（不論哪天）都占著物品 |
| 狀態只能照流程走 | 每個 `UPDATE` 都在 `WHERE` 檢查目前狀態，例如 `WHERE status = 'pending'` |
| 同時操作 | 新增／審核／借出前先取得 `pg_advisory_xact_lock`，兩個管理員同時核准衝突的單，只會有一張成功 |
