import os
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path


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
    updated = services.api.put(
        vehicle_path,
        headers=headers,
        json={"name": "Updated vehicle", "daily_rate_cents": 20000},
    )
    assert updated.status_code == 200
    assert updated.json()["daily_rate_cents"] == 20000
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
    updated = services.api.put(
        f"/vehicles/{vehicle['id']}",
        headers=services.headers("carol"),
        json={"name": "Changed rate", "daily_rate_cents": 45000},
    )
    assert updated.status_code == 200
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
    assert replacement.json()["total_cents"] == 90000
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
