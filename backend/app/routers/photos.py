"""现场照片注册与中文图文检索。

照片与向量索引只落盘到 backend/data，不连接业务数据库。
"""

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from ..data.repositories import get_data_source
from ..dependencies import require_roles, user_has_station_access
from ..services.photo_store import get_photo_index

router = APIRouter(prefix="/api/v1", tags=["Photos"])
data_source = get_data_source()


def _photo_visible(station_id: str | None, user: dict) -> bool:
    return station_id is None or user_has_station_access(user, station_id)


@router.get("/photos/status")
def photo_status(user: dict = Depends(require_roles("admin", "operator", "reviewer"))) -> dict:
    """Chinese-CLIP 与照片索引状态。"""

    return get_photo_index().status()


@router.post("/photos")
def upload_photo(
    file: UploadFile = File(...),
    station_id: str | None = Form(None),
    station_name: str | None = Form(None),
    caption: str | None = Form(None),
    user: dict = Depends(require_roles("admin", "operator", required_permissions=("submit_scheme",))),
) -> dict:
    """上传现场照片并计算图像特征（模型可用时）。"""

    payload = file.file.read()
    if not payload:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="上传照片为空")
    if station_id is not None and data_source.stations.get(station_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="站点不存在")
    if station_id is not None and not user_has_station_access(user, station_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前账号无权上传该站点照片")
    if station_id is None and "*" not in (user.get("station_ids") or ["*"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="站点账号上传照片时必须指定授权站点")
    try:
        record = get_photo_index().register(
            filename=file.filename or "photo.jpg",
            payload=payload,
            station_id=station_id,
            station_name=station_name,
            caption=caption,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return {
        "photo_id": record.photo_id,
        "filename": record.filename,
        "station_id": record.station_id,
        "embedding_ready": record.embedding_ready,
        "caption": record.caption,
    }


@router.get("/photos")
def list_photos(user: dict = Depends(require_roles("admin", "operator", "reviewer"))) -> list[dict]:
    """列出已注册照片（不含本地绝对路径）。"""

    records = [item for item in get_photo_index().list_photos() if _photo_visible(item.station_id, user)]
    return [
        {
            "photo_id": item.photo_id,
            "filename": item.filename,
            "station_id": item.station_id,
            "station_name": item.station_name,
            "caption": item.caption,
            "uploaded_at": item.uploaded_at,
            "embedding_ready": item.embedding_ready,
        }
        for item in records
    ]


@router.get("/photos/search")
def search_photos(
    q: str,
    k: int = 3,
    user: dict = Depends(require_roles("admin", "operator", "reviewer")),
) -> dict:
    """用中文描述检索照片，例如「二泵站压力表异常」。"""

    if not q.strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="请输入检索描述")
    try:
        results = get_photo_index().search(q.strip(), k=max(1, min(k, 10)))
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    return {"query": q.strip(), "results": [item for item in results if _photo_visible(item.get("station_id"), user)]}
