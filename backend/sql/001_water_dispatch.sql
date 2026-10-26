CREATE DATABASE IF NOT EXISTS water_dispatch
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_0900_ai_ci;

USE water_dispatch;

CREATE TABLE IF NOT EXISTS stations (
  id VARCHAR(32) PRIMARY KEY,
  code VARCHAR(32) NOT NULL,
  name VARCHAR(64) NOT NULL,
  station_type VARCHAR(32) NOT NULL,
  sequence_no INT NOT NULL,
  enabled TINYINT(1) NOT NULL DEFAULT 1,
  note VARCHAR(255) NULL
);

CREATE TABLE IF NOT EXISTS links (
  id VARCHAR(32) PRIMARY KEY,
  from_object VARCHAR(32) NOT NULL,
  to_object VARCHAR(32) NOT NULL,
  link_type VARCHAR(32) NOT NULL,
  capacity DECIMAL(12,2) NULL,
  travel_time INT NULL,
  valid_from DATE NULL,
  length_km DECIMAL(10,4) NULL,
  note VARCHAR(255) NULL
);

CREATE TABLE IF NOT EXISTS supply_areas (
  id VARCHAR(32) PRIMARY KEY,
  code VARCHAR(32) NOT NULL,
  name VARCHAR(64) NOT NULL,
  parent_id VARCHAR(32) NULL,
  enabled TINYINT(1) NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS station_area_map (
  station_id VARCHAR(32) NOT NULL,
  area_id VARCHAR(32) NOT NULL,
  valid_from DATE NULL,
  valid_to DATE NULL,
  confirmed_by VARCHAR(64) NULL,
  PRIMARY KEY (station_id, area_id)
);

CREATE TABLE IF NOT EXISTS measurement_points (
  id VARCHAR(32) PRIMARY KEY,
  object_id VARCHAR(32) NOT NULL,
  metric_code VARCHAR(32) NOT NULL,
  unit VARCHAR(16) NULL,
  quality_rule VARCHAR(128) NULL,
  source VARCHAR(64) NULL,
  device_id VARCHAR(64) NULL
);

CREATE TABLE IF NOT EXISTS external_factors (
  id VARCHAR(32) PRIMARY KEY,
  factor_type VARCHAR(32) NOT NULL,
  effective_at DATETIME NULL,
  payload JSON NULL,
  source VARCHAR(64) NULL
);

CREATE TABLE IF NOT EXISTS users_roles (
  user_id VARCHAR(32) PRIMARY KEY,
  role_code VARCHAR(32) NOT NULL,
  station_scope VARCHAR(255) NULL,
  area_scope VARCHAR(255) NULL
);

CREATE TABLE IF NOT EXISTS telemetry_readings (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  point_id VARCHAR(32) NOT NULL,
  observed_at DATETIME NOT NULL,
  value DECIMAL(16,4) NULL,
  quality VARCHAR(16) NULL,
  source_batch VARCHAR(64) NULL,
  is_stale TINYINT(1) NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS supply_plans (
  id VARCHAR(32) PRIMARY KEY,
  area_id VARCHAR(32) NOT NULL,
  plan_time DATETIME NULL,
  planned_volume DECIMAL(16,4) NULL,
  version VARCHAR(16) NULL,
  status VARCHAR(16) NULL
);

CREATE TABLE IF NOT EXISTS demand_observations (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  area_id VARCHAR(32) NOT NULL,
  observed_at DATETIME NOT NULL,
  demand_value DECIMAL(16,4) NULL,
  source VARCHAR(64) NULL
);

CREATE TABLE IF NOT EXISTS scheme_comparisons (
  id VARCHAR(32) PRIMARY KEY,
  request_id VARCHAR(64) NULL,
  options_json JSON NULL,
  metrics_json JSON NULL,
  created_by VARCHAR(64) NULL
);

CREATE TABLE IF NOT EXISTS alarms (
  id VARCHAR(32) PRIMARY KEY,
  object_id VARCHAR(32) NOT NULL,
  alarm_code VARCHAR(32) NULL,
  level VARCHAR(16) NULL,
  started_at DATETIME NULL,
  ended_at DATETIME NULL,
  status VARCHAR(16) NULL
);

CREATE TABLE IF NOT EXISTS station_contacts (
  id VARCHAR(32) PRIMARY KEY,
  station_id VARCHAR(32) NOT NULL,
  contact_type VARCHAR(32) NULL,
  destination VARCHAR(128) NULL,
  priority INT NULL,
  enabled TINYINT(1) NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS incidents (
  id VARCHAR(32) PRIMARY KEY,
  station_id VARCHAR(32) NOT NULL,
  category VARCHAR(32) NULL,
  level VARCHAR(16) NULL,
  source VARCHAR(64) NULL,
  occurred_at DATETIME NULL,
  status VARCHAR(16) NULL,
  reported_by VARCHAR(64) NULL
);

CREATE TABLE IF NOT EXISTS escalation_rules (
  id VARCHAR(32) PRIMARY KEY,
  level VARCHAR(16) NOT NULL,
  acknowledge_timeout INT NULL,
  escalation_timeout INT NULL,
  target_role VARCHAR(32) NULL
);

CREATE TABLE IF NOT EXISTS notifications (
  id VARCHAR(32) PRIMARY KEY,
  incident_id VARCHAR(32) NOT NULL,
  recipient VARCHAR(128) NULL,
  channel VARCHAR(32) NULL,
  status VARCHAR(16) NULL,
  sent_at DATETIME NULL,
  acknowledged_at DATETIME NULL
);

CREATE TABLE IF NOT EXISTS notification_deliveries (
  id VARCHAR(32) PRIMARY KEY,
  notification_id VARCHAR(32) NOT NULL,
  attempt_no INT NOT NULL,
  provider VARCHAR(64) NULL,
  result VARCHAR(32) NULL,
  failure_reason VARCHAR(255) NULL,
  attempted_at DATETIME NULL
);

CREATE TABLE IF NOT EXISTS work_orders (
  id VARCHAR(32) PRIMARY KEY,
  object_id VARCHAR(32) NOT NULL,
  category VARCHAR(32) NULL,
  description VARCHAR(255) NULL,
  owner VARCHAR(64) NULL,
  status VARCHAR(16) NULL,
  due_at DATETIME NULL
);

CREATE TABLE IF NOT EXISTS shift_handovers (
  id VARCHAR(32) PRIMARY KEY,
  shift_at DATETIME NULL,
  summary VARCHAR(255) NULL,
  open_issues VARCHAR(255) NULL,
  created_by VARCHAR(64) NULL
);

CREATE TABLE IF NOT EXISTS dispatch_reviews (
  id VARCHAR(32) PRIMARY KEY,
  request_id VARCHAR(64) NULL,
  recommendation VARCHAR(255) NULL,
  reviewer VARCHAR(64) NULL,
  decision VARCHAR(32) NULL,
  decided_at DATETIME NULL
);

CREATE TABLE IF NOT EXISTS knowledge_documents (
  id VARCHAR(32) PRIMARY KEY,
  title VARCHAR(128) NOT NULL,
  doc_type VARCHAR(32) NOT NULL,
  version VARCHAR(16) NOT NULL,
  valid_from DATE NULL,
  valid_to DATE NULL,
  status VARCHAR(16) NOT NULL,
  source VARCHAR(255) NULL,
  approved_by VARCHAR(64) NULL
);

CREATE TABLE IF NOT EXISTS knowledge_chunks (
  id VARCHAR(32) PRIMARY KEY,
  document_id VARCHAR(32) NOT NULL,
  page_or_section VARCHAR(64) NULL,
  content TEXT NOT NULL,
  station_scope VARCHAR(128) NULL
);

CREATE TABLE IF NOT EXISTS conversations (
  id VARCHAR(32) PRIMARY KEY,
  user_id VARCHAR(32) NULL,
  created_at DATETIME NULL,
  title VARCHAR(128) NULL
);

CREATE TABLE IF NOT EXISTS agent_runs (
  id VARCHAR(32) PRIMARY KEY,
  conversation_id VARCHAR(32) NULL,
  intent VARCHAR(32) NULL,
  tools_used VARCHAR(255) NULL,
  status VARCHAR(16) NULL,
  duration_ms INT NULL
);

CREATE TABLE IF NOT EXISTS audit_events (
  id VARCHAR(32) PRIMARY KEY,
  user_id VARCHAR(32) NULL,
  action VARCHAR(64) NULL,
  object_type VARCHAR(32) NULL,
  object_id VARCHAR(64) NULL,
  created_at DATETIME NULL
);

INSERT INTO stations (id, code, name, station_type, sequence_no, enabled, note) VALUES
  ('st-jiquan-1', 'JQ1', '集泉一站', '泵站', 1, 1, '校对稿：水帘洞附近，汇集滚泉、河北泉、桥墩泉、禁区泉'),
  ('st-jiquan-2', 'JQ2', '集泉二站', '泵站', 2, 1, '校对稿：梁家河附近，距总干一站北约400米'),
  ('st-zonggan-1', 'ZG1', '总干一站', '泵站', 3, 1, '校对稿：苇泽关梁家河泉附近'),
  ('st-zonggan-2', 'ZG2', '总干二站', '泵站', 4, 1, '校对稿：娘子关村东南'),
  ('st-zonggan-3', 'ZG3', '总干三站', '泵站', 5, 1, '校对稿：旧关村分水岭北侧'),
  ('st-zonggan-4', 'ZG4', '总干四站', '泵站', 6, 1, '校对稿：槐树铺村北侧赵家峪'),
  ('st-shangzhuang', 'SZDH', '上庄倒虹', '倒虹', 7, 1, '校对稿：西干渠，南上庄村')
ON DUPLICATE KEY UPDATE name = VALUES(name), note = VALUES(note);

INSERT INTO links (id, from_object, to_object, link_type, length_km, note) VALUES
  ('lk-jq1-zg1', 'st-jiquan-1', 'st-zonggan-1', '前池来水', NULL, '校对稿：集泉一站送至总干一站前池'),
  ('lk-jq2-zg1', 'st-jiquan-2', 'st-zonggan-1', '前池来水', 0.4000, '校对稿：集泉二站距总干一站北约400米'),
  ('lk-zg1-zg2', 'st-zonggan-1', 'st-zonggan-2', '总干', 0.5707, '校对稿页码32'),
  ('lk-zg2-zg3', 'st-zonggan-2', 'st-zonggan-3', '总干', 3.8030, '校对稿页码32'),
  ('lk-zg3-zg4', 'st-zonggan-3', 'st-zonggan-4', '总干', 5.4080, '校对稿页码32'),
  ('lk-west-sz', 'st-zonggan-4', 'st-shangzhuang', '西干渠', NULL, '校对稿：西干渠至上庄倒虹，渠长未拆到本段')
ON DUPLICATE KEY UPDATE length_km = VALUES(length_km), note = VALUES(note);

INSERT INTO knowledge_documents (id, title, doc_type, version, status, source) VALUES
  ('kd-duty', '调度员岗位职责', '规程', '桌面稿', '待审', 'C:/Users/lenovo/Desktop/规程/规程.txt'),
  ('kd-flow', '集泉至平定输水流程', '调度说明', '桌面稿', '待审', 'C:/Users/lenovo/Desktop/规程/工作流程.txt'),
  ('kd-pump', '泵站现场运行规程', '规程', '桌面稿', '待审', 'C:/Users/lenovo/Desktop/规程/4.泵站现场运行规程.wps'),
  ('kd-hydro', '水工现场运行规程', '规程', '桌面稿', '待审', 'C:/Users/lenovo/Desktop/规程/6.水工现场运行规程.wps'),
  ('kd-substation', '变电站运行规程', '规程', '桌面稿', '待审', 'C:/Users/lenovo/Desktop/规程/5.变电站运行规程.wps'),
  ('kd-safety', '电力安全工作规程', '规程', '桌面稿', '待审', 'C:/Users/lenovo/Desktop/规程/3.电力安全工作规程.wps'),
  ('kd-em-power', '输变电应急预案', '应急预案', '桌面稿', '待审', 'C:/Users/lenovo/Desktop/规程/24.输变电应急预案.wps'),
  ('kd-em-line', '35KV线路应急预案', '应急预案', '桌面稿', '待审', 'C:/Users/lenovo/Desktop/规程/25.35KV线路应急预案.wps'),
  ('kd-em-sub', '变电站应急预案', '应急预案', '桌面稿', '待审', 'C:/Users/lenovo/Desktop/规程/26.变电站应急预案.wps')
ON DUPLICATE KEY UPDATE status = VALUES(status), source = VALUES(source);

INSERT INTO knowledge_chunks (id, document_id, page_or_section, content, station_scope) VALUES
  ('kc-duty', 'kd-duty', '全文', '调度员是当班调度岗工作的责任人。应按生产计划执行调度任务，并按安全、供水和调度规程协调停送电、开停机、维护检修和抢修。当值期间做记录和数据汇总，异常及时汇报。', NULL),
  ('kc-flow', 'kd-flow', '全文', '泉眼自流进入集泉一、集泉二前池，两站加压后到一泵站前池，再逐级加压到二泵站、三泵站、四泵站，之后自流到上庄倒虹，再送往平定。', '集泉至四泵站')
ON DUPLICATE KEY UPDATE content = VALUES(content);

ALTER TABLE stations COMMENT = '泵站、取水点、倒虹等工程对象';
ALTER TABLE links COMMENT = '站与站、站与渠道之间的连接和长度';
ALTER TABLE supply_areas COMMENT = '供水片区';
ALTER TABLE station_area_map COMMENT = '泵站与片区的对应关系，需业务确认';
ALTER TABLE measurement_points COMMENT = '流量、压力、水位、能耗等测点定义，不含实时读数';
ALTER TABLE external_factors COMMENT = '天气、检修等外部影响因素';
ALTER TABLE users_roles COMMENT = '用户角色以及可查看的站点和片区';
ALTER TABLE telemetry_readings COMMENT = '测点读数，含时间和数据质量';
ALTER TABLE supply_plans COMMENT = '供水计划及版本';
ALTER TABLE demand_observations COMMENT = '片区需求或供水统计';
ALTER TABLE scheme_comparisons COMMENT = '备选调度方案的比较结果';
ALTER TABLE alarms COMMENT = '告警及其关闭状态';
ALTER TABLE station_contacts COMMENT = '站点值班联系人、备用联系人和通知渠道';
ALTER TABLE incidents COMMENT = '站点人工或系统事件及处理状态';
ALTER TABLE escalation_rules COMMENT = '未确认事件的升级时限和通知对象';
ALTER TABLE notifications COMMENT = '发给调度人员的通知及确认状态';
ALTER TABLE notification_deliveries COMMENT = '通知的每次发送、失败和重试';
ALTER TABLE work_orders COMMENT = '巡检、维修和待办工单';
ALTER TABLE shift_handovers COMMENT = '交接班摘要和未闭环问题';
ALTER TABLE dispatch_reviews COMMENT = '调度建议的人工审核，不保存控制指令';
ALTER TABLE knowledge_documents COMMENT = '规程、预案和调度说明的文档信息，不含正文';
ALTER TABLE knowledge_chunks COMMENT = '规程正文片段；向量仍在 Chroma，不在本表';
ALTER TABLE conversations COMMENT = '用户与 Agent 的会话';
ALTER TABLE agent_runs COMMENT = '一次 Agent 分析的意图、工具和状态';
ALTER TABLE audit_events COMMENT = '查看、导出、审批和配置变更记录';
