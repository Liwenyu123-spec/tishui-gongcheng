from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_CENTER, TA_LEFT
out='output/pdf/李文聿_简历_更新版.pdf'
pdfmetrics.registerFont(TTFont('Noto',r'C:\Windows\Fonts\NotoSansSC-VF.ttf'))
styles=getSampleStyleSheet()
navy=colors.HexColor('#123B5D'); blue=colors.HexColor('#2F6B8A'); gray=colors.HexColor('#5B6570')
styles.add(ParagraphStyle('Name',fontName='Noto',fontSize=22,leading=27,textColor=navy,alignment=TA_CENTER,spaceAfter=3))
styles.add(ParagraphStyle('Sub',fontName='Noto',fontSize=10,leading=15,textColor=gray,alignment=TA_CENTER))
styles.add(ParagraphStyle('H',fontName='Noto',fontSize=12.5,leading=18,textColor=navy,spaceBefore=5,spaceAfter=3))
styles.add(ParagraphStyle('Body',fontName='Noto',fontSize=8.7,leading=12.5,textColor=colors.HexColor('#20262D'),spaceAfter=2))
styles.add(ParagraphStyle('Small',fontName='Noto',fontSize=8.5,leading=12.5,textColor=gray))
styles.add(ParagraphStyle('Proj',fontName='Noto',fontSize=10,leading=14,textColor=navy,spaceAfter=1))

def P(t,s='Body'): return Paragraph(t,styles[s])
def bullet(t): return P('• '+t)

doc=SimpleDocTemplate(out,pagesize=A4,rightMargin=14*mm,leftMargin=14*mm,topMargin=9*mm,bottomMargin=9*mm)
story=[]
story += [P('李文聿','Name'), P('求职方向：AI 应用开发 / RAG 应用开发','Sub'), P('24岁  |  18335367635  |  18335367635@163.com','Sub'), Spacer(1,5)]
# summary
story += [P('个人概况','H'), P('具备 Python、FastAPI、Vue 3、Chroma/RAG 与 Linux 基础，能够独立完成从文档导入、向量检索、Prompt 组织到问答接口与前端联调的完整闭环。关注检索质量、引用可追溯性、权限边界与工程化测试，已完成知识库问答系统和提水工程供水调度平台两个可运行项目。')]
story += [P('教育背景','H'), P('<b>山东农业大学</b>　本科　2021-2025'), P('学习课程：数学分析、工程数学、概率论与数理统计、线性代数等。')]
story += [P('技术能力','H')]
for t in [
'<b>编程与后端：</b>Python、FastAPI、REST API、SSE 流式接口、Pydantic；能编写脚本完成数据处理、文件读写和业务逻辑。',
'<b>RAG 与大模型：</b>掌握文档切分、Embedding、向量检索、Prompt 设计、上下文拼接与引用返回；了解 Hybrid Search、BM25、RRF、Rerank、CRAG、Self-RAG、GraphRAG、Multi-Query、HyDE、Step-Back。',
'<b>数据与基础设施：</b>Chroma、Qdrant、Neo4j（可选图谱）、MySQL 基础、Linux 常用命令与日志排障。',
'<b>前端与工程化：</b>Vue 3、TypeScript、Vite、Element Plus、ECharts；pytest、冒烟测试、回归检查、Git。']:
 story.append(bullet(t))
story += [P('项目经历','H')]
# project 1
story += [P('<b>提水工程供水调度平台</b>　个人项目　2026','Proj'), P('<b>技术栈：</b>Vue 3 / TypeScript / Vite / Element Plus / ECharts / FastAPI / Python / Chroma / SSE')]
for t in [
'面向提水工程运行监控与调度辅助，搭建登录、运行总览、工程拓扑、站点趋势、告警中心、片区供需、知识库、Agent 助手、方案比较、审核和报告等业务模块。',
'设计共享状态式多 Agent 工作流：协调节点先校验问题范围，再调用状态、趋势、诊断、事件、供需等只读专业工具，最后由安全复核节点汇总证据；通过 SSE 返回 agent/tool/result/done 事件、引用、置信度、数据质量与待确认项。',
'实现本地 Chroma RAG 联调链路，支持文档导入、现行状态管理、术语归一化、混合评分、来源指纹去重和引用返回；预留 sentence-transformers Embedding 与真实数据源接入边界。',
'建立安全边界和测试门禁：Agent 仅支持只读分析，不执行启停泵、切阀等现场控制；覆盖权限范围、健康检查、Agent 限额、RAG 质量和前后端构建的自动化回归。']:
 story.append(bullet(t))
# project 2
story += [Spacer(1,3), P('<b>RAG 知识库文档管理与问答系统</b>　个人项目　2025-2026','Proj'), P('<b>技术栈：</b>Python / FastAPI / Vue / Chroma / Qdrant / Neo4j / DeepSeek / BM25 / Cross-Encoder')]
for t in [
'实现文档上传、切分、Embedding、Chroma/Qdrant 入库、语义搜索、一次性问答和多轮会话，提供来源片段与过程信息。',
'将问答流程模块化为 Retrieve Gate、预检索、向量/混合检索、重排、压缩、CRAG、GraphRAG、生成与评估等 AskModule，支持预设与配置合并。',
'集成 BM25+向量混合检索、RRF 融合、查询改写/HyDE/Step-Back、Cross-Encoder 重排、Self-RAG/CRAG、Neo4j 图谱双通道和可选 Tavily 联网检索。',
'构建检索评估与功能测试，覆盖 Hit Rate、MRR、Precision@K、Recall@K、引用完整性及知识库管理；通过 FastAPI 接口和 Vue 页面展示答案、来源、优化过程与评估结果。']:
 story.append(bullet(t))
story += [P('校园与实践','H')]
for t in ['参加校级创新创业类活动，完成项目方案撰写与展示。','参与大学生创新创业训练计划，负责资料整理、系统设计与项目汇报。','完成图像处理、目标识别/检测及道路场景相关课程设计或实践。']:
 story.append(bullet(t))
story += [P('自我评价','H'), P('学习主动，能快速阅读项目代码与文档并定位问题；重视可验证的功能边界、日志与测试，能够将 RAG 能力落到具体业务流程中。')]
doc.build(story)
print(out)

