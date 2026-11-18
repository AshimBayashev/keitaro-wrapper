import asyncio
import hashlib
import json
import logging
import secrets
from collections import defaultdict
from collections.abc import Generator

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from .config import settings
from .countries import COUNTRIES, COUNTRY_CODES
from .db import SessionLocal
from .keitaro import KeitaroClient, KeitaroError
from .models import CampaignRecord
from .schemas import AddOffer, CreateCampaign


logger = logging.getLogger(__name__)
app = FastAPI(title="Keitaro Campaign Studio", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type"],
)

stream_locks: defaultdict[int, asyncio.Lock] = defaultdict(asyncio.Lock)


def get_client() -> KeitaroClient:
    return KeitaroClient()


def get_db() -> Generator[Session, None, None]:
    with SessionLocal() as db:
        yield db


@app.exception_handler(KeitaroError)
async def keitaro_error_handler(_request, exc: KeitaroError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


@app.get("/api/health")
async def health():
    return {"status": "ok", "configured": bool(settings.api_key)}


@app.get("/api/config")
async def config():
    return {"name_prefix": settings.name_prefix}


@app.get("/api/meta")
async def meta(client: KeitaroClient = Depends(get_client)):
    domains, groups, sources, offers = await asyncio.gather(
        client.get("domains"),
        client.get("groups", params={"type": "campaigns"}),
        client.get("traffic_sources"),
        client.get("offers"),
    )
    return {
        "countries": COUNTRIES,
        "domains": [{"id": x["id"], "name": x["name"]} for x in domains if x.get("state") == "active"],
        "groups": [{"id": x["id"], "name": x["name"]} for x in groups if x.get("type") == "campaigns"],
        "sources": [{"id": x["id"], "name": x["name"]} for x in sources if x.get("state") == "active"],
        "offers": [{"id": x["id"], "name": x["name"]} for x in offers if x.get("state") == "active"],
    }


@app.get("/api/campaigns")
async def list_campaigns(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=40, ge=1, le=100),
    client: KeitaroClient = Depends(get_client),
):
    rows = await client.get("campaigns", params={"offset": offset, "limit": limit})
    return {
        "items": [
            {
                "id": x["id"],
                "name": x["name"],
                "alias": x.get("alias"),
                "state": x.get("state"),
                "domain_id": x.get("domain_id"),
                "group_id": x.get("group_id"),
                "traffic_source_id": x.get("traffic_source_id"),
            }
            for x in rows if x.get("state") != "deleted"
        ],
        "offset": offset,
        "limit": limit,
        "has_more": len(rows) == limit,
        "next_offset": offset + len(rows),
    }


def present_stream(stream: dict, offer_names: dict[int, str]) -> dict:
    offers = [x for x in stream.get("offers", []) if x.get("state") != "deleted"]
    total = sum(max(0, int(x.get("share") or 0)) for x in offers if x.get("state") == "active")
    return {
        "id": stream["id"],
        "name": stream["name"],
        "type": stream.get("type"),
        "schema": stream.get("schema"),
        "state": stream.get("state"),
        "position": stream.get("position"),
        "revision": stream_revision(stream),
        "action_type": stream.get("action_type"),
        "action_payload": stream.get("action_payload"),
        "filters": stream.get("filters", []),
        "offers": [
            {
                "id": x["offer_id"],
                "name": offer_names.get(x["offer_id"], f"Оффер #{x['offer_id']}"),
                "share": x.get("share", 0),
                "state": x.get("state"),
                "percentage": round(100 * int(x.get("share") or 0) / total, 2)
                if total and x.get("state") == "active" else 0,
            }
            for x in offers
        ],
    }


@app.get("/api/campaigns/{campaign_id}")
async def campaign_detail(campaign_id: int, client: KeitaroClient = Depends(get_client)):
    campaign, streams, offers = await asyncio.gather(
        client.get(f"campaigns/{campaign_id}"),
        client.get(f"campaigns/{campaign_id}/streams"),
        client.get("offers"),
    )
    names = {x["id"]: x["name"] for x in offers}
    active_streams = [x for x in streams if x.get("state") != "deleted"]
    return {
        "campaign": {
            "id": campaign["id"], "name": campaign["name"], "alias": campaign.get("alias"),
            "state": campaign.get("state"), "domain_id": campaign.get("domain_id"),
            "group_id": campaign.get("group_id"), "traffic_source_id": campaign.get("traffic_source_id"),
        },
        "streams": [present_stream(x, names) for x in sorted(active_streams, key=lambda s: s.get("position") or 0)],
    }


async def validate_create(request: CreateCampaign, client: KeitaroClient):
    name = request.name.strip()
    if not name.startswith(settings.name_prefix) or len(name) <= len(settings.name_prefix):
        raise HTTPException(422, f"Название должно начинаться с {settings.name_prefix} и содержать окончание")
    if request.geo not in COUNTRY_CODES:
        raise HTTPException(422, "Выберите страну из списка. GEO-код не найден в ISO 3166-1.")
    domain, offer, source, groups = await asyncio.gather(
        client.get(f"domains/{request.domain_id}"),
        client.get(f"offers/{request.offer_id}"),
        client.get(f"traffic_sources/{request.traffic_source_id}"),
        client.get("groups", params={"type": "campaigns"}),
    )
    if domain.get("state") != "active" or offer.get("state") != "active" or source.get("state") != "active":
        raise HTTPException(422, "Домен, источник и оффер должны быть активны")
    if not any(g.get("id") == request.group_id for g in groups):
        raise HTTPException(422, "Группа кампаний не найдена")


@app.post("/api/campaigns", status_code=201)
async def create_campaign(
    request: CreateCampaign,
    client: KeitaroClient = Depends(get_client),
    db: Session = Depends(get_db),
):
    await validate_create(request, client)
    campaign = await client.post("campaigns", {
        "name": request.name.strip(),
        "alias": f"t-{secrets.token_hex(5)}",
        "type": "position",
        "state": "disabled",
        "domain_id": request.domain_id,
        "group_id": str(request.group_id),
        "traffic_source_id": request.traffic_source_id,
    })
    campaign_id = campaign["id"]
    try:
        google = await client.post("streams", {
            "campaign_id": campaign_id,
            "name": f"{request.geo} → Google",
            "schema": "redirect",
            "type": "forced",
            "position": 1,
            "action_type": "http",
            "action_payload": "https://www.google.com",
            "filters": [{"name": "country", "mode": "accept", "payload": [request.geo]}],
        })
        offer_stream = await client.post("streams", {
            "campaign_id": campaign_id,
            "name": "Офферы",
            "schema": "landings",
            "type": "default",
            "position": 2,
            "action_type": "http",
            "action_payload": "",
            "offers": [{"offer_id": request.offer_id, "share": 100, "state": "active"}],
        })
        await client.put(f"campaigns/{campaign_id}", {"state": "active"})
    except Exception:
        try:
            await client.delete(f"campaigns/{campaign_id}")
        except KeitaroError:
            logger.exception("Could not archive incomplete campaign %s", campaign_id)
        raise

    warning = None
    try:
        db.add(CampaignRecord(
            keitaro_campaign_id=campaign_id, name=request.name.strip(), geo=request.geo,
            initial_offer_id=request.offer_id, domain_id=request.domain_id, group_id=request.group_id,
            traffic_source_id=request.traffic_source_id, google_stream_id=google["id"],
            offer_stream_id=offer_stream["id"],
        ))
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Campaign %s created in Keitaro, but local audit write failed", campaign_id)
        warning = "Кампания создана в Keitaro, но не записана в локальную историю. Проверьте миграции."
    return {"id": campaign_id, "google_stream_id": google["id"], "offer_stream_id": offer_stream["id"], "warning": warning}


def stream_revision(stream: dict) -> str:
    relevant = {
        "schema": stream.get("schema"),
        "state": stream.get("state"),
        "offers": sorted(
            ({"offer_id": x.get("offer_id"), "share": x.get("share"), "state": x.get("state")}
             for x in stream.get("offers", [])),
            key=lambda x: x["offer_id"],
        ),
    }
    return hashlib.sha256(json.dumps(relevant, sort_keys=True).encode()).hexdigest()[:16]


def check_version(stream: dict, expected: str | None):
    if expected and stream_revision(stream) != expected:
        raise HTTPException(409, "Поток изменился в Keitaro. Обновите данные и повторите действие.")


def writable_offers(stream: dict) -> list[dict]:
    return [
        {"offer_id": x["offer_id"], "share": x["share"], "state": x["state"]}
        for x in stream.get("offers", []) if x.get("state") in ("active", "disabled")
    ]


async def get_offer_stream(stream_id: int, client: KeitaroClient) -> dict:
    stream = await client.get(f"streams/{stream_id}")
    if stream.get("schema") != "landings" or stream.get("state") != "active":
        raise HTTPException(422, "Добавление офферов доступно только в активном потоке с офферами")
    return stream


@app.post("/api/streams/{stream_id}/offers")
async def add_offer(stream_id: int, request: AddOffer, client: KeitaroClient = Depends(get_client)):
    async with stream_locks[stream_id]:
        stream = await get_offer_stream(stream_id, client)
        check_version(stream, request.expected_revision)
        offers = writable_offers(stream)
        if any(x["offer_id"] == request.offer_id for x in offers):
            raise HTTPException(409, "Этот оффер уже добавлен в поток")
        offer = await client.get(f"offers/{request.offer_id}")
        if offer.get("state") != "active":
            raise HTTPException(422, "Оффер должен быть активен")
        offers.append({"offer_id": request.offer_id, "share": 100, "state": "active"})
        await client.put(f"streams/{stream_id}", {"offers": offers})
        actual = writable_offers(await client.get(f"streams/{stream_id}"))
        if not any(x["offer_id"] == request.offer_id for x in actual):
            raise KeitaroError("Keitaro не сохранил новый оффер")
        return {"stream_id": stream_id, "offer_count": len(actual)}


@app.delete("/api/streams/{stream_id}/offers/{offer_id}")
async def remove_offer(
    stream_id: int,
    offer_id: int,
    expected_revision: str | None = None,
    client: KeitaroClient = Depends(get_client),
):
    async with stream_locks[stream_id]:
        stream = await get_offer_stream(stream_id, client)
        check_version(stream, expected_revision)
        offers = writable_offers(stream)
        if not any(x["offer_id"] == offer_id for x in offers):
            raise HTTPException(404, "Оффер не найден в этом потоке")
        remaining = [x for x in offers if x["offer_id"] != offer_id]
        await client.put(f"streams/{stream_id}", {"offers": remaining})
        actual = writable_offers(await client.get(f"streams/{stream_id}"))
        if any(x["offer_id"] == offer_id for x in actual):
            raise KeitaroError("Keitaro не удалил оффер из потока")
        return {"stream_id": stream_id, "offer_count": len(actual)}
