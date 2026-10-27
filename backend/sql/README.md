# 数据库脚本

库名 `water_dispatch`。按文件名顺序执行，不要跳号。后端启动时会把尚未记录的 `002`、`003` 写入 `schema_migrations` 并执行；`001` 需要先手工建库。

## 执行顺序

1. `001_water_dispatch.sql`：建库、建表，并写入校对稿站点、站间连接和规程文档索引。
2. `002_payload_columns.sql`：给业务表补 `payload`，并增加报告表、登录令牌表。列或表已存在时跳过，可以重复执行。
3. `003_seed.sql`：写入接口使用的站点、三个片区、片区对应关系、测点和本地联调账号。已有同主键时跳过。

在 MySQL 客户端中：

```sql
SOURCE backend/sql/001_water_dispatch.sql;
SOURCE backend/sql/002_payload_columns.sql;
SOURCE backend/sql/003_seed.sql;
```

路径按当前工作目录调整。连接串使用环境变量 `MYSQL_PASSWORD`，库名默认 `water_dispatch`。

## 初始账号

这些账号只用于本机联调，和 `backend/app/data/users.py` 一致。

| 用户名 | 密码 | 角色 |
| --- | --- | --- |
| admin | admin123 | 系统管理员 |
| operator | operator123 | 运行值班员 |
| station-operator | station123 | 仅二泵站 |
| reviewer | reviewer123 | 审批负责人 |

固定令牌形如 `mock-token-admin`。后端连上库且这些行已在时，登录读取库里的记录。
