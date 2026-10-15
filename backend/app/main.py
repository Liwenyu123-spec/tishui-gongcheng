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


class Station(BaseModel):
    id: str
    name: str
    sequence: int
    station_type: str
    status: str
    source: str = "mock"


class StationDetail(Station):
    location: str
    description: str
    metrics: list[str]


class TopologyNode(BaseModel):
    station_id: str
    name: str
    sequence: int


class TopologyEdge(BaseModel):
    source: str
    target: str
    direction: str = "downstream"


class TopologyResponse(BaseModel):
    version: str
    confirmed_at: datetime
    source: str = "mock"
    nodes: list[TopologyNode]
    edges: list[TopologyEdge]


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

_STATIONS = [
    {
        "id": "jq-01",
        "name": "集泉一站",
        "sequence": 1,
        "station_type": "取水泵站",
        "status": "running",
        "location": "集泉取水口",
        "description": "工程上游取水及一级提水站点。",
        "metrics": ["flow", "pressure", "level", "energy"],
    },
    {
        "id": "pump-01",
        "name": "一泵站",
        "sequence": 2,
        "station_type": "加压泵站",
        "status": "running",
        "location": "输水干线 1+200",
        "description": "承担一级输水加压。",
        "metrics": ["flow", "pressure", "energy"],
    },
    {
        "id": "pump-02",
        "name": "二泵站",
        "sequence": 3,
        "station_type": "加压泵站",
        "status": "warning",
        "location": "输水干线 4+800",
        "description": "承担中段输水加压。",
        "metrics": ["flow", "pressure", "level", "energy"],
    },
    {
        "id": "pump-03",
        "name": "三泵站",
        "sequence": 4,
        "station_type": "加压泵站",
        "status": "running",
        "location": "输水干线 8+600",
        "description": "承担中下游输水加压。",
        "metrics": ["flow", "pressure", "energy"],
    },
    {
        "id": "pump-04",
        "name": "四泵站",
        "sequence": 5,
        "station_type": "末端泵站",
        "status": "running",
        "location": "平定城区入口",
        "description": "承担末端供水调节。",
        "metrics": ["flow", "pressure", "level", "energy"],
    },
    {
        "id": "pingding-inlet",
        "name": "平定侧入口",
        "sequence": 6,
        "station_type": "供水入口",
        "status": "running",
        "location": "平定城区",
        "description": "工程输水进入片区的入口节点。",
        "metrics": ["flow", "pressure"],
    },
]


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


@app.get("/api/v1/topology", response_model=TopologyResponse, tags=["拓扑"])
def topology() -> TopologyResponse:
    nodes = [TopologyNode(station_id=s["id"], name=s["name"], sequence=s["sequence"]) for s in _STATIONS]
    edges = [
        TopologyEdge(source=_STATIONS[index]["id"], target=_STATIONS[index + 1]["id"])
        for index in range(len(_STATIONS) - 1)
    ]
    return TopologyResponse(
        version="mock-topology-v1",
        confirmed_at=datetime(2026, 10, 15, tzinfo=timezone.utc),
        nodes=nodes,
        edges=edges,
    )


@app.get("/api/v1/stations", response_model=list[Station], tags=["站点"])
def stations() -> list[Station]:
    return [Station(**{key: station[key] for key in Station.model_fields}) for station in _STATIONS]


@app.get("/api/v1/stations/{station_id}", response_model=StationDetail, tags=["站点"])
def station_detail(station_id: str) -> StationDetail:
    station = next((item for item in _STATIONS if item["id"] == station_id), None)
    if station is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="站点不存在")
    return StationDetail(**station)
