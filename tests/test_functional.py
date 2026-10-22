import os
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path

import pytest


@pytest.mark.parametrize("client_name", ["api", "fleet"])
def test_vehicle_creation_improper_input_validation_demo(services, client_name):
    client = getattr(services, client_name)
    headers = services.headers("carol")
    body = {"name": "   ", "daily_rate_cents": 35000}
    response = client.post("/vehicles", headers=headers, json=body)
    assert response.status_code == 201, response.text
    created = response.json()
    assert created == {"id": created["id"], **body}
    listed = client.get("/vehicles", headers=headers)
    assert listed.status_code == 200
    assert created in listed.json()
    for changes in (
        {"name": ""},
        {"name": "x" * 101},
        {"daily_rate_cents": 0},
        {"daily_rate_cents": "35000"},
        {"daily_rate_cents": 2**31},
        {"unexpected": True},
    ):
        invalid = client.post(
            "/vehicles", headers=headers, json={**body, **changes}
        )
        assert invalid.status_code == 422, invalid.text
    assert (
        client.post("/vehicles", headers=services.headers("bob"), json=body).status_code
        == 403
    )
    assert client.post("/vehicles", json=body).status_code == 401


@pytest.mark.parametrize("client_name", ["api", "fleet"])
def test_vehicle_update_endpoint_removed(services, vehicle, client_name):
    client = getattr(services, client_name)
    response = client.put(
        f"/vehicles/{vehicle['id']}",
        headers=services.headers("carol"),
        json={"name": "Updated vehicle", "daily_rate_cents": 20000},
    )
    assert response.status_code == 405
    schema = client.get("/openapi.json")
    assert schema.status_code == 200
    assert "put" not in schema.json()["paths"]["/vehicles/{vehicle_id}"]


@pytest.mark.parametrize("client_name", ["api", "fleet"])
def test_vehicle_search(services, vehicle, client_name):
    client = getattr(services, client_name)
    headers = services.headers()
    response = client.get(
        "/vehicles/search", params={"name": "Test veh"}, headers=headers
    )
    assert response.status_code == 200, response.text
    rows = response.json()
    assert vehicle in rows
    assert all("Test veh" in row["name"] for row in rows)
    assert [row["id"] for row in rows] == sorted(row["id"] for row in rows)
    missing = client.get(
        "/vehicles/search",
        params={"name": "no-such-vehicle-for-search"},
        headers=headers,
    )
    assert missing.status_code == 200
    assert missing.json() == []
    assert client.get("/vehicles/search", headers=headers).status_code == 422


@pytest.mark.parametrize("client_name", ["api", "fleet"])
def test_vehicle_search_reserved_characters(services, client_name):
    name = "Road & Trail + City?#"
    created = services.api.post(
        "/vehicles",
        headers=services.headers("carol"),
        json={"name": name, "daily_rate_cents": 10000},
    )
    assert created.status_code == 201, created.text
    response = getattr(services, client_name).get(
        "/vehicles/search", params={"name": name}, headers=services.headers()
    )
    assert response.status_code == 200, response.text
    rows = response.json()
    assert created.json() in rows
    assert all(row["name"] == name for row in rows)


@pytest.mark.parametrize("client_name", ["api", "fleet"])
def test_vehicle_search_sql_injection_demo(services, client_name):
    client = getattr(services, client_name)
    headers = services.headers()
    baseline = client.get("/vehicles", headers=headers)
    assert baseline.status_code == 200
    assert baseline.json()
    response = client.get(
        "/vehicles/search",
        params={"name": "no-such-vehicle-for-search%' OR 1=1 --"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert sorted(response.json(), key=lambda row: row["id"]) == baseline.json()


def test_seed_is_repeatable(tmp_path):
    environment = {**os.environ, "FLEET_DB_PATH": str(tmp_path / "fleet.sqlite3")}
    command = [sys.executable, "-m", "app.fleet_resource_service.db"]
    root = Path(__file__).resolve().parents[1]
    subprocess.run(command, cwd=root, env=environment, check=True, capture_output=True)
    with closing(sqlite3.connect(environment["FLEET_DB_PATH"])) as db, db:
        assert db.execute("SELECT COUNT(*) FROM vehicles").fetchone()[0] == 5
        db.execute("UPDATE vehicles SET daily_rate_cents = 12345 WHERE id = 1")
    subprocess.run(command, cwd=root, env=environment, check=True, capture_output=True)
    with closing(sqlite3.connect(environment["FLEET_DB_PATH"])) as db:
        assert db.execute("SELECT COUNT(*) FROM vehicles").fetchone()[0] == 5
        assert (
            db.execute("SELECT daily_rate_cents FROM vehicles WHERE id = 1").fetchone()[
                0
            ]
            == 12345
        )


def test_renter_booking_and_agreement_flow(services, booking):
    path = f"/bookings/{booking['id']}"
    headers = services.headers()
    viewed = services.api.get(path, headers=headers)
    assert viewed.status_code == 200
    assert viewed.json() == booking
    generated = services.api.post(path + "/agreement", headers=headers)
    assert generated.status_code == 200, generated.text
    expected = (
        f"Rental invoice\nbooking_id: {booking['id']}\nrenter_id: alice\n"
        f"vehicle_id: {booking['vehicle_id']}\nstart_date: 2030-06-01\n"
        "end_date: 2030-06-03\ntotal_cents: 70000\n"
    )
    assert generated.json() == {"booking_id": booking["id"], "content": expected}
    saved = services.api.get(path + "/agreement", headers=headers)
    assert saved.status_code == 200
    assert saved.json() == generated.json()
    cancelled = services.api.post(path + "/cancel", headers=headers)
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert services.api.post(path + "/agreement", headers=headers).status_code == 409
    assert services.api.get(path + "/agreement", headers=headers).json() == saved.json()


def test_staff_fleet_and_booking_controls(services, vehicle, booking):
    headers = services.headers("carol")
    path = f"/bookings/{booking['id']}"
    all_bookings = services.api.get("/bookings", headers=headers)
    assert all_bookings.status_code == 200
    assert booking["id"] in {row["id"] for row in all_bookings.json()}
    assert services.api.get(path, headers=headers).status_code == 200
    generated = services.api.post(path + "/agreement", headers=headers)
    assert generated.status_code == 200
    assert "renter_id: alice\n" in generated.json()["content"]
    cancelled = services.api.post(path + "/cancel", headers=headers)
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert (
        services.api.delete(f"/vehicles/{vehicle['id']}", headers=headers).status_code
        == 409
    )
    created = services.api.post(
        "/vehicles",
        headers=headers,
        json={"name": "Unused vehicle", "daily_rate_cents": 10000},
    )
    assert created.status_code == 201
    vehicle_path = f"/vehicles/{created.json()['id']}"
    deleted = services.api.delete(vehicle_path, headers=headers)
    assert deleted.status_code == 204
    assert deleted.content == b""


def test_booking_price_and_availability(services, vehicle, booking):
    body = {
        "vehicle_id": vehicle["id"],
        "start_date": "2030-06-02",
        "end_date": "2030-06-04",
    }
    assert (
        services.api.post(
            "/bookings", headers=services.headers("bob"), json=body
        ).status_code
        == 409
    )
    adjacent = services.api.post(
        "/bookings",
        headers=services.headers("bob"),
        json={**body, "start_date": "2030-06-03"},
    )
    assert adjacent.status_code == 201
    path = f"/bookings/{booking['id']}"
    assert (
        services.api.get(path, headers=services.headers()).json()["total_cents"]
        == 70000
    )
    assert (
        services.api.post(path + "/cancel", headers=services.headers()).status_code
        == 200
    )
    replacement = services.api.post(
        "/bookings",
        headers=services.headers("bob"),
        json={**body, "start_date": "2030-06-01", "end_date": "2030-06-03"},
    )
    assert replacement.status_code == 201
    assert replacement.json()["total_cents"] == 70000
    invalid = services.api.post(
        "/bookings",
        headers=services.headers(),
        json={**body, "end_date": body["start_date"]},
    )
    assert invalid.status_code == 422


def test_concurrent_overlap_rejection(services, vehicle):
    def create(_):
        return services.api.post(
            "/bookings",
            headers=services.headers(),
            json={
                "vehicle_id": vehicle["id"],
                "start_date": "2030-06-01",
                "end_date": "2030-06-03",
            },
        )

    with ThreadPoolExecutor(max_workers=12) as pool:
        responses = list(pool.map(create, range(12)))
    assert sorted(response.status_code for response in responses) == [201] + [409] * 11
