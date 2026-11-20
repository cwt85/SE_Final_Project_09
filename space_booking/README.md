# space_booking/ — 模組② 空間／物品預約借用

負責人：＿cwt85＿＿＿

讓登入的使用者預約教室並借用物品（鑰匙、投影筆、筆電…），由管理員審核、登記借出與歸還。

## 需求清單

- [x] 事先建置好測試用的空間資料（已在 `sql/02_seed.sql`，**不需實作空間的增刪改功能**）
- [x] 登入才能使用（整個 router 都已加上 `require_login`）
  - [ ] 選擇空間，**以週為單位**列出當週該教室的借用狀況
  - [ ] 預約登記：空間編號、日期、時間區間、借用物品（**可多項**）
- [ ] 管理員**審核通過或退件**，可加註審核意見
- [ ] 領用／歸還
  - [ ] 領用鑰匙與物品時，由管理員登記借出
  - [ ] 歸還時由管理員確認並登記歸還
- [x] 可瀏覽借用紀錄（「我的借用紀錄」已完成基本版）
- [ ] **整合**：送出預約前用 `common.occupancy.find_conflicts` 檢查衝突，排課占用的時段也要擋下

## 檔案說明

| 檔案 | 用途 |
|---|---|
| `routes.py` | 這個模組的所有網址（`/booking` 開頭） |
| `templates/space_booking/` | 這個模組的頁面 |
| `static/` | （需要時自己建立）放 CSS／JS，網址是 `/static/space_booking/檔名`，**新增資料夾後要重啟伺服器** |

## 網址

| 網址 | 說明 | 權限 | 狀態 |
|---|---|---|---|
| `GET /booking` | 我的借用紀錄 | 登入 | 基本版 ✅ |
| `GET /booking/new?room_id=` | 預約表單（空間查詢頁會帶 `room_id` 過來） | 登入 | TODO |
| `GET /booking/admin` | 審核、借出、歸還 | 管理員 | TODO |

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
