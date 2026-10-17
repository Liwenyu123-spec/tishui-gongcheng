"""认证和用户管理共用的内存用户数据。"""

# 内存用户表：真实数据库接入后应替换为用户服务或 Repository。
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

# 固定 Token 到用户名的映射，仅用于模拟阶段调试认证流程。
_TOKENS = {"mock-token-admin": "admin", "mock-token-operator": "operator"}
