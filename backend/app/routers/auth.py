"""登录、当前用户和退出登录路由。"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from ..data.users import _USERS
from ..dependencies import get_current_username
from ..schemas.auth import LoginRequest, LoginResponse, LogoutResponse, UserResponse

router = APIRouter(prefix="/api/v1/auth", tags=["认证"])


def _public_user(username: str) -> UserResponse:
    """移除密码后生成公开用户响应。"""

    user = _USERS[username]
    return UserResponse(**{key: value for key, value in user.items() if key != "password"})


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest) -> LoginResponse:
    """校验 Mock 用户名和密码并签发固定 Token。"""

    user = _USERS.get(payload.username)
    if not user or user["password"] != payload.password:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    return LoginResponse(access_token=f"mock-token-{payload.username}", user=_public_user(payload.username))


@router.get("/me", response_model=UserResponse)
def me(username: Annotated[str, Depends(get_current_username)]) -> UserResponse:
    """返回 Token 对应的当前用户。"""

    return _public_user(username)


@router.post("/logout", response_model=LogoutResponse)
def logout(_: Annotated[str, Depends(get_current_username)]) -> LogoutResponse:
    """验证 Token 后返回退出确认；Mock 阶段不需要服务端销毁 Token。"""

    return LogoutResponse()
