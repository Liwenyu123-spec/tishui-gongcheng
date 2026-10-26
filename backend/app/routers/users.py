"""用户列表、新增和权限修改路由。"""

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status

from ..data.repositories import get_data_source
from ..dependencies import require_roles
from ..schemas.auth import UserResponse
from ..schemas.users import UserCreateRequest, UserPatchRequest
from ..services.audit import record_audit

# 用户管理路由只允许管理员访问，避免普通调度员修改权限配置。
router = APIRouter(prefix="/api/v1", tags=["管理"])
data_source = get_data_source()


def _public_user(username: str) -> UserResponse:
    """移除密码后生成公开用户响应。"""

    # 读取内部用户记录，并在响应模型转换时排除 password 字段。
    user = data_source.users.users()[username]
    return UserResponse(**{key: value for key, value in user.items() if key != "password"})


@router.get("/users", response_model=list[UserResponse])
def users(_: dict = Depends(require_roles("admin"))) -> list[UserResponse]:
    """返回所有用户的公开信息，不返回密码。"""

    # 遍历用户名生成公开列表，密码不会进入响应模型。
    # 返回顺序沿用内存用户字典顺序，便于联调时稳定查看结果。
    return [_public_user(username) for username in data_source.users.users()]


@router.post("/users", response_model=UserResponse)
def create_user(payload: UserCreateRequest, _: dict = Depends(require_roles("admin"))) -> UserResponse:
    """创建一个内存 Mock 用户并记录审计事件。"""

    # 用户名是内存字典键，先做唯一性校验再生成新用户编号。
    if payload.username in data_source.users.users():
        # 用户名作为字典键必须唯一，否则无法区分后续登录账号。
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="用户名已存在")
    # 使用短 UUID 生成便于日志和页面展示的用户编号。
    user_id = f"user-{uuid4().hex[:10]}"
    # 将请求中的身份、角色、功能权限和站点范围保存到 Mock 用户表。
    data_source.users.users()[payload.username] = {
        "password": payload.password,
        "id": user_id,
        "username": payload.username,
        "display_name": payload.display_name,
        "role": payload.role,
        "permissions": payload.permissions,
        # 保存创建请求中的站点范围，后续接口会据此执行站点权限过滤。
        "station_ids": payload.station_ids,
    }
    commit = getattr(data_source, "commit_user", None)
    if commit is not None and not commit(payload.username, data_source.users.users()[payload.username], creating=True):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="用户未能写入数据库")
    # 新用户创建后立即返回公开字段；密码只留在内存内部记录中。
    # 用户新增属于管理操作，需要写入审计记录。
    record_audit("create", "user", user_id, f"创建用户 {payload.username}")
    return _public_user(payload.username)


@router.patch("/users/{user_id}", response_model=UserResponse)
def update_user(user_id: str, payload: UserPatchRequest, _: dict = Depends(require_roles("admin"))) -> UserResponse:
    """只更新请求中实际提供的用户字段。"""

    # 用户接口使用 user_id 更新，因此先反向查找字典中的用户名。
    username = next((name for name, user in data_source.users.users().items() if user["id"] == user_id), None)
    if username is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    # 排除未提交字段，避免 PATCH 请求把已有权限覆盖为空值。
    updates = payload.model_dump(exclude_none=True)
    # 空 PATCH 不会改变用户记录，但仍按一次合法管理请求继续返回当前用户。
    # 只更新请求实际提供的字段，并保留用户密码等未开放字段。
    data_source.users.users()[username].update(updates)
    commit = getattr(data_source, "commit_user", None)
    if commit is not None and not commit(username, data_source.users.users()[username], creating=False):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="用户已被其他人更新，请刷新后再修改")
    # 用户权限或展示信息变化需要留下审计记录，便于追踪管理操作。
    record_audit("update", "user", user_id, f"修改用户 {username}")
    return _public_user(username)


@router.delete("/users/{user_id}")
def delete_user(user_id: str, current: dict = Depends(require_roles("admin"))) -> dict:
    """删除一个账号。不能删除当前登录账号，也不能删掉最后一个管理员。"""

    username = next((name for name, user in data_source.users.users().items() if user["id"] == user_id), None)
    if username is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    if username == current.get("username"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="不能删除当前登录的账号")
    target = data_source.users.users()[username]
    admins = [user for user in data_source.users.users().values() if user.get("role") == "admin"]
    if target.get("role") == "admin" and len(admins) <= 1:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="至少保留一个管理员")
    remove = getattr(data_source, "delete_user", None)
    if remove is not None:
        remove(username)
    data_source.users.users().pop(username, None)
    expired = [token for token, owner in data_source.users.tokens().items() if owner == username]
    for token in expired:
        data_source.users.tokens().pop(token, None)
    record_audit("delete", "user", user_id, f"删除用户 {username}")
    return {"deleted": user_id}
