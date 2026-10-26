ALTER TABLE stations ADD COLUMN payload JSON NULL;
ALTER TABLE alarms ADD COLUMN payload JSON NULL;
ALTER TABLE supply_areas ADD COLUMN payload JSON NULL;
ALTER TABLE incidents ADD COLUMN payload JSON NULL;
ALTER TABLE notifications ADD COLUMN payload JSON NULL;
ALTER TABLE dispatch_reviews ADD COLUMN payload JSON NULL;
ALTER TABLE work_orders ADD COLUMN payload JSON NULL;
ALTER TABLE users_roles ADD COLUMN payload JSON NULL;
ALTER TABLE audit_events ADD COLUMN payload JSON NULL;
ALTER TABLE knowledge_documents ADD COLUMN payload JSON NULL;
ALTER TABLE agent_runs ADD COLUMN payload JSON NULL;
ALTER TABLE agent_runs ADD COLUMN task_payload JSON NULL;
ALTER TABLE conversations ADD COLUMN payload JSON NULL;
CREATE TABLE IF NOT EXISTS reports (
  id VARCHAR(64) PRIMARY KEY,
  payload JSON NULL
) COMMENT = '运行报告草稿、复核和归档';
CREATE TABLE IF NOT EXISTS auth_tokens (
  token VARCHAR(128) PRIMARY KEY,
  username VARCHAR(64) NOT NULL
) COMMENT = '登录令牌与用户名';
