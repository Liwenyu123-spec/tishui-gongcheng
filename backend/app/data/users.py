"""认证和用户管理共用的内存用户数据。"""

# 内存用户表：真实数据库接入后应替换为用户服务或 Repository。
# 每个用户记录包含登录信息、业务角色、功能权限和可访问站点范围。
_USERS = {
    # 管理员拥有全部功能和全部站点范围。
    "admin": {
        "password": "admin123",
        "id": "user-admin",
        "username": "admin",
        "display_name": "系统管理员",
        "role": "admin",
        "permissions": ["read", "ask", "submit_scheme", "review", "knowledge", "audit"],
        "station_ids": ["*"],
    },
    # 运行调度员可以查询和提交业务内容，但不能管理用户。
    "operator": {
        "password": "operator123",
        "id": "user-operator",
        "username": "operator",
        "display_name": "运行值班员",
        "role": "operator",
        "permissions": ["read", "ask", "submit_scheme"],
        "station_ids": ["*"],
    },
    # 专用站点账号只授权二泵站，用于验证最小站点权限。
    "station-operator": {
        "password": "station123",
        "id": "user-station-operator",
        "username": "station-operator",
        "display_name": "二泵站值班员",
        "role": "operator",
        "permissions": ["read"],
        "station_ids": ["pump-02"],
    },
}

# 固定 Token 到用户名的映射，仅用于模拟阶段调试认证流程。
# 服务重启后映射仍由代码重新加载，不代表真实会话或刷新令牌机制。
_TOKENS = {
    "mock-token-admin": "admin",
    "mock-token-operator": "operator",
    "mock-token-station-operator": "station-operator",
}
