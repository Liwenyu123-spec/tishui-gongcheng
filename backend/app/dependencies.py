"""FastAPI 依赖函数。"""

from typing import Annotated

from fastapi import Header, HTTPException, status

from .data.users import _TOKENS


def get_current_username(authorization: Annotated[str | None, Header()] = None) -> str:
    """解析并校验 Authorization: Bearer <token> 请求头。"""

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
