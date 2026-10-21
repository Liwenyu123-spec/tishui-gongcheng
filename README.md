# 提水工程供水调度平台

基于 Agentic RAG 与多智能体协作的提水工程供水调度平台。当前项目处于本地模拟联调阶段，使用 Vue 3、Vite、TypeScript、Element Plus、ECharts 和 FastAPI，业务数据仍来自 Mock 数据，不连接真实数据库和现场控制系统。

## 当前版本

- 项目迭代：`v0.10.153`
- 前端包版本：`0.2.0`
- 当前模式：本地测试、Mock 数据、只读 Agent、多 Agent 专业节点协作
- 前端目录：[frontend](./frontend)
- 后端目录：[backend](./backend)

当前已经可以完成页面浏览、后端接口联调、Agent 流式问答、只读工具分析、知识库检索、方案比较、审核和报告草稿等流程。数据库、真实测点、现场控制和部署仍属于后续阶段。

## 已实现页面

- 登录页
- 运行总览
- 工程拓扑
- 站点趋势
- 告警中心
- 片区供需
- Agent 智能助手
- 调度方案比较
- 建议审核
- 知识库与设备资料
- 报告与交接班
- 用户与权限

## 本地运行

进入前端目录：

```powershell
cd frontend
```

安装依赖：

```powershell
npm install --registry=https://registry.npmmirror.com
```

启动开发服务器：

```powershell
npm run dev
```

打开登录页：

```text
http://localhost:5173/login
```

生产构建：

```powershell
npm run build
```

一键启动前后端（Windows）：

```powershell
.\启动开发环境.bat
```

也可以在 PowerShell 中执行：

```powershell
.\启动开发环境.ps1
```

脚本会分别打开后端和前端终端窗口。后端地址为 `http://127.0.0.1:8000`，前端地址为 `http://127.0.0.1:5173/login`。前端页面可以在后端暂不可用时显示部分本地示例，但登录、通知、告警、报告和工单等联调功能需要后端保持运行。

构建后单地址运行：

```powershell
cd frontend
npm.cmd run build
cd ..\backend
..\.venv\Scripts\python.exe -m app
```

当 `frontend/dist` 存在时，FastAPI 会同时提供前端页面和 `/api/v1` 接口，打开 `http://127.0.0.1:8000` 即可使用，不需要启动 Vite。

单地址一键启动：

```text
双击 启动单地址模式.bat
```

该脚本会先构建前端，再只启动 FastAPI；浏览器打开 `http://127.0.0.1:8000` 即可使用完整页面和接口。

单地址启动时，FastAPI 会先提供页面和基础接口，再在后台准备 RAG 的 Embedding、重排模型和知识索引。
可访问 `GET /api/v1/health` 查看 `startup.status`：`starting` 表示准备中，`ready` 表示完成，
`degraded` 或 `failed` 表示 RAG 降级但基础接口仍可使用。自动化测试如需等待 RAG 完成，可设置
`RAG_STARTUP_MODE=blocking`；日常开发建议使用 `background`。

如果出现 `WinError 10048` 或“端口已被占用”，说明 8000 或 5173 端口已有进程使用。请先关闭之前启动的项目窗口，或查找并结束占用对应端口的进程后再重启，不要重复启动多个后端实例。

启动后端（PowerShell）：

```powershell
cd ..\backend
..\.venv\Scripts\python.exe -m app
```

基础和认证接口文档：`http://127.0.0.1:8000/docs`

## DeepSeek 配置

大模型接入是可选能力。Agent 的事实、数值、引用、权限和控制边界仍由后端只读工具与规则逻辑负责；DeepSeek 只参与可选的意图/参数路由和答案措辞整理。

在系统环境变量或项目 `.env` 中配置：

```env
AGENT_LLM_ENABLED=1
AGENT_LLM_ANSWER_ENABLED=1
AGENT_LLM_MODEL=deepseek-chat
AGENT_LLM_TIMEOUT=20
DEEPSEEK_API_KEY=请配置你自己的密钥
```

后端优先读取 `DEEPSEEK_API_KEY`，同时兼容旧变量名 `DEEPSEEKAPIKEY`；可通过 `DEEPSEEK_BASE_URL` 覆盖接口地址。密钥只由后端读取，不应写入前端代码、提交到 Git 或粘贴到 README。

关闭 `AGENT_LLM_ENABLED` 后，Agent 会回退到本地规则模式；关闭 `AGENT_LLM_ANSWER_ENABLED` 后，最终答案不使用模型润色。冒烟测试会自动关闭外部模型调用，避免消耗 API 配额。

## 多 Agent 协作流程

当前 Agent 是共享状态式的专业节点协作流程：

```text
调度协调 Agent
    → 状态 / 趋势 / 诊断 / 事件 / 供需等专业 Agent
    → 各自的只读工具
    → 安全复核 Agent
    → 结构化答案与人工复核提示
```

对应实现位于 `backend/app/agent/workflow.py`，协调器和 SSE 路由位于 `backend/app/agent/orchestrator.py`、`backend/app/routers/agent.py`。目前所有专业 Agent 只能读取 Mock 数据、知识检索结果和权限范围，不能执行启停泵、切阀、压力设定等现场写操作。

Agent 流式接口：`POST /api/v1/chat/stream`

常见 SSE 事件顺序为：`start → agent / tool（一个或多个）→ result → done`。

- `start`：返回会话、模式和计划来源；
- `agent`：返回协调、专业执行和安全复核节点，以及前序 Agent 依赖和当前节点看到的共享证据数量；
- `tool`：返回实际执行 Agent、只读标记、摘要和引用编号；
- `result`：返回事实、建议、引用、置信度、数据质量和待确认项；
- `done`：表示本轮流式分析完成。

同一页面的短追问会复用进程内 `session_id`，例如先问“二泵站压力是多少”，再问“那流量呢”。会话按用户隔离，只保留有限的问句和站点上下文，服务重启后清空，不写入数据库。

## 当前边界

- 使用本地 Mock 数据和前端演示接口；
- Agent 当前以后端规则分析和 SSE 返回为安全回退路径；设置 `AGENT_LLM_ENABLED=1` 后，可使用 DeepSeek 辅助意图和参数路由。另设置 `AGENT_LLM_ANSWER_ENABLED=1` 后，模型可基于用户问题、规则答案摘要和只读工具摘要润色最终措辞，但数值、告警、供需、知识引用和控制边界仍由后端提供；
- 方案比较当前使用后端确定性评分和约束校验，结果只用于人工复核；
- 报告草稿会按当前账号可见站点汇总 Mock 供需与告警指标，并在详情和 Markdown 导出中保留来源编号；
- 站点事件通知支持 Mock 失败记录、失败原因、重试次数和权限范围内的重试操作；
- 不连接 MySQL、SCADA、PLC 或 DCS；
- 不下发启停泵、切阀、压力设定等现场控制命令；
- 分析结果不能作为真实生产调度结论；
- 真实数据接入前，需要重新确认拓扑、测点、单位、阈值和权限。

### 第一阶段本地 RAG 测试

当前项目已支持一个不依赖 MySQL 和 DeepSeek 的本地 Chroma RAG 测试链路。资料导入后先保持“待审”，管理员将状态改为“现行”后才会参与检索。

- Chroma 数据目录：`backend/data/rag_chroma_db/`；
- RAG 状态：`GET /api/v1/knowledge/rag/status`；
- 文档导入：`POST /api/v1/knowledge/import`；
- 文档检索：`GET /api/v1/knowledge/search?q=流量异常`；
- 当前使用本地确定性测试 Embedding，不调用外部大模型；
- 可通过 `RAG_EMBEDDING_PROVIDER=sentence-transformers` 切换真实语义 Embedding，模型由 `RAG_EMBEDDING_MODEL` 指定（默认 `BAAI/bge-small-zh-v1.5`）；首次使用前需要安装 `sentence-transformers` 并准备模型；
- 切换真实模型后会自动使用独立 Chroma 集合，需要重新导入测试资料，避免不同向量空间混写。

该阶段的文档正文和元数据仍保存在进程内，Chroma 只负责切片向量和检索，因此适合联调验证，不作为生产持久化方案。

## 开发文档

- [项目需求](./提水工程供水调度平台项目需求.md)
- [项目规划](./李文聿提水工程供水调度平台项目规划书.md)
- [前端提示词](./前端提示词.md)
- [项目文档与前端使用说明](./项目文档与前端使用说明.md)
- [Mock 阶段回归验收清单](./Mock阶段回归验收清单.md)
- [更新日志](./更新日志.md)
- [开发问题与解决方案](./开发问题与解决方案.md)
- [后端接口调试教程](./后端接口调试教程.md)

## 版本迭代要求

每次版本迭代必须同步更新：

1. `更新日志.md`：记录版本、变更和影响范围；
2. `开发问题与解决方案.md`：记录本次开发遇到的问题、原因、解决方案和验证结果；
3. `README.md`：当运行方式、页面、技术栈或边界发生变化时同步修改。

### Agent 诊断生成工单草稿

Agent 的诊断类回答现在会返回结构化 `work_order_suggestion`。前端只有在完成诊断提问后才启用“生成核查工单草稿”，生成内容会使用最近一次诊断的站点、问题、建议动作和优先级；创建工单仍需经过后端站点权限校验，且不会下发现场控制指令。

### Agent 数据质量提示

Agent 回答会在事实、建议和引用后显示数据质量与限制说明。当前规则驱动阶段固定标记为 `mock`，表示结果来自进程内 Mock 数据，只用于联调和人工复核，不能作为实时生产调度结论。后续接入真实数据源时，后端可使用 `partial`、`live` 或 `stale` 表示数据完整性，前端无需更换展示结构。

回答还会显示“置信度”。它用于区分规则分支的把握程度，不代表真实生产准确率；当前诊断结果显示低置信度，状态、趋势和供需结果显示中等置信度，控制请求拦截显示高置信度。

回答还会列出“待确认项”，用于提示需要现场核查或补充数据的内容。待确认项不会自动创建工单、改变通知状态或执行现场控制。

管理员和值班调度员可以点击“提交人工复核”，把当前答案和待确认项创建为审核待办；审批负责人在建议审核页面继续处理。该操作只写入 Mock 审核和审计记录。

同一条 Agent 答案重复点击不会创建重复审核记录，后端会返回原审核编号。

建议审核页面会把接口返回的 UTC 创建、更新时间转换为浏览器本地时间显示；后端仍统一保存 UTC。

Agent 回答还会显示本次分析的时间范围，例如“过去 2 小时”或“当前 Mock 样本”，帮助区分样本周期和实时结论。

状态、趋势和诊断回答还会显示数据观测时间，并转换为浏览器本地时间；它与答案生成时间分开，便于判断 Mock 数据的新鲜度。

Agent 还会显示数据新鲜度。当前固定 Mock 样本会标记为“已过期”，没有观测时间的结果标记为“未知”。

Agent 后端现在具备共享状态式的专业节点协作：协调 Agent 先校验范围，再由状态、趋势、诊断、事件、供需等专业 Agent 执行各自只读工具；后续节点接收前序节点的共享证据快照，最后由安全复核 Agent 汇总检查。SSE 会返回真实执行的 Agent 节点、工具归属、前序依赖和共享证据数量；当前事实仍来自 Mock 数据，不执行现场写操作。

Agent 页面同一轮对话会自动携带进程内 `session_id`，支持“二泵站压力是多少”后继续追问“那流量呢”。会话按用户隔离，只保留最近问句和站点上下文，服务重启后清空，不写入数据库。

提交前应至少执行：

```powershell
cd frontend
npm.cmd run build
```

```powershell
cd ..\backend
..\.venv\Scripts\python.exe -m compileall -q app
..\.venv\Scripts\python.exe smoke_test.py
```

```powershell
cd ..
git diff --check
```

冒烟测试固定使用 Hash Embedding、关闭重排、关闭知识生成和关闭 Agent 外部模型调用，不需要数据库或 DeepSeek API Key。
