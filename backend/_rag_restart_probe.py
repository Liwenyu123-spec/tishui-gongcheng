"""检查重启后 Chroma 不再命中已消失的内存文档。"""

import json
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:8000"


def request(method: str, path: str, body: dict | None = None, token: str | None = None) -> dict:
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    token = request("POST", "/api/v1/auth/login", {"username": "admin", "password": "admin123"})["access_token"]
    imported = request(
        "POST",
        "/api/v1/knowledge/import",
        {
            "filename": "restart-probe.md",
            "title": "重启残留探针规程",
            "version": "1.0",
            "category": "规程",
            "content": "重启残留探针只用于确认旧分片会在服务启动时删除。",
            "station_ids": ["pump-02"],
        },
        token,
    )
    request("PATCH", f"/api/v1/knowledge/{imported['id']}/status", {"status": "valid"}, token)
    before = request("GET", "/api/v1/knowledge/search?q=" + urllib.parse.quote("重启残留探针"), token=token)
    hit_ids = [item["source_id"] for item in before["results"]]
    print("before", imported["id"], hit_ids)
    if imported["id"] not in hit_ids:
        raise SystemExit("批准后的探针文档没有被检索到")
    print("READY", imported["id"])


if __name__ == "__main__":
    main()
