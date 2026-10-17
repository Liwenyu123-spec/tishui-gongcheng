"""用户管理接口的请求模型。"""

from pydantic import BaseModel, Field


class UserCreateRequest(BaseModel):
    """新建用户请求。"""

    # 新用户的登录账号。
    username: str
    # 新用户的登录密码；Mock 阶段由内存用户数据校验。
    password: str
    # 页面展示的用户名称。
    display_name: str
    # 用户角色，未填写时按普通操作员处理。
    role: str = "operator"
    # 用户可以调用的权限编码列表。
    permissions: list[str] = Field(default_factory=list)
    # 用户可访问的站点编号；默认星号表示不限制站点范围。
    station_ids: list[str] = Field(default_factory=lambda: ["*"])


class UserPatchRequest(BaseModel):
    """修改用户时允许提交的可选字段。"""

    # 修改后的展示名称；不传时保持原值。
    display_name: str | None = None
    # 修改后的角色；不传时保持原值。
    role: str | None = None
    # 修改后的权限列表；不传时保持原值。
    permissions: list[str] | None = None
    # 修改后的站点范围；不传时保持原值。
    station_ids: list[str] | None = None
