-- 补 payload 等列。列已经存在时跳过，本文件可以重复执行。
-- 每列先查 information_schema，再决定是否 ALTER。

SET @ddl = (SELECT IF(
  (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'stations' AND COLUMN_NAME = 'payload') = 0,
  'ALTER TABLE stations ADD COLUMN payload JSON NULL', 'SELECT 1'));
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl = (SELECT IF(
  (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'alarms' AND COLUMN_NAME = 'payload') = 0,
  'ALTER TABLE alarms ADD COLUMN payload JSON NULL', 'SELECT 1'));
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl = (SELECT IF(
  (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'supply_areas' AND COLUMN_NAME = 'payload') = 0,
  'ALTER TABLE supply_areas ADD COLUMN payload JSON NULL', 'SELECT 1'));
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl = (SELECT IF(
  (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'incidents' AND COLUMN_NAME = 'payload') = 0,
  'ALTER TABLE incidents ADD COLUMN payload JSON NULL', 'SELECT 1'));
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl = (SELECT IF(
  (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'notifications' AND COLUMN_NAME = 'payload') = 0,
  'ALTER TABLE notifications ADD COLUMN payload JSON NULL', 'SELECT 1'));
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl = (SELECT IF(
  (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'dispatch_reviews' AND COLUMN_NAME = 'payload') = 0,
  'ALTER TABLE dispatch_reviews ADD COLUMN payload JSON NULL', 'SELECT 1'));
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl = (SELECT IF(
  (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'work_orders' AND COLUMN_NAME = 'payload') = 0,
  'ALTER TABLE work_orders ADD COLUMN payload JSON NULL', 'SELECT 1'));
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl = (SELECT IF(
  (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'users_roles' AND COLUMN_NAME = 'payload') = 0,
  'ALTER TABLE users_roles ADD COLUMN payload JSON NULL', 'SELECT 1'));
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl = (SELECT IF(
  (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'audit_events' AND COLUMN_NAME = 'payload') = 0,
  'ALTER TABLE audit_events ADD COLUMN payload JSON NULL', 'SELECT 1'));
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl = (SELECT IF(
  (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'knowledge_documents' AND COLUMN_NAME = 'payload') = 0,
  'ALTER TABLE knowledge_documents ADD COLUMN payload JSON NULL', 'SELECT 1'));
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl = (SELECT IF(
  (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'agent_runs' AND COLUMN_NAME = 'payload') = 0,
  'ALTER TABLE agent_runs ADD COLUMN payload JSON NULL', 'SELECT 1'));
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl = (SELECT IF(
  (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'agent_runs' AND COLUMN_NAME = 'task_payload') = 0,
  'ALTER TABLE agent_runs ADD COLUMN task_payload JSON NULL', 'SELECT 1'));
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl = (SELECT IF(
  (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'conversations' AND COLUMN_NAME = 'payload') = 0,
  'ALTER TABLE conversations ADD COLUMN payload JSON NULL', 'SELECT 1'));
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

CREATE TABLE IF NOT EXISTS reports (
  id VARCHAR(64) PRIMARY KEY,
  payload JSON NULL
) COMMENT = '运行报告草稿、复核和归档';
CREATE TABLE IF NOT EXISTS auth_tokens (
  token VARCHAR(128) PRIMARY KEY,
  username VARCHAR(64) NOT NULL
) COMMENT = '登录令牌与用户名';
