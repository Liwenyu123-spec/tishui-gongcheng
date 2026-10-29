# Docker 本机测试版

此配置用于单机内部联调，默认只绑定本机 `127.0.0.1:8000`。它不会连接现场设备，也不应作为公网生产部署配置。当前认证仍采用演示账号、明文密码和固定 Token；MySQL 不可用时应用可能回退到内存数据。

## 前提

- 安装 Docker Desktop，并启用 Linux 容器。
- 首次构建需要联网拉取 Node、Python、MySQL 镜像及 npm、pip 依赖。Python 镜像包含 PyTorch 等依赖，需预留较多磁盘空间。
- 本测试版使用 `hash` 检索向量并关闭重排、DeepSeek，避免额外下载模型。

## 启动

在项目根目录的 PowerShell 中执行：

```powershell
Copy-Item deploy/.env.example deploy/.env
# 编辑 deploy/.env，把 MYSQL_PASSWORD 改成唯一的测试密码
docker compose --env-file deploy/.env -f deploy/compose.yaml up --build -d
docker compose --env-file deploy/.env -f deploy/compose.yaml ps
```

打开 `http://127.0.0.1:8000`。MySQL 首次创建空数据卷时自动执行 `001_water_dispatch.sql`，应用启动时执行尚未记录的 `002`、`003`。`001` 不会在已有数据卷上重复执行。登录使用当前项目的联调账号，数据库新建时会由应用写入演示账号。

## 验收和排查

```powershell
docker compose --env-file deploy/.env -f deploy/compose.yaml logs --tail=100 app
docker compose --env-file deploy/.env -f deploy/compose.yaml logs --tail=100 db
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health
```

确认页面和登录正常，创建一条可保存的业务记录，再执行 `docker compose --env-file deploy/.env -f deploy/compose.yaml restart app` 并确认记录仍在。另检查知识库状态接口和日志中的 MySQL 数据源状态。`/health` 只证明 HTTP 服务在线，**不能证明 MySQL 已连接**；若日志出现“回退到内存数据源”，本次验收应判为失败。

## 停止与数据

```powershell
docker compose --env-file deploy/.env -f deploy/compose.yaml down
```

普通 `down` 保留 MySQL、知识文档、Chroma、照片及模型缓存卷。不要使用 `down -v`，除非已备份且确定要清空测试数据。迁移或重建前，先备份 MySQL 数据和这些卷。`deploy/.env` 已被 Git 忽略，不要提交密码。

目前尚未在 Docker 环境实测此配置；首次运行后需按上述步骤验收，再用于演示。
