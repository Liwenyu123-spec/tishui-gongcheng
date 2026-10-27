-- 平台联调用的初始业务数据。001 里的校对稿站点 id 与接口使用的 id 不同，这里按接口补齐。
-- 已有同主键记录时跳过，避免覆盖库里后来改过的账号和站点。

INSERT IGNORE INTO stations (id, code, name, station_type, sequence_no, enabled, note, payload) VALUES
  ('jq-01', 'jq-01', '集泉一站', '取水泵站', 1, 1, '水帘洞附近', '{"id":"jq-01","name":"集泉一站","sequence":1,"station_type":"取水泵站","status":"running","location":"水帘洞附近","description":"泉眼高于前池，自流汇入后加压，送往一泵站前池。","metrics":["flow","pressure","level","energy"]}'),
  ('jq-02', 'jq-02', '集泉二站', '取水泵站', 2, 1, '梁家河附近', '{"id":"jq-02","name":"集泉二站","sequence":2,"station_type":"取水泵站","status":"running","location":"梁家河附近","description":"与集泉一站共同汇集泉水并加压，经渠线送入一泵站前池。","metrics":["flow","pressure","level","energy"]}'),
  ('pump-01', 'pump-01', '一泵站', '加压泵站', 3, 1, '输水干线 1+200', '{"id":"pump-01","name":"一泵站","sequence":3,"station_type":"加压泵站","status":"running","location":"输水干线 1+200","description":"承接集泉来水，加压后送往二泵站。","metrics":["flow","pressure","level","energy"]}'),
  ('pump-02', 'pump-02', '二泵站', '加压泵站', 4, 1, '输水干线 4+800', '{"id":"pump-02","name":"二泵站","sequence":4,"station_type":"加压泵站","status":"warning","location":"输水干线 4+800","description":"承接一泵站来水，加压后送往三泵站。","metrics":["flow","pressure","level","energy"]}'),
  ('pump-03', 'pump-03', '三泵站', '加压泵站', 5, 1, '输水干线 8+600', '{"id":"pump-03","name":"三泵站","sequence":5,"station_type":"加压泵站","status":"running","location":"输水干线 8+600","description":"承接二泵站来水，加压后送往四泵站。","metrics":["flow","pressure","level","energy"]}'),
  ('pump-04', 'pump-04', '四泵站', '加压泵站', 6, 1, '槐树铺至西干渠', '{"id":"pump-04","name":"四泵站","sequence":6,"station_type":"加压泵站","status":"running","location":"槐树铺至西干渠","description":"末级加压。出水后改为自流，进入上庄倒虹。","metrics":["flow","pressure","level","energy"]}'),
  ('sz-invert', 'sz-invert', '上庄倒虹', '倒虹', 7, 1, '南上庄村', '{"id":"sz-invert","name":"上庄倒虹","sequence":7,"station_type":"倒虹","status":"running","location":"南上庄村","description":"四泵站之后的自流段，跨越南川河后送往平定。","metrics":["flow","pressure","level"]}'),
  ('pingding-inlet', 'pingding-inlet', '平定侧入口', '供水入口', 8, 1, '平定城区', '{"id":"pingding-inlet","name":"平定侧入口","sequence":8,"station_type":"供水入口","status":"running","location":"平定城区","description":"上庄倒虹之后进入平定片区的入口。","metrics":["flow","pressure","level"]}');

INSERT IGNORE INTO supply_areas (id, code, name, parent_id, enabled, payload) VALUES
  ('平定城区', 'pump-04', '平定城区', NULL, 1, '{"area":"平定城区","station_id":"pump-04","supply":9200.0,"demand":9800.0,"pressure":0.38,"risk":"medium"}'),
  ('东部片区', 'pump-03', '东部片区', NULL, 1, '{"area":"东部片区","station_id":"pump-03","supply":5600.0,"demand":5200.0,"pressure":0.43,"risk":"low"}'),
  ('西部片区', 'pump-02', '西部片区', NULL, 1, '{"area":"西部片区","station_id":"pump-02","supply":4100.0,"demand":4700.0,"pressure":0.31,"risk":"high"}');

INSERT IGNORE INTO station_area_map (station_id, area_id, confirmed_by) VALUES
  ('pump-04', '平定城区', 'seed'),
  ('pump-03', '东部片区', 'seed'),
  ('pump-02', '西部片区', 'seed');

INSERT IGNORE INTO measurement_points (id, object_id, metric_code, unit, quality_rule, source) VALUES
  ('mp-jq-01-flow', 'jq-01', 'flow', 'm³/h', '非负', 'seed'),
  ('mp-jq-01-pressure', 'jq-01', 'pressure', 'MPa', '非负', 'seed'),
  ('mp-jq-01-level', 'jq-01', 'level', 'm', '非负', 'seed'),
  ('mp-jq-01-energy', 'jq-01', 'energy', 'kWh', '非负', 'seed'),
  ('mp-jq-02-flow', 'jq-02', 'flow', 'm³/h', '非负', 'seed'),
  ('mp-jq-02-pressure', 'jq-02', 'pressure', 'MPa', '非负', 'seed'),
  ('mp-jq-02-level', 'jq-02', 'level', 'm', '非负', 'seed'),
  ('mp-jq-02-energy', 'jq-02', 'energy', 'kWh', '非负', 'seed'),
  ('mp-pump-01-flow', 'pump-01', 'flow', 'm³/h', '非负', 'seed'),
  ('mp-pump-01-pressure', 'pump-01', 'pressure', 'MPa', '非负', 'seed'),
  ('mp-pump-01-level', 'pump-01', 'level', 'm', '非负', 'seed'),
  ('mp-pump-01-energy', 'pump-01', 'energy', 'kWh', '非负', 'seed'),
  ('mp-pump-02-flow', 'pump-02', 'flow', 'm³/h', '非负', 'seed'),
  ('mp-pump-02-pressure', 'pump-02', 'pressure', 'MPa', '非负', 'seed'),
  ('mp-pump-02-level', 'pump-02', 'level', 'm', '非负', 'seed'),
  ('mp-pump-02-energy', 'pump-02', 'energy', 'kWh', '非负', 'seed'),
  ('mp-pump-03-flow', 'pump-03', 'flow', 'm³/h', '非负', 'seed'),
  ('mp-pump-03-pressure', 'pump-03', 'pressure', 'MPa', '非负', 'seed'),
  ('mp-pump-03-level', 'pump-03', 'level', 'm', '非负', 'seed'),
  ('mp-pump-03-energy', 'pump-03', 'energy', 'kWh', '非负', 'seed'),
  ('mp-pump-04-flow', 'pump-04', 'flow', 'm³/h', '非负', 'seed'),
  ('mp-pump-04-pressure', 'pump-04', 'pressure', 'MPa', '非负', 'seed'),
  ('mp-pump-04-level', 'pump-04', 'level', 'm', '非负', 'seed'),
  ('mp-pump-04-energy', 'pump-04', 'energy', 'kWh', '非负', 'seed'),
  ('mp-sz-invert-flow', 'sz-invert', 'flow', 'm³/h', '非负', 'seed'),
  ('mp-sz-invert-pressure', 'sz-invert', 'pressure', 'MPa', '非负', 'seed'),
  ('mp-sz-invert-level', 'sz-invert', 'level', 'm', '非负', 'seed'),
  ('mp-pingding-inlet-flow', 'pingding-inlet', 'flow', 'm³/h', '非负', 'seed'),
  ('mp-pingding-inlet-pressure', 'pingding-inlet', 'pressure', 'MPa', '非负', 'seed'),
  ('mp-pingding-inlet-level', 'pingding-inlet', 'level', 'm', '非负', 'seed');

INSERT IGNORE INTO users_roles (user_id, role_code, station_scope, area_scope, payload) VALUES
  ('admin', 'admin', '*', '', '{"password":"admin123","id":"user-admin","username":"admin","display_name":"系统管理员","role":"admin","permissions":["read","ask","submit_scheme","review","knowledge","audit"],"station_ids":["*"]}'),
  ('operator', 'operator', '*', '', '{"password":"operator123","id":"user-operator","username":"operator","display_name":"运行值班员","role":"operator","permissions":["read","ask","submit_scheme"],"station_ids":["*"]}'),
  ('station-operator', 'operator', 'pump-02', '西部片区', '{"password":"station123","id":"user-station-operator","username":"station-operator","display_name":"二泵站值班员","role":"operator","permissions":["read"],"station_ids":["pump-02"]}'),
  ('reviewer', 'reviewer', '*', '', '{"password":"reviewer123","id":"user-reviewer","username":"reviewer","display_name":"审批负责人","role":"reviewer","permissions":["read","review"],"station_ids":["*"]}');

INSERT IGNORE INTO auth_tokens (token, username) VALUES
  ('mock-token-admin', 'admin'),
  ('mock-token-operator', 'operator'),
  ('mock-token-station-operator', 'station-operator'),
  ('mock-token-reviewer', 'reviewer');
