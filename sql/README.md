# sql/ — 資料庫腳本

Docker 第一次建立資料庫時，會**依檔名順序**自動執行這個資料夾裡的 `.sql` 檔。

| 檔案 | 用途 |
|---|---|
| `01_schema.sql` | 建立所有資料表、索引、`room_occupancy` VIEW |
| `02_seed.sql` | 測試資料（帳號、空間、物品、借用單、課程） |

設計說明請看 [`docs/database.md`](../docs/database.md)。

## 修改後如何套用

這些腳本**只在資料庫第一次建立時執行**，改完要清空資料庫重建：

```bash
docker compose down -v   # -v 會連資料一起刪除
docker compose up -d
```

## 規則

- 修改 `01_schema.sql` 後，請同步更新 `docs/database.md`，並通知組員重建資料庫。
- 修改共用的表（`users`、`rooms`）前，請先在組內討論。
- 測試資料的日期請用 `date_trunc('week', CURRENT_DATE)::date + N` 的寫法（本週一往後 N 天），這樣不論哪天 demo，週曆上都看得到資料。
