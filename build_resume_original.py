from reportlab.lib.pagesizes import A4
from reportlab.platypus import *
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.utils import ImageReader
pdfmetrics.registerFont(TTFont('Noto',r'C:\Windows\Fonts\NotoSansSC-VF.ttf'))
out='output/pdf/李文聿_简历_按原结构更新.pdf'
navy=colors.HexColor('#111111'); gray=colors.HexColor('#555555'); line=colors.HexColor('#E5E7EB')
styles=getSampleStyleSheet(); styles.add(ParagraphStyle('Name',fontName='Noto',fontSize=22,leading=26,textColor=navy,spaceAfter=6)); styles.add(ParagraphStyle('Contact',fontName='Noto',fontSize=9.5,leading=18,textColor=gray)); styles.add(ParagraphStyle('H',fontName='Noto',fontSize=15,leading=21,textColor=navy,spaceBefore=12,spaceAfter=5)); styles.add(ParagraphStyle('B',fontName='Noto',fontSize=9.3,leading=16,textColor=colors.HexColor('#333333'))); styles.add(ParagraphStyle('PTitle',fontName='Noto',fontSize=10.5,leading=16,textColor=navy,spaceBefore=4)); styles.add(ParagraphStyle('Tiny',fontName='Noto',fontSize=8.7,leading=14,textColor=gray))
def P(x,s='B'): return Paragraph(x,styles[s])
def lineflow(): return Table([['']],colWidths=[180*mm],rowHeights=[0.5],style=TableStyle([('BACKGROUND',(0,0),(-1,-1),line)]))
def bullets(items): return [P('• '+x) for x in items]
doc=SimpleDocTemplate(out,pagesize=A4,leftMargin=14*mm,rightMargin=14*mm,topMargin=11*mm,bottomMargin=11*mm)
story=[]
# header with photo
head=Table([[P('李文聿','Name'),Image('photo0.png',width=22*mm,height=28*mm)]],colWidths=[160*mm,25*mm],style=TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('ALIGN',(1,0),(1,0),'RIGHT')]))
story += [head,P('男 | 24岁　☎ 18335367635　✉ 18335367635@163.com','Contact'),P('求职意向：AI应用开发','Contact')]
story += [P('个人优势','H'),lineflow()]+bullets(['具备 Python / MySQL / Linux 基础，能独立完成简单脚本开发、数据查询与服务器基础操作。','系统学习过 RAG 检索增强生成，理解文档入库、向量检索、Prompt 与大模型生成全流程，并完成知识库问答与业务 Agent 项目实践。'])
story += [P('专业技能','H'),lineflow()]+bullets(['光学：工程光学、光电学、光辐射测量、照明设计等专业课程。','Python：掌握基础语法与常用数据结构，能编写脚本完成数据处理、文件读写与简单业务逻辑；了解面向对象基础。','MySQL：掌握库表设计基础，熟练使用增删改查、条件查询、排序分页、多表关联与聚合统计；了解索引、主键/外键等基本概念。','Linux：掌握常用命令（文件/目录、权限、进程、管道重定向等），能进行环境查看、日志排查与基础服务操作。','RAG / 大模型应用：了解文档切分、Embedding、向量检索、Prompt 组装与生成；熟悉混合检索、重排、CRAG、Self-RAG、GraphRAG 等概念。'])
story += [P('教育经历','H'),lineflow(),P('<b>大连工业大学</b>　本科　光源与照明　　　　　　　　　　　　　　　2021-2025'),P('参加多项校内比赛：大学生照明产品设计大赛、全国大学生半导体光源系统创新竞赛；独立参与单片机控制系统及数字电路实践；本科毕业设计为某大楼外立面照明设计，由本人独立完成。')]
story += [P('项目经历','H'),lineflow(),P('<b>rag搜索引擎项目</b>　　　主要开发者','PTitle'),P('<b>RAG 知识库搜索与问答系统</b>')]+bullets(['负责知识库 RAG 全链路：文档切分入库、向量检索、Prompt 组装与 DeepSeek 生成，降低大模型幻觉并支持答案溯源。','实现 Modular RAG 可配置管线：检索前改写/HyDE、向量+BM25 混合检索（RRF）、Cross-Encoder 重排、CRAG/Self-RAG 等模块可按需开关。','使用 Chroma/Qdrant 存储向量，本地中文 Embedding 与 bge-reranker 提升召回与排序质量；可选 Neo4j 图谱与 Tavily 联网增强。','基于 FastAPI 提供检索/问答/入库等 API，Vue 前端完成策略勾选、过程可视化与效果对比演示。'])
story += [Spacer(1,4),P('<b>提水工程供水调度平台</b>　　　主要开发者','PTitle'),P('<b>基于 Agentic RAG 的供水调度辅助平台</b>')]+bullets(['搭建运行总览、工程拓扑、站点趋势、告警中心、片区供需、知识库、Agent 助手、方案比较、审核和报告等业务模块。','设计共享状态式多 Agent 工作流，由协调、状态/趋势/诊断/事件/供需专业节点和安全复核节点协作完成只读分析，并通过 SSE 返回过程事件、证据引用与待确认项。','实现本地 Chroma RAG 联调链路，支持文档导入、现行状态管理、术语归一化、混合评分、来源指纹去重和引用返回。','建立权限、限额和回归测试边界：Agent 不执行启停泵、切阀等现场控制，覆盖健康检查、RAG 质量、Agent 限额及前后端构建检查。'])
doc.build(story)
print(out)
