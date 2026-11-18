from copy import deepcopy

from fastapi.testclient import TestClient

from app.keitaro import KeitaroError
from app.main import app, get_client, get_db, stream_revision


class FakeDb:
    def __init__(self):
        self.record = None

    def add(self, record):
        self.record = record

    def commit(self):
        pass

    def rollback(self):
        pass


class FakeKeitaro:
    def __init__(self):
        self.calls = []
        self.fail_second_stream = False
        self.stream = {
            "id": 7, "schema": "landings", "state": "active",
            "offers": [{"offer_id": 1, "share": 60, "state": "active"},
                       {"offer_id": 2, "share": 40, "state": "active"}],
        }

    async def get(self, path, **kwargs):
        self.calls.append(("GET", path, kwargs))
        if path.startswith("domains/"):
            return {"id": 1, "state": "active"}
        if path.startswith("offers/"):
            return {"id": int(path.split("/")[-1]), "state": "active"}
        if path.startswith("traffic_sources/"):
            return {"id": 3, "state": "active"}
        if path == "groups":
            return [{"id": 4, "type": "campaigns"}]
        if path == "streams/7":
            return deepcopy(self.stream)
        raise AssertionError(path)

    async def post(self, path, data):
        self.calls.append(("POST", path, deepcopy(data)))
        if path == "campaigns":
            return {"id": 10}
        if path == "streams":
            count = sum(c[0:2] == ("POST", "streams") for c in self.calls)
            if count == 2 and self.fail_second_stream:
                raise KeitaroError("second stream failed")
            return {"id": 70 + count}
        raise AssertionError(path)

    async def put(self, path, data):
        self.calls.append(("PUT", path, deepcopy(data)))
        if path == "streams/7":
            self.stream["offers"] = deepcopy(data["offers"])
        return {}

    async def delete(self, path):
        self.calls.append(("DELETE", path, None))
        return {}


def client_with(fake):
    db = FakeDb()
    app.dependency_overrides[get_client] = lambda: fake
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app), db


def teardown_function():
    app.dependency_overrides.clear()


def payload():
    return {
        "name": "test_bayashev_campaign1", "geo": "us", "offer_id": 1,
        "domain_id": 1, "group_id": 4, "traffic_source_id": 3,
    }


def test_creates_ordered_country_and_default_offer_flows():
    fake = FakeKeitaro()
    client, db = client_with(fake)
    response = client.post("/api/campaigns", json=payload())
    assert response.status_code == 201, response.json()
    assert response.json()["id"] == 10
    created = [call[2] for call in fake.calls if call[:2] == ("POST", "streams")]
    assert created[0]["type"] == "forced"
    assert created[0]["schema"] == "redirect"
    assert created[0]["action_payload"] == "https://www.google.com"
    assert created[0]["filters"] == [{"name": "country", "mode": "accept", "payload": ["US"]}]
    assert created[1]["type"] == "default"
    assert created[1]["offers"] == [{"offer_id": 1, "share": 100, "state": "active"}]
    assert fake.calls.index(("PUT", "campaigns/10", {"state": "active"})) > fake.calls.index(("POST", "streams", created[1]))
    assert db.record.google_stream_id == 71


def test_failed_second_stream_archives_incomplete_campaign():
    fake = FakeKeitaro()
    fake.fail_second_stream = True
    client, db = client_with(fake)
    response = client.post("/api/campaigns", json=payload())
    assert response.status_code == 502
    assert ("DELETE", "campaigns/10", None) in fake.calls
    assert db.record is None


def test_add_offer_preserves_existing_weights_and_remove_is_scoped():
    fake = FakeKeitaro()
    client, _ = client_with(fake)
    added = client.post("/api/streams/7/offers", json={"offer_id": 3, "expected_revision": stream_revision(fake.stream)})
    assert added.status_code == 200, added.json()
    assert fake.stream["offers"] == [
        {"offer_id": 1, "share": 60, "state": "active"},
        {"offer_id": 2, "share": 40, "state": "active"},
        {"offer_id": 3, "share": 100, "state": "active"},
    ]
    removed = client.delete("/api/streams/7/offers/3", params={"expected_revision": stream_revision(fake.stream)})
    assert removed.status_code == 200, removed.json()
    assert [x["offer_id"] for x in fake.stream["offers"]] == [1, 2]


def test_stale_edit_is_rejected_without_writing():
    fake = FakeKeitaro()
    client, _ = client_with(fake)
    response = client.post("/api/streams/7/offers", json={"offer_id": 3, "expected_revision": "old"})
    assert response.status_code == 409
    assert not any(call[0] == "PUT" for call in fake.calls)


def test_last_active_offer_can_be_removed_and_readded():
    fake = FakeKeitaro()
    fake.stream["offers"] = [{"offer_id": 1, "share": 100, "state": "active"}]
    client, _ = client_with(fake)
    response = client.delete("/api/streams/7/offers/1", params={"expected_revision": stream_revision(fake.stream)})
    assert response.status_code == 200
    assert fake.stream["offers"] == []
    readded = client.post("/api/streams/7/offers", json={"offer_id": 1, "expected_revision": stream_revision(fake.stream)})
    assert readded.status_code == 200
    assert fake.stream["offers"] == [{"offer_id": 1, "share": 100, "state": "active"}]
