"""jiekou.ai 代理端点共用工具。

四个 jiekou provider (seedream_v45 / flux_kontext_max / midjourney_txt2img /
jiekou_openai) 共享 base_url 和 sk_ key。Gemini 走自己的 Google key。

响应形状的探测策略：
- 同步端点返回结构未在官方 snippet 里给出。常见形状有：
  {"data": [{"url": "..."}]} / {"data": [{"b64_json": "..."}]} / {"image_url": "..."}
- 本模块提供 `extract_image_payload` 宽松匹配上述几种，取回
  (image_url_or_none, base64_bytes_or_none)；调用方负责下载/解码。
- 异步端点 POST 返回 {"id" / "task_id"} + 后续 GET 轮询直到 status done。
  轮询 URL 未在 snippet 里写死，本模块提供几个候选路径，优先级见 `ASYNC_STATUS_URL_CANDIDATES`。
"""
from __future__ import annotations

import base64
import re
import time
from typing import Any

import httpx
import structlog

from ....config import settings

log = structlog.get_logger()


# Poll URLs to try when we have only a task id.
# The primary endpoint uses query param: GET /v3/async/task-result?task_id=xxx
ASYNC_POLL_PRIMARY = "/v3/async/task-result"

# Fallback path-based candidates (legacy, kept for compatibility)
ASYNC_STATUS_URL_CANDIDATES = [
    "/v3/async/result/{id}",
    "/v3/async/{id}",
    "/v3/task/{id}",
    "/v3/tasks/{id}",
]


class JiekouError(RuntimeError):
    pass


def jiekou_headers() -> dict[str, str]:
    """Common auth+content headers for jiekou.ai endpoints."""
    if not settings.jiekou_api_key:
        raise JiekouError("JIEKOU_API_KEY missing in settings/.env")
    return {
        "Authorization": f"Bearer {settings.jiekou_api_key}",
        "Content-Type": "application/json",
    }


def jiekou_url(path: str) -> str:
    base = settings.jiekou_base_url.rstrip("/")
    return f"{base}{path}"


def _find_first(data: Any, keys: list[str]) -> Any:
    """DFS search for the first key in `keys` in a nested dict/list."""
    if isinstance(data, dict):
        for k in keys:
            if k in data and data[k]:
                return data[k]
        for v in data.values():
            found = _find_first(v, keys)
            if found is not None:
                return found
    elif isinstance(data, list) and data:
        for item in data:
            found = _find_first(item, keys)
            if found is not None:
                return found
    return None


def extract_image_payload(data: dict) -> tuple[str | None, bytes | None]:
    """Return (url_or_none, bytes_or_none). Never raises; caller checks."""
    # URL-ish keys
    url = _find_first(data, [
        "image_url", "url", "output_url", "result_url", "download_url",
        "imageUrl", "outputUrl",
    ])
    if isinstance(url, str) and url.startswith(("http://", "https://")):
        return url, None

    # base64-ish keys
    b64 = _find_first(data, [
        "b64_json", "image_base64", "base64", "image_data", "b64",
    ])
    if isinstance(b64, str) and b64:
        # Strip data: URI prefix if present
        if b64.startswith("data:"):
            b64 = b64.split(",", 1)[-1]
        try:
            return None, base64.b64decode(b64)
        except Exception:
            return None, None

    # Sometimes the URL is a bare string in an `image_urls` array
    urls = data.get("image_urls") or data.get("images") or data.get("output")
    if isinstance(urls, list) and urls:
        first = urls[0]
        if isinstance(first, str) and first.startswith(("http://", "https://")):
            return first, None
        if isinstance(first, dict):
            return extract_image_payload(first)

    return None, None


def download_bytes(url: str, timeout: float = 60.0) -> bytes:
    with httpx.Client(timeout=timeout) as client:
        r = client.get(url)
        r.raise_for_status()
        return r.content


def extract_task_id(data: dict) -> str:
    """Pull a task id from async-submit response."""
    for k in ("id", "task_id", "taskId", "job_id", "jobId"):
        v = data.get(k)
        if isinstance(v, str) and v:
            return v
    # Sometimes nested
    nested = _find_first(data, ["id", "task_id", "taskId"])
    if isinstance(nested, str) and nested:
        return nested
    raise JiekouError(f"could not find task id in submit response: {data}")


# Status-field values that mean success / failure
_DONE_STATES = {"succeeded", "success", "completed", "done", "finished"}
_FAIL_STATES = {"failed", "error", "canceled", "cancelled", "rejected"}


def poll_async_result(
    task_id: str,
    *,
    endpoint_hint: str | None = None,
) -> dict:
    """Poll for an async task and return the final payload.

    Primary: GET /v3/async/task-result?task_id=xxx
    Response shape:
      { "task": {"task_id": "...", "status": "TASK_STATUS_SUCCEED"}, "images": [...] }

    Raises JiekouError on failure or timeout.
    """
    interval = settings.async_poll_interval_s
    max_attempts = settings.async_poll_max_attempts
    headers = jiekou_headers()
    poll_url = jiekou_url(ASYNC_POLL_PRIMARY)

    with httpx.Client(timeout=30) as client:
        for attempt in range(max_attempts):
            try:
                r = client.get(poll_url, headers=headers, params={"task_id": task_id})
            except httpx.HTTPError as e:
                log.warning("jiekou.poll_error", task_id=task_id, attempt=attempt, error=str(e)[:150])
                time.sleep(interval)
                continue

            if r.status_code != 200:
                log.warning("jiekou.poll_http_error", task_id=task_id, status=r.status_code)
                time.sleep(interval)
                continue

            data = r.json() if r.content else {}
            task_obj = data.get("task", {})
            status = task_obj.get("status", "")

            if status == "TASK_STATUS_SUCCEED":
                return data
            if status in ("TASK_STATUS_FAILED", "TASK_STATUS_CANCELLED"):
                reason = task_obj.get("reason", "unknown")
                raise JiekouError(f"async task {task_id} failed: {reason}")

            log.debug("jiekou.poll_waiting", task_id=task_id, status=status, attempt=attempt)
            time.sleep(interval)

    raise JiekouError(
        f"async task {task_id} timed out after {max_attempts} polls "
        f"at {interval}s interval"
    )


def _lower_str(v: Any) -> str:
    return v.lower() if isinstance(v, str) else ""


# Aspect ratio → integer width/height (jiekou endpoints vary in what they accept;
# each provider converts as needed)
def aspect_to_wh(aspect: str, *, base_height: int = 1920) -> tuple[int, int]:
    """Return (w, h) for a TikTok-friendly size.

    Defaults to 1088x1920 for 9:16 (SDXL/FLUX divisible-by-16 convention).
    """
    m = re.match(r"^(\d+):(\d+)$", aspect.strip())
    if not m:
        return (1088, 1920)
    a, b = int(m.group(1)), int(m.group(2))
    if a <= 0 or b <= 0:
        return (1088, 1920)
    h = base_height
    w = round(h * a / b / 16) * 16
    h = round(h / 16) * 16
    return (max(w, 16), max(h, 16))
