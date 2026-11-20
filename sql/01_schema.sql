-- =========================================================
-- 01_schema.sql：管院空間系統的資料表結構（PostgreSQL 18）
-- 設計說明請看 docs/database.md
--
-- Docker 第一次啟動時會自動執行（檔名 01_ 讓它比 02_seed 先跑）
-- 手動執行：psql -U postgres -d ims -f sql/01_schema.sql
-- ⚠ 會先刪除所有舊資料表，正式資料請勿執行
-- =========================================================

-- pgcrypto 提供 crypt()/gen_salt()，讓測試資料可以直接產生 bcrypt 密碼雜湊
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- 刪除順序與建立順序相反，避免外鍵擋住
DROP VIEW  IF EXISTS room_occupancy;
DROP TABLE IF EXISTS course_sessions, courses,
                     booking_items, bookings, items,
                     rooms, floor_plans, users CASCADE;

-- ---------- 共用：使用者 ----------
CREATE TABLE users (
    id            INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,  -- 自動編號
    username      VARCHAR(50)  NOT NULL UNIQUE,                       -- 登入帳號不可重複
    password_hash TEXT         NOT NULL,                              -- 只存 bcrypt 雜湊值
    full_name     VARCHAR(50)  NOT NULL,
    email         VARCHAR(100),
    role          TEXT NOT NULL DEFAULT 'user'
                  CHECK (role IN ('admin', 'teacher', 'user')),
    status        TEXT NOT NULL DEFAULT 'pending'                     -- 新註冊預設待審核
                  CHECK (status IN ('pending', 'active', 'rejected', 'disabled')),
    approved_by   INTEGER REFERENCES users(id),                       -- 審核的管理員
    approved_at   TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------- 模組①：平面圖 ----------
CREATE TABLE floor_plans (
    id        INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    building  VARCHAR(50) NOT NULL DEFAULT '管理學院',
    floor     SMALLINT    NOT NULL,                                   -- 地下室用負數
    image_url TEXT        NOT NULL,
    UNIQUE (building, floor)                                          -- 同館同層只有一張圖
);

-- ---------- 共用：空間 ----------
CREATE TABLE rooms (
    id            INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    room_code     VARCHAR(20)  NOT NULL UNIQUE,                       -- 例如 M101
    name          VARCHAR(100) NOT NULL,
    room_type     TEXT NOT NULL DEFAULT 'classroom'
                  CHECK (room_type IN ('classroom', 'computer_lab', 'meeting', 'other')),
    capacity      INTEGER CHECK (capacity >= 0),
    equipment     TEXT,
    description   TEXT,
    photo_url     TEXT,
    panorama_url  TEXT,                                               -- Pannellum 360° 照片
    floor_plan_id INTEGER REFERENCES floor_plans(id) ON DELETE SET NULL,
    map_x         NUMERIC(5,2) CHECK (map_x BETWEEN 0 AND 100),       -- 平面圖上的 X（%）
    map_y         NUMERIC(5,2) CHECK (map_y BETWEEN 0 AND 100),       -- 平面圖上的 Y（%）
    is_bookable   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------- 模組②：物品 ----------
CREATE TABLE items (
    id             INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name           VARCHAR(50) NOT NULL,
    category       TEXT NOT NULL DEFAULT 'device'
                   CHECK (category IN ('key', 'device', 'other')),
    total_quantity INTEGER NOT NULL DEFAULT 1 CHECK (total_quantity >= 0),
    room_id        INTEGER REFERENCES rooms(id) ON DELETE CASCADE,    -- 鑰匙對應的教室
    is_active      BOOLEAN NOT NULL DEFAULT TRUE
);

-- ---------- 模組②：借用單 ----------
CREATE TABLE bookings (
    id             INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id        INTEGER NOT NULL REFERENCES users(id),
    room_id        INTEGER NOT NULL REFERENCES rooms(id),
    booking_date   DATE    NOT NULL,
    start_time     TIME    NOT NULL,
    end_time       TIME    NOT NULL,
    purpose        TEXT,
    status         TEXT NOT NULL DEFAULT 'pending'
                   CHECK (status IN ('pending', 'approved', 'rejected',
                                     'checked_out', 'returned', 'cancelled')),
    review_comment TEXT,                                              -- 審核意見
    reviewed_by    INTEGER REFERENCES users(id),
    reviewed_at    TIMESTAMPTZ,
    checked_out_by INTEGER REFERENCES users(id),                      -- 登記借出的管理員
    checked_out_at TIMESTAMPTZ,
    returned_by    INTEGER REFERENCES users(id),                      -- 確認歸還的管理員
    returned_at    TIMESTAMPTZ,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (start_time < end_time)                                     -- 結束要晚於開始
);

-- ---------- 模組②：借用單 ↔ 物品（多對多） ----------
CREATE TABLE booking_items (
    booking_id INTEGER NOT NULL REFERENCES bookings(id) ON DELETE CASCADE,
    item_id    INTEGER NOT NULL REFERENCES items(id),
    quantity   INTEGER NOT NULL DEFAULT 1 CHECK (quantity > 0),
    PRIMARY KEY (booking_id, item_id)                                 -- 同一單同一物品只記一列
);

-- ---------- 模組③：課程 ----------
CREATE TABLE courses (
    id          INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    course_code VARCHAR(20),
    name        VARCHAR(100) NOT NULL,
    teacher_id  INTEGER NOT NULL REFERENCES users(id),                -- 授課老師
    created_by  INTEGER NOT NULL REFERENCES users(id),                -- 建立者
    note        TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------- 模組③：上課時段 ----------
CREATE TABLE course_sessions (
    id           INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    course_id    INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,  -- 刪課連帶刪時段
    room_id      INTEGER NOT NULL REFERENCES rooms(id),                      -- 希望的教室
    session_date DATE    NOT NULL,
    start_time   TIME    NOT NULL,
    end_time     TIME    NOT NULL,
    CHECK (start_time < end_time)
);

-- ---------- 索引：加速「某教室某天」的查詢 ----------
CREATE INDEX idx_bookings_room_date ON bookings (room_id, booking_date);
CREATE INDEX idx_bookings_user      ON bookings (user_id);
CREATE INDEX idx_sessions_room_date ON course_sessions (room_id, session_date);
CREATE INDEX idx_courses_teacher    ON courses (teacher_id);

-- ---------- 整合：統一占用表 ----------
-- 把「已核准的借用」和「排課」合成一張虛擬表，借用頁與排課頁都查這裡
CREATE VIEW room_occupancy AS
SELECT 'booking'::TEXT    AS source,      -- 來源：借用
       b.id               AS source_id,
       b.room_id,
       b.booking_date     AS occupy_date,
       b.start_time,
       b.end_time,
       COALESCE(b.purpose, '借用')::TEXT AS title,
       b.user_id          AS owner_id
FROM bookings b
WHERE b.status IN ('approved', 'checked_out')   -- 只有核准後才算占用
UNION ALL
SELECT 'course'::TEXT,                          -- 來源：排課
       s.id,
       s.room_id,
       s.session_date,
       s.start_time,
       s.end_time,
       c.name::TEXT,
       c.teacher_id
FROM course_sessions s
JOIN courses c ON c.id = s.course_id;
