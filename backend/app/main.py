from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

app = FastAPI(
    title="提水工程供水调度平台 API",
    version="0.3.0-mock",
    description="模拟阶段后端接口。当前仅提供基础和登录认证能力。",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "water-dispatch-backend"
    environment: str = "mock"
    timestamp: datetime


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class UserResponse(BaseModel):
    id: str
    username: str
    display_name: str
    role: str
    permissions: list[str]


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class LogoutResponse(BaseModel):
    success: bool = True
    message: str = "已退出登录"


_USERS = {
    "admin": {
        "password": "admin123",
        "id": "user-admin",
        "username": "admin",
        "display_name": "系统管理员",
        "role": "admin",
        "permissions": ["read", "ask", "submit_scheme", "review", "knowledge", "audit"],
    },
    "operator": {
        "password": "operator123",
        "id": "user-operator",
        "username": "operator",
        "display_name": "运行值班员",
        "role": "operator",
        "permissions": ["read", "ask", "submit_scheme"],
    },
}
_TOKENS = {"mock-token-admin": "admin", "mock-token-operator": "operator"}


def _public_user(username: str) -> UserResponse:
    user = _USERS[username]
    return UserResponse(**{key: value for key, value in user.items() if key != "password"})


def _get_current_username(authorization: Annotated[str | None, Header()] = None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少 Bearer Token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    username = _TOKENS.get(authorization[7:].strip())
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 无效或已过期",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return username


@app.get("/api/v1/health", response_model=HealthResponse, tags=["基础"])
def health() -> HealthResponse:
    return HealthResponse(timestamp=datetime.now(timezone.utc))


@app.post("/api/v1/auth/login", response_model=LoginResponse, tags=["认证"])
def login(payload: LoginRequest) -> LoginResponse:
    user = _USERS.get(payload.username)
    if not user or user["password"] != payload.password:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    return LoginResponse(access_token=f"mock-token-{payload.username}", user=_public_user(payload.username))


@app.get("/api/v1/auth/me", response_model=UserResponse, tags=["认证"])
def me(username: Annotated[str, Depends(_get_current_username)]) -> UserResponse:
    return _public_user(username)


@app.post("/api/v1/auth/logout", response_model=LogoutResponse, tags=["认证"])
def logout(_: Annotated[str, Depends(_get_current_username)]) -> LogoutResponse:
    return LogoutResponse()
