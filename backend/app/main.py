"""模拟阶段的 FastAPI 后端入口。

应用初始化和路由注册保留在这里；各业务接口按领域拆到独立路由包。
"""

# Path 用于定位项目根目录下的前端构建产物。
from pathlib import Path

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

# 创建 FastAPI 应用对象；Swagger 文档会读取这里的元数据。
app = FastAPI(
    # Swagger 页面显示的项目名称。
    title="提水工程供水调度平台 API",
    # 当前模拟阶段的后端版本。
    version="0.3.0-mock",
    # Swagger 页面显示的项目说明。
    description="模拟阶段后端接口。当前使用内存 Mock 数据，供前后端联调。",
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


@app.on_event("startup")
def refresh_knowledge_index_on_startup() -> None:
    """启动时用当前内存文档重刷 Chroma，避免重启后命中已经不存在的资料。"""

    from .routers.knowledge import rebuild_knowledge_index

    rebuild_knowledge_index()


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
