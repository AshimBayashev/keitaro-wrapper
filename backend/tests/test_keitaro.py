import httpx
import pytest

from app.keitaro import KeitaroClient, KeitaroError


@pytest.mark.asyncio
async def test_duplicate_campaign_name_is_actionable_conflict():
    def reply(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/campaigns")
        return httpx.Response(422, json={"name": ["Name has already used"]})

    client = KeitaroClient(transport=httpx.MockTransport(reply))
    with pytest.raises(KeitaroError) as error:
        await client.post("campaigns", {"name": "test_bayashev_campaign1"})

    assert error.value.status_code == 409
    assert "Укажите другое окончание" in error.value.message


@pytest.mark.asyncio
async def test_field_validation_is_not_hidden_by_generic_reason_phrase():
    client = KeitaroClient(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(422, json={"filters": ["Country is invalid"]})
        )
    )
    with pytest.raises(KeitaroError) as error:
        await client.post("streams", {"filters": []})

    assert error.value.status_code == 422
    assert error.value.message == "Keitaro: filters: Country is invalid"
