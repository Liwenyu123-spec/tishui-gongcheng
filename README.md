# 提水工程供水调度平台

基于 Agentic RAG 与多智能体协作的提水工程供水调度平台。当前项目处于本地模拟联调阶段，使用 Vue 3、Vite、TypeScript、Element Plus、ECharts 和 FastAPI，业务数据仍来自 Mock 数据，不连接真实数据库和现场控制系统。

## 当前版本

- 项目迭代：`v0.10.220`
- 前端包版本：`0.2.0`
- 当前模式：本地测试、Mock 数据、只读 Agent、多 Agent 专业节点协作
- 前端目录：[frontend](./frontend)
- 后端目录：[backend](./backend)

当前已经可以完成页面浏览、后端接口联调、Agent 流式问答、只读工具分析、知识库检索、方案比较、审核和报告草稿等流程。数据库、真实测点、现场控制和部署仍属于后续阶段。

当前主要业务读取统一经过 `backend/app/data/repositories.py` 的数据访问接口，底层实现仍是 Mock 数据。后续接入数据库或时序数据时，优先替换仓储实现，不直接改动路由、Agent 和前端接口。

知识库文档支持待审、现行、废止和已归档状态；已归档文档不会进入检索结果。

管理员可在知识库文档操作区查看后端文档的审核历史。

知识库引用结果会显示章节路径或“段落/分片”定位，并可继续查看原文片段。

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

### 刷新当前页面

顶栏右上角（「通知」左侧）有统一的「刷新本页」按钮，重新拉取当前页面的后端数据。各页面通过 `frontend/src/composables/pageRefresh.ts` 注册自己的刷新动作，登录页无数据可刷新，按钮会自动置灰。

刷新是幂等的重新取数，不会清空页面状态：站点趋势保留已选站点，用户权限保留正在编辑的权限表单，Agent 助手保留当前对话和会话编号（只刷新工单和站点列表）。

页面上原有的上下文刷新入口仍然可用，例如运行总览的「刷新数据」、报告中心的「刷新列表」「刷新报告详情」、知识库的「刷新状态」和通知弹窗的「刷新通知」。

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
AGENT_TOOL_TIMEOUT=5
AGENT_TOOL_RETRIES=1
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
- `retry` / `error` / `fallback`：工具重试、失败/超时和降级为人工复核提示；
- `result`：返回事实、建议、引用、置信度、数据质量和待确认项；
- `done`：表示本轮流式分析完成。

同一页面的短追问会复用进程内 `session_id`，例如先问“二泵站压力是多少”，再问“那流量呢”。前端按当前账号把会话编号保存到浏览器 `sessionStorage`，页面切换或刷新后仍可继续当前浏览器会话；点击“新建会话”会生成新的会话编号。会话按用户隔离，只保留有限的问句和站点上下文，服务重启后清空，不写入数据库。

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

## 提交前检查与完整回归

分两层，避免每次提交都等最慢的检查：

**日常提交（提交前门禁）**

安装一次即可由 `git commit` 自动触发：

```powershell
.\安装提交检查.ps1
```

也可以用批处理双击安装：`安装提交检查.bat`。门禁依次执行后端编译、pytest 单元用例、Mock 冒烟和 `git diff --check`，约 1 分钟；只改文档的提交会自动跳过代码检查。检查未通过时会把失败记录追加到 `.test-temp\precommit_failures.log`（已在 `.gitignore` 中），便于后台自动同步被拦住后回查。临时绕过用 `git commit --no-verify` 或设置环境变量 `SKIP_PRECOMMIT=1`，需要卸载时执行 `.\安装提交检查.ps1 -卸载`。

手工执行同一套检查：

```powershell
python scripts\pre_commit_check.py
python scripts\pre_commit_check.py --full   # 追加 RAG 质量回归
```

**发布前或里程碑前（完整回归）**

```powershell
.\完整回归.ps1
```

依次执行前端生产构建、后端编译、pytest 单元用例、Mock 冒烟回归、RAG 质量回归和 `git diff --check`，每个子任务都有硬超时，不会因为某个子进程卡住而停在终端。

单独跑某一项：

```powershell
cd frontend
npm.cmd run build
```

```powershell
cd ..\backend
..\.venv\Scripts\python.exe -m compileall -q app
..\.venv\Scripts\python.exe -m pytest tests -q
..\.venv\Scripts\python.exe smoke_test.py
```

```powershell
cd ..
git diff --check
```

验收时对照 [Mock 阶段回归验收清单](./Mock阶段回归验收清单.md)：标「自动化」的条目已由脚本覆盖，标「待人工验证」的页面交互需要人工点击确认。

冒烟测试固定使用 Hash Embedding、关闭重排、关闭知识生成和关闭 Agent 外部模型调用，不需要数据库或 DeepSeek API Key。

RAG 质量回归使用 `backend/rag_eval.py`，会覆盖线上问句清洗、Recall@K、MRR、无答案弃答、可回答误拒和引用完整性（来源编号、标题、版本、正文）检查：

```powershell
cd backend
python rag_eval.py
python rag_eval.py --no-rerank  # 对照测试，预期暴露质量退化
```

评测语料为合成样本，仅用于检索和引用回归，不代表现场资料。

### Agent 运行标识与工具结果（v0.10.164）

每次 Agent 编排运行会生成 `run_id`，并把当前会话编号作为 `thread_id` 传入工具执行上下文；`task_id` 已预留给后续任务状态管理。只读工具结果统一携带工具版本、风险等级、执行起止时间、耗时、重试次数、数据来源和结构化错误码。

当前阶段这些运行信息只保存在进程内，不引入数据库或持久化 checkpoint。常见错误码包括 `TOOL_NOT_FOUND`、`SOURCE_TIMEOUT`、`SOURCE_UNAVAILABLE`、`AUTH_SCOPE_DENIED` 和 `CONTROL_ACTION_BLOCKED`。这些字段用于后续增加调用限额、并发控制和运行追踪，不改变 Agent 只能读取 Mock 数据、不能执行现场控制的边界。

### Agent 工具 SSE 字段补充（v0.10.165）

Agent 的 `tool`、`retry` 和 `error` SSE 事件现在也会返回本次 `run_id`。其中 `tool` 事件会直接显示工具版本、风险等级、执行起止时间、耗时和错误码，便于前端展示和接口调试。

### Agent 调用预算与并发限制（v0.10.166）

Agent 现在支持进程内调用治理：`AGENT_MAX_TOOL_CALLS` 限制单次请求工具调用数，`AGENT_MAX_MODEL_CALLS` 记录模型调用预算配置，`AGENT_MAX_CONCURRENCY` 限制同时运行的 Agent 请求数。超过工具预算返回 `TOOL_BUDGET_EXCEEDED`，并发槽位不足返回 `AGENT_CAPACITY_EXCEEDED`。这些限制当前只在单个后端进程内生效。



### Agent 预算回归测试（v0.10.167）

后端新增 Agent 限额回归测试，验证工具步骤超过 `AGENT_MAX_TOOL_CALLS` 时返回 `TOOL_BUDGET_EXCEEDED`。当前后端测试共 8 项。


### Agent 代码注释补充（v0.10.168）

为 Agent 限额模块、工作流预算逻辑和预算测试补充了中文模块说明、函数职责、关键分支和测试意图注释，不改变运行行为。


### Agent start 事件限额摘要（v0.10.169）

Agent 的 `start` SSE 事件现在返回 `limits` 对象，包含 `max_tool_calls`、`max_model_calls` 和 `max_concurrency`，便于确认当前进程实际使用的限额配置。


### SSE 生命周期运行追踪（v0.10.170）

Agent 的 `agent`、`fallback` 和 `done` 事件现在也返回 `run_id`。同一轮请求的 `start`、`agent`、`tool`、`fallback`、`result` 和 `done` 事件可以通过同一个运行编号关联。


### 模型调用预算生效（v0.10.171）

`AGENT_MAX_MODEL_CALLS` 现在会实际控制模型调用：预算为 0 时跳过模型路由，预算低于 2 次时跳过答案润色，系统保留规则模式答案。


### 工具风险和权限元数据（v0.10.172）

只读工具目录现在声明 `risk_level` 和 `required_permission`。普通读取工具默认是 `low / agent.read`，控制边界检查工具是 `high / agent.control.review`，并会在工具 SSE 事件中返回。


### Agent 前端显示工具风险和权限（v0.10.173）

Agent 分析步骤现在会显示工具的风险等级和所需权限，例如“风险：low；权限：agent.read”。这只是执行契约的可视化，不会改变工具权限。


### Agent 前端运行信息（v0.10.174）

Agent 回答证据区域现在显示本轮 `run_id` 和运行限额，便于用户确认一次分析的追踪编号及当前工具、模型和并发配置。


### RAG 文档指纹（v0.10.175）

知识文档现在保存 `file_hash` 和 `content_hash`，用于识别重复文件、正文变化和后续增量索引。当前导入流程仍使用本地 JSON 和正文文件，不接数据库。


### RAG 重复文档幂等导入（v0.10.176）

知识文档导入现在按文件或正文指纹去重。相同正文即使更换文件名再次导入，也会返回原文档，不创建重复记录；正文变化仍可创建新版本。


### RAG 水务术语归一化（v0.10.177）

知识检索会把常见口语归一化为规程术语，例如“二泵”转为“二泵站”、“压强”转为“压力”、“电流过高”转为“运行电流超限”。原始问题仍保留，归一化只用于检索。


### RAG 轻量混合评分（v0.10.178）

Chroma 语义召回结果现在会叠加查询词在标题、文件名和正文中的命中分，增强泵站编号和专业术语的精确匹配。现有权限、有效期、重排和弃答门槛保持不变。
