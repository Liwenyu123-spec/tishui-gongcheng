"""认证相关的请求和响应模型。"""

from datetime import datetime

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """健康检查响应。"""

    # 健康检查结果，正常时返回 ok。
    status: str = "ok"
    # 当前提供接口的服务名称。
    service: str = "water-dispatch-backend"
    # 运行环境标记，当前项目使用 Mock 数据。
    environment: str = "mock"
    # 服务器生成本次检查响应的时间。
    timestamp: datetime


class LoginRequest(BaseModel):
    """登录请求体。"""

    # 登录账号，限制长度以避免无效或过大的请求。
    username: str = Field(min_length=1, max_length=64)
    # 登录密码；当前 Mock 登录只做账号密码校验。
    password: str = Field(min_length=1, max_length=128)


class UserResponse(BaseModel):
    """对外返回的用户信息，不包含密码。"""

    # 用户唯一标识。
    id: str
    # 用于登录的账号名。
    username: str
    # 页面展示的用户名称。
    display_name: str
    # 用户角色，决定默认权限范围。
    role: str
    # 当前用户可以调用的权限编码列表。
    permissions: list[str]
    # 用户可访问的站点编号；星号表示不限制站点范围。
    station_ids: list[str] = Field(default_factory=list)


class LoginResponse(BaseModel):
    """登录成功后返回 Token 和用户信息。"""

    # 登录后返回的访问令牌，后续业务请求放入 Bearer 请求头。
    access_token: str
    # 令牌认证方式，前端应使用 bearer 方式发送。
    token_type: str = "bearer"
    # 与令牌对应的用户信息。
    user: UserResponse


class LogoutResponse(BaseModel):
    """退出登录响应。"""

    # 是否完成退出登录处理。
    success: bool = True
    # 提示前端展示的退出结果。
    message: str = "已退出登录"
