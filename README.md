# 提水工程供水调度平台

基于 Agentic RAG 与多智能体协作的提水工程供水调度平台。当前仓库处于前端原型阶段，使用 Vue 3、Vite、TypeScript、Element Plus 和 ECharts，暂时使用 Mock 数据，不连接真实数据库和现场控制系统。

## 当前版本

- 前端版本：`0.2.3`
- 当前模式：测试环境、Mock 数据、只读分析
- 前端目录：[frontend](./frontend)

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

## 当前边界

- 使用本地 Mock 数据和前端演示接口；
- 不连接 MySQL、SCADA、PLC 或 DCS；
- 不下发启停泵、切阀、压力设定等现场控制命令；
- 分析结果不能作为真实生产调度结论；
- 真实数据接入前，需要重新确认拓扑、测点、单位、阈值和权限。

## 开发文档

- [项目需求](./提水工程供水调度平台项目需求.md)
- [项目规划](./李文聿提水工程供水调度平台项目规划书.md)
- [前端提示词](./前端提示词.md)
- [更新日志](./更新日志.md)
- [开发问题与解决方案](./开发问题与解决方案.md)

## 版本迭代要求

每次版本迭代必须同步更新：

1. `更新日志.md`：记录版本、变更和影响范围；
2. `开发问题与解决方案.md`：记录本次开发遇到的问题、原因、解决方案和验证结果；
3. `README.md`：当运行方式、页面、技术栈或边界发生变化时同步修改。

提交前应至少执行：

```powershell
npm run build
git diff --check
```
