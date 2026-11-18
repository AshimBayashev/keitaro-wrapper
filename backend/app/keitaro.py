from typing import Any

import httpx

from .config import settings


class KeitaroError(Exception):
    def __init__(self, message: str, status_code: int = 502):
        self.message = message
        self.status_code = status_code


class KeitaroClient:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None):
        self.transport = transport

    async def request(self, method: str, path: str, **kwargs: Any) -> Any:
        if not settings.api_key:
            raise KeitaroError("Задайте KEITARO_API_KEY в backend/.env", 503)
        try:
            async with httpx.AsyncClient(
                base_url=f"{settings.base_url}/admin_api/v1/",
                headers={"Api-Key": settings.api_key},
                timeout=20,
                transport=self.transport,
            ) as client:
                response = await client.request(method, path.lstrip("/"), **kwargs)
        except httpx.RequestError as exc:
            raise KeitaroError("Не удалось связаться с Keitaro") from exc
        if response.is_error:
            try:
                body = response.json()
                message = body.get("error") or body.get("message") or response.reason_phrase
            except (ValueError, AttributeError):
                message = response.reason_phrase
            status = 404 if response.status_code == 404 else 502
            raise KeitaroError(f"Keitaro: {message}", status)
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise KeitaroError("Keitaro вернул ответ не в формате JSON") from exc

    async def get(self, path: str, **kwargs: Any) -> Any:
        return await self.request("GET", path, **kwargs)

    async def post(self, path: str, data: dict[str, Any]) -> Any:
        return await self.request("POST", path, json=data)

    async def put(self, path: str, data: dict[str, Any]) -> Any:
        return await self.request("PUT", path, json=data)

    async def delete(self, path: str) -> Any:
        return await self.request("DELETE", path)
