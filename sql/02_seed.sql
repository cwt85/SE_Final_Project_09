-- =========================================================
-- 02_seed.sql：測試資料
-- 必須在 01_schema.sql 之後執行（資料表剛建好，id 會從 1 開始）
--
-- 日期都用「本週一」往後推算，所以不管哪天啟動，週曆上都看得到資料：
--   date_trunc('week', CURRENT_DATE)::date  → 本週一
--   ... + 1 → 週二，+ 2 → 週三 ...
--
-- 教室編號只是示意，正式資料請參考
-- https://www.ibs.ncnu.edu.tw/index.php/resources/space-classroom
-- =========================================================

-- ---------- 帳號 ----------
-- crypt(明碼, gen_salt('bf')) 會產生 bcrypt 雜湊（$2a$...），
-- Python 端用 bcrypt.checkpw() 就能驗證
-- 測試帳號的密碼都是「帳號 + 123」，例如 admin / admin123
INSERT INTO users (username, password_hash, full_name, email, role, status) VALUES
('admin',    crypt('admin123',    gen_salt('bf')), '系統管理員', 'admin@example.com',    'admin',   'active'),   -- id 1
('teacher1', crypt('teacher1123', gen_salt('bf')), '王老師',     'teacher1@example.com', 'teacher', 'active'),   -- id 2
('teacher2', crypt('teacher2123', gen_salt('bf')), '李老師',     'teacher2@example.com', 'teacher', 'active'),   -- id 3
('student1', crypt('student1123', gen_salt('bf')), '陳同學',     'student1@example.com', 'user',    'active'),   -- id 4
('student2', crypt('student2123', gen_salt('bf')), '林同學',     'student2@example.com', 'user',    'active'),   -- id 5
('newbie',   crypt('newbie123',   gen_salt('bf')), '待審核同學', 'newbie@example.com',   'user',    'pending');  -- id 6：測試帳號審核

-- 已啟用的帳號補上「由 admin 審核」
UPDATE users SET approved_by = 1, approved_at = now() WHERE status = 'active';

-- ---------- 平面圖 ----------
INSERT INTO floor_plans (floor, image_url) VALUES
(1, '/static/space_query/floorplans/1F.png'),   -- id 1
(2, '/static/space_query/floorplans/2F.png');   -- id 2

-- ---------- 空間 ----------
INSERT INTO rooms (room_code, name, room_type, capacity, equipment, floor_plan_id, map_x, map_y, is_bookable) VALUES
('M101', '示範教室 101', 'classroom',    60, '投影機、音響、白板',       1, 20.0, 35.0, TRUE),   -- id 1
('M102', '示範教室 102', 'classroom',    40, '投影機、白板',             1, 45.0, 35.0, TRUE),   -- id 2
('M201', '電腦教室 201', 'computer_lab', 50, '電腦 50 台、廣播系統',     2, 30.0, 60.0, TRUE),   -- id 3
('M202', '會議室 202',   'meeting',      12, '大螢幕、視訊設備',         2, 70.0, 60.0, TRUE),   -- id 4
('M203', '院辦公室',     'other',      NULL, NULL,                       2, 85.0, 20.0, FALSE);  -- id 5：不開放借用

-- ---------- 物品 ----------
INSERT INTO items (name, category, total_quantity, room_id) VALUES
('M101 鑰匙', 'key',    1, 1),      -- id 1
('M102 鑰匙', 'key',    1, 2),      -- id 2
('M201 鑰匙', 'key',    1, 3),      -- id 3
('M202 鑰匙', 'key',    1, 4),      -- id 4
('投影筆',    'device', 5, NULL),   -- id 5
('筆電',      'device', 3, NULL),   -- id 6
('延長線',    'other',  4, NULL);   -- id 7

-- ---------- 借用單：涵蓋每一種狀態 ----------
INSERT INTO bookings (user_id, room_id, booking_date, start_time, end_time, purpose, status,
                      review_comment, reviewed_by, reviewed_at,
                      checked_out_by, checked_out_at, returned_by, returned_at) VALUES
-- id 1：已核准（週一上午）
(4, 1, date_trunc('week', CURRENT_DATE)::date + 0, '10:00', '12:00', '讀書會', 'approved',
 '請準時歸還鑰匙', 1, now(), NULL, NULL, NULL, NULL),
-- id 2：待審核（週二下午）
(4, 2, date_trunc('week', CURRENT_DATE)::date + 1, '13:00', '15:00', '專題討論', 'pending',
 NULL, NULL, NULL, NULL, NULL, NULL, NULL),
-- id 3：已借出（週三晚上）
(5, 1, date_trunc('week', CURRENT_DATE)::date + 2, '18:00', '20:00', '系學會會議', 'checked_out',
 NULL, 1, now(), 1, now(), NULL, NULL),
-- id 4：已歸還（上週）
(5, 3, date_trunc('week', CURRENT_DATE)::date - 5, '09:00', '12:00', '程式工作坊', 'returned',
 NULL, 1, now(), 1, now(), 1, now()),
-- id 5：被退件（週四）
(4, 4, date_trunc('week', CURRENT_DATE)::date + 3, '14:00', '16:00', '社團聚餐', 'rejected',
 '會議室不開放用餐活動', 1, now(), NULL, NULL, NULL, NULL);

-- 借用物品（一張單可以借多項）
INSERT INTO booking_items (booking_id, item_id, quantity) VALUES
(1, 1, 1),   -- 讀書會：M101 鑰匙
(1, 5, 1),   --         投影筆
(3, 1, 1),   -- 系學會：M101 鑰匙
(3, 6, 1),   --         筆電
(3, 7, 2),   --         延長線 ×2
(4, 3, 1);   -- 工作坊：M201 鑰匙

-- ---------- 課程 ----------
INSERT INTO courses (course_code, name, teacher_id, created_by) VALUES
('IM301', '管理資訊系統', 2, 2),   -- id 1：王老師自己建立
('IM302', '資料庫系統',   3, 3),   -- id 2：李老師自己建立
('IM201', '程式設計',     3, 1),   -- id 3：管理員建立後指派給李老師
('IM202', '統計學',       2, 1);   -- id 4：管理員建立後指派給王老師

-- 上課時段：generate_series(0, 3) 產生 0,1,2,3 → 從本週起連續 4 週
-- 管理資訊系統：每週一 13:10-16:00 @ M101
INSERT INTO course_sessions (course_id, room_id, session_date, start_time, end_time)
SELECT 1, 1, date_trunc('week', CURRENT_DATE)::date + 7 * w, '13:10', '16:00'
FROM generate_series(0, 3) AS w;

-- 資料庫系統：每週二 09:10-12:00 @ M201
INSERT INTO course_sessions (course_id, room_id, session_date, start_time, end_time)
SELECT 2, 3, date_trunc('week', CURRENT_DATE)::date + 1 + 7 * w, '09:10', '12:00'
FROM generate_series(0, 3) AS w;

-- 刻意製造的衝突（給「衝突清單」功能測試用）：
-- 程式設計：本週一 14:10-17:00 @ M101 → 和「管理資訊系統」搶同一間教室（教室衝突）
INSERT INTO course_sessions (course_id, room_id, session_date, start_time, end_time) VALUES
(3, 1, date_trunc('week', CURRENT_DATE)::date + 0, '14:10', '17:00');

-- 統計學：本週一 15:10-17:00 @ M102 → 王老師同時要上「管理資訊系統」（老師衝堂）
INSERT INTO course_sessions (course_id, room_id, session_date, start_time, end_time) VALUES
(4, 2, date_trunc('week', CURRENT_DATE)::date + 0, '15:10', '17:00');
