"""登录、当前用户和退出登录路由。"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from ..data.repositories import get_data_source, save_row
from ..dependencies import get_current_username
from ..schemas.auth import LoginRequest, LoginResponse, LogoutResponse, UserResponse

# 认证路由不受业务角色限制，但除登录外的接口仍需携带有效 Token。
router = APIRouter(prefix="/api/v1/auth", tags=["认证"])
data_source = get_data_source()


def _public_user(username: str) -> UserResponse:
    """移除密码后生成公开用户响应。"""

    # 只从内部用户记录中提取公开字段，避免把密码返回给前端。
    user = data_source.users.users()[username]
    return UserResponse(**{key: value for key, value in user.items() if key != "password"})


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest) -> LoginResponse:
    """校验 Mock 用户名和密码并签发固定 Token。"""

    # 根据用户名读取 Mock 用户，并校验明文密码（仅限当前演示阶段）。
    user = data_source.users.users().get(payload.username)
    if not user or user["password"] != payload.password:
        # 用户不存在和密码不匹配统一返回 401，避免泄露账号是否存在。
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    # Token 使用固定前缀拼接用户名，便于本地联调时在 Swagger 中复用。
    # 响应同时返回去除密码后的用户信息，前端可据此初始化权限和站点范围。
    access_token = f"mock-token-{payload.username}"
    # 新建用户首次登录时，将签发的 Mock Token 注册到内存映射中。
    data_source.users.tokens()[access_token] = payload.username
    save_row("commit_token", access_token, payload.username)
    return LoginResponse(access_token=access_token, user=_public_user(payload.username))


@router.get("/me", response_model=UserResponse)
def me(username: Annotated[str, Depends(get_current_username)]) -> UserResponse:
    """返回 Token 对应的当前用户。"""

    # Token 依赖已经完成认证，这里只负责返回当前账号的公开信息。
    # 密码等内部字段不会进入 UserResponse。
    return _public_user(username)


@router.post("/logout", response_model=LogoutResponse)
def logout(_: Annotated[str, Depends(get_current_username)]) -> LogoutResponse:
    """验证 Token 后返回退出确认；Mock 阶段不需要服务端销毁 Token。"""

    # Mock Token 没有服务端会话状态，验证 Token 后返回退出成功即可。
    return LogoutResponse()
