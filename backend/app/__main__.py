"""支持通过 ``python -m app`` 启动本地 FastAPI 服务。"""

# Uvicorn 是运行 FastAPI ASGI 应用的开发服务器。
import uvicorn


if __name__ == "__main__":
    # 使用字符串导入 app.main:app，让 Uvicorn 能定位 FastAPI 应用对象。
    # 当前关闭 reload，避免共享虚拟环境路径问题触发子进程启动失败。
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000)
