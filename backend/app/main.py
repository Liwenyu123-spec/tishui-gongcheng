"""模拟阶段的 FastAPI 后端入口。

应用初始化和路由注册保留在这里；各业务接口按领域拆到独立路由包。
"""

# Path 用于定位项目根目录下的前端构建产物。
from pathlib import Path
from threading import Thread
import asyncio
import logging
import time

# FastAPI 应用对象负责创建服务和注册中间件。
from fastapi import FastAPI, HTTPException, status
# CORS 允许本地 Vue 前端从 5173 端口访问 8000 端口的后端。
from fastapi.middleware.cors import CORSMiddleware
# FileResponse 返回前端入口文件，StaticFiles 提供构建后的静态资源。
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .routers.auth import router as auth_router
from .routers.audit import router as audit_router
from .routers.agent import router as agent_router
from .routers.health import router as health_router
from .routers.imports import router as imports_router
from .routers.incidents import router as incidents_router
from .routers.monitoring import router as monitoring_router
from .routers.photos import router as photos_router
from .routers.reports import router as reports_router
from .routers.reviews import router as reviews_router
from .routers.schemes import router as schemes_router
from .routers.supply import router as supply_router
from .routers.work_orders import router as work_orders_router
from .routers.users import router as users_router
from .routers.knowledge import router as knowledge_router
from .services.runtime_env import windows_env
from .services.startup_state import mark_failed, mark_finished, mark_phase, mark_starting


logger = logging.getLogger(__name__)

# 创建 FastAPI 应用对象；Swagger 文档会读取这里的元数据。
app = FastAPI(
    # Swagger 页面显示的项目名称。
    title="提水工程供水调度平台 API",
    # 当前模拟阶段的后端版本。
    version="0.10.306",
    # Swagger 页面显示的项目说明。
    description="本地联调接口。业务记录和测试遥测在 MySQL，不连接现场设备，不下发控制指令。",
)

# 注册跨域中间件，使 Vue 开发服务器可以请求本地后端。
app.add_middleware(
    CORSMiddleware,
    # 只允许当前前端开发地址访问。
    allow_origins=["http://localhost:5173"],
    # 允许浏览器携带认证信息。
    allow_credentials=True,
    # Mock 阶段允许常见 HTTP 方法。
    allow_methods=["*"],
    # Mock 阶段允许所有请求头，便于发送 Authorization。
    allow_headers=["*"],
)

# 已完成拆分的领域路由在应用入口统一注册。
# 按业务领域注册已经拆分的路由模块，保持统一的 /api/v1 前缀。
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(incidents_router)
app.include_router(monitoring_router)
app.include_router(supply_router)
app.include_router(schemes_router)
app.include_router(reviews_router)
app.include_router(reports_router)
app.include_router(work_orders_router)
app.include_router(users_router)
app.include_router(knowledge_router)
app.include_router(photos_router)
app.include_router(imports_router)
app.include_router(audit_router)
app.include_router(agent_router)

from .data.repositories import get_data_source, use_mysql_source

# 数据库是可选的运行时依赖：开发/冒烟环境没有 MySQL 或 pymysql 时，保留 Mock 数据源，
# 不应因为导入应用模块就直接启动失败。生产部署仍应在启动日志中明确暴露数据库不可用。
try:
    use_mysql_source()
except Exception as exc:  # noqa: BLE001
    logger.warning("MySQL 数据源初始化失败，回退到内存数据源：%s", exc)


_api_lock = asyncio.Lock()


@app.middleware("http")
async def persist_database(request, call_next):
    """接口请求前后同步 MySQL。页面和静态文件不进出数据库。"""

    if not request.url.path.startswith("/api/"):
        return await call_next(request)
    source = get_data_source()
    is_read = request.method in {"GET", "HEAD", "OPTIONS"}
    async with _api_lock:
        reload = getattr(source, "reload_stations_and_users", None)
        if reload is not None:
            try:
                await asyncio.to_thread(reload)
            except Exception as exc:  # noqa: BLE001
                logger.warning("MySQL 请求前刷新失败，继续使用当前数据：%s", exc)
        response = await call_next(request)
        if not is_read and response.status_code < 500:
            flush = getattr(source, "flush", None)
            if flush is not None:
                try:
                    await asyncio.to_thread(flush)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("MySQL 请求后写回失败：%s", exc)
        return response


@app.on_event("startup")
def refresh_knowledge_index_on_startup() -> None:
    """启动时准备 RAG 引擎并从磁盘重建知识索引。

    默认采用后台模式：FastAPI 先完成启动，RAG 在独立线程中预热和重建。
    需要严格等待 RAG 准备完成的自动化测试可以设置 RAG_STARTUP_MODE=blocking。
    """

    mode = (windows_env("RAG_STARTUP_MODE") or "background").strip().lower()

    def prepare_rag() -> None:
        started = time.monotonic()
        mark_starting(mode)
        logger.info("RAG 启动准备开始（模式=%s）", mode)
        try:
            from .routers.knowledge import rebuild_knowledge_index
            from .services.rag_chroma import warmup_rag

            mark_phase("warmup", "正在加载 Embedding 和重排模型")
            warmup = warmup_rag()
            mark_phase("reindex", "正在重建知识库索引")
            rebuild_knowledge_index()
            degraded = not bool(warmup.get("ok", False))
            message = (
                "RAG 已就绪"
                if not degraded
                else "RAG 已启动但处于降级模式，请查看知识库状态"
            )
            elapsed = time.monotonic() - started
            mark_finished(elapsed_seconds=elapsed, degraded=degraded, message=message)
            logger.info("%s（耗时 %.2f 秒）", message, elapsed)
        except Exception as exc:  # noqa: BLE001
            elapsed = time.monotonic() - started
            mark_failed(elapsed_seconds=elapsed, error=str(exc))
            logger.exception("RAG 启动准备失败，普通接口继续提供服务")

    if mode in {"blocking", "sync", "synchronous"}:
        prepare_rag()
        return

    # daemon 线程不会阻止开发服务关闭；服务接口和前端页面可以先启动。
    Thread(target=prepare_rag, name="rag-startup", daemon=True).start()


# 前端构建目录位于项目根目录的 frontend/dist；开发时可以先执行 npm run build。
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
FRONTEND_INDEX = FRONTEND_DIST / "index.html"

# dist 存在时，FastAPI 同时提供前端页面，实现单地址访问；未构建前端时不影响 API 和 Swagger。
if FRONTEND_INDEX.is_file():
    # Vite 构建后的 JS、CSS 和图片统一从 /assets 路径提供。
    assets_dir = FRONTEND_DIST / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="frontend-assets")

    @app.get("/", include_in_schema=False)
    def frontend_index() -> FileResponse:
        """返回前端应用入口页面。"""

        return FileResponse(FRONTEND_INDEX)

    @app.get("/{full_path:path}", include_in_schema=False)
    def frontend_spa_fallback(full_path: str) -> FileResponse:
        """将 Vue 前端路由回退到 index.html，保证刷新子页面不会 404。"""

        # 未注册的 API 路径仍返回 404，避免把接口错误伪装成前端页面。
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="接口不存在")
        # 前端资源由 /assets 挂载处理，其余页面路径交给 Vue Router。
        return FileResponse(FRONTEND_INDEX)
