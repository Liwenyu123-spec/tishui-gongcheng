"""认证相关的请求和响应模型。"""

from datetime import datetime

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """健康检查响应。"""

    status: str = "ok"
    service: str = "water-dispatch-backend"
    environment: str = "mock"
    timestamp: datetime


class LoginRequest(BaseModel):
    """登录请求体。"""

    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class UserResponse(BaseModel):
    """对外返回的用户信息，不包含密码。"""

    id: str
    username: str
    display_name: str
    role: str
    permissions: list[str]


class LoginResponse(BaseModel):
    """登录成功后返回 Token 和用户信息。"""

    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class LogoutResponse(BaseModel):
    """退出登录响应。"""

    success: bool = True
    message: str = "已退出登录"
