"""FastAPI 认证和角色权限依赖函数。"""

from typing import Annotated, Any, Callable

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .data.users import _TOKENS, _USERS
from .services.audit import record_audit

# 使用 FastAPI 标准 Bearer 方案，让 Swagger 的 Authorize 按钮可以自动注入请求头。
bearer_scheme = HTTPBearer(auto_error=False)

def get_current_username(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(bearer_scheme)] = None,
) -> str:
    """解析并校验 Authorization: Bearer <token> 请求头。"""

    # 没有 Bearer 凭据时，统一返回认证错误，避免受保护接口泄露数据。
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少 Bearer Token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # HTTPBearer 已经解析 Bearer 前缀，这里只用凭据值查找 Mock Token 对应的用户名。
    username = _TOKENS.get(credentials.credentials.strip())
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 无效或已过期",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return username


def get_current_user(username: Annotated[str, Depends(get_current_username)]) -> dict[str, Any]:
    """根据已验证的 Token 返回当前用户内部记录。"""

    # Token 校验通过后，再从用户字典中读取完整权限记录。
    user = _USERS.get(username)
    if user is None:
        # Token 映射和用户表不一致时，按认证失败处理，避免继续使用残缺用户。
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在")
    return user


def require_roles(*allowed_roles: str) -> Callable[..., dict[str, Any]]:
    """创建角色依赖；角色不满足时返回 403 并写入审计记录。"""

    def dependency(user: Annotated[dict[str, Any], Depends(get_current_user)]) -> dict[str, Any]:
        """FastAPI 实际调用的角色校验函数。"""

        # 读取当前账号角色，并与路由声明的允许角色集合进行比较。
        role = str(user.get("role", ""))
        if role not in allowed_roles:
            # 权限拒绝也写入审计日志，便于管理员追踪越权访问。
            record_audit(
                "forbidden",
                "permission",
                str(user.get("id")) if user.get("id") else None,
                f"角色 {role or 'unknown'} 无权执行此操作，要求角色：{', '.join(allowed_roles)}",
            )
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前角色无权执行此操作")
        return user

    return dependency


def user_has_station_access(user: dict[str, Any], station_id: str) -> bool:
    """判断用户是否被授权访问指定站点；`*` 表示全站点范围。"""

    # 没有配置范围时沿用全站点兼容策略；明确配置 `*` 也表示全站点。
    station_ids = user.get("station_ids") or ["*"]
    return "*" in station_ids or station_id in station_ids


def require_station_access(*allowed_roles: str) -> Callable[..., dict[str, Any]]:
    """创建同时校验角色和路径站点范围的依赖。"""

    def dependency(
        station_id: str,
        user: Annotated[dict[str, Any], Depends(get_current_user)],
    ) -> dict[str, Any]:
        """FastAPI 实际调用的角色和站点范围联合校验函数。"""

        # 路径中的 station_id 来自请求 URL，必须同时检查角色和站点授权。
        role = str(user.get("role", ""))
        if role not in allowed_roles or not user_has_station_access(user, station_id):
            # 记录被拒绝的站点和账号，避免只在前端显示 403 而没有后台依据。
            record_audit(
                "forbidden",
                "station_scope",
                station_id,
                f"用户 {user.get('username', 'unknown')} 无权访问站点 {station_id}",
            )
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前账号无权访问该站点")
        return user

    return dependency
