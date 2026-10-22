import secrets
import time

import jwt


def test_login_roles_and_rejection(services):
    for username, role in (("alice", "renter"), ("bob", "renter"), ("carol", "staff")):
        claims = jwt.decode(
            services.tokens[username], services.key, algorithms=["HS256"]
        )
        assert claims["sub"] == username
        assert claims["role"] == role
        assert claims["exp"] - claims["iat"] == 900
    password = secrets.token_urlsafe(20)
    wrong = services.api.post(
        "/login", json={"username": "alice", "password": password}
    )
    unknown = services.api.post(
        "/login", json={"username": "unknown", "password": password}
    )
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()
    assert (
        services.api.post(
            "/login", json={"username": "alice", "password": password, "role": "staff"}
        ).status_code
        == 422
    )


def test_renter_boundaries(services, vehicle, booking):
    path = f"/bookings/{booking['id']}"
    for method, suffix in (
        ("GET", ""),
        ("POST", "/cancel"),
        ("POST", "/agreement"),
        ("GET", "/agreement"),
    ):
        assert (
            services.api.request(
                method, path + suffix, headers=services.headers("bob")
            ).status_code
            == 403
        )
    for username in ("alice", "bob"):
        own = services.api.get("/bookings", headers=services.headers(username))
        assert own.status_code == 200
        assert all(row["renter_id"] == username for row in own.json())
    for method, target in (
        ("POST", "/vehicles"),
        ("PUT", f"/vehicles/{vehicle['id']}"),
        ("DELETE", f"/vehicles/{vehicle['id']}"),
    ):
        assert (
            services.api.request(
                method,
                target,
                headers=services.headers(),
                json={"name": "Forbidden", "daily_rate_cents": 1},
            ).status_code
            == 403
        )
    assert (
        services.api.post(
            "/bookings",
            headers=services.headers("carol"),
            json={
                "vehicle_id": vehicle["id"],
                "start_date": "2030-07-01",
                "end_date": "2030-07-03",
            },
        ).status_code
        == 403
    )


def test_least_privilege(services, booking):
    for username, role in (("alice", "renter"), ("carol", "staff")):
        scoped = services.sign(
            sub=username, role=role, scope="agreement", booking_id=booking["id"]
        )
        headers = {"Authorization": f"Bearer {scoped}"}
        path = f"/bookings/{booking['id']}"
        assert services.fleet.get(path, headers=headers).status_code == 200
        assert (
            services.processor.post(
                f"/agreements/{booking['id']}", headers=headers
            ).status_code
            == 200
        )
        assert services.fleet.get("/bookings", headers=headers).status_code == 403
        assert services.fleet.get("/vehicles", headers=headers).status_code == 403
        assert services.fleet.post(path + "/cancel", headers=headers).status_code == 403
        assert (
            services.processor.post(
                f"/agreements/{booking['id'] + 1000}", headers=headers
            ).status_code
            == 403
        )
    assert (
        services.processor.post(
            f"/agreements/{booking['id']}", headers=services.headers()
        ).status_code
        == 403
    )


def test_complete_mediation(services, vehicle, booking):
    path = f"/bookings/{booking['id']}"
    spoofed_headers = {
        **services.headers("bob"),
        "X-User-Id": "alice",
        "X-Role": "staff",
    }
    assert services.fleet.get(path, headers=spoofed_headers).status_code == 403
    wrong_owner = services.sign(sub="bob", scope="agreement", booking_id=booking["id"])
    assert (
        services.fleet.get(
            path, headers={"Authorization": f"Bearer {wrong_owner}"}
        ).status_code
        == 403
    )
    assert (
        services.processor.post(
            f"/agreements/{booking['id']}",
            headers={"Authorization": f"Bearer {wrong_owner}"},
        ).status_code
        == 403
    )
    assert (
        services.fleet.post(
            "/bookings",
            headers=services.headers("bob"),
            json={
                "vehicle_id": vehicle["id"],
                "user_id": "alice",
                "start_date": "2030-07-01",
                "end_date": "2030-07-03",
            },
        ).status_code
        == 422
    )


def test_fail_safe_defaults(services, vehicle, booking):
    expired = services.sign(iat=int(time.time()) - 901, exp=int(time.time()) - 1)
    for client, method, path in (
        (services.api, "GET", "/bookings"),
        (services.fleet, "GET", "/bookings"),
        (services.processor, "POST", f"/agreements/{booking['id']}"),
    ):
        for credential in (None, "invalid", expired):
            headers = {"Authorization": f"Bearer {credential}"} if credential else {}
            response = client.request(method, path, headers=headers)
            assert response.status_code == 401
            assert response.headers["www-authenticate"] == "Bearer"
    assert booking["status"] == "pending"
    assert (
        services.api.get(
            f"/bookings/{booking['id']}", headers=services.headers()
        ).json()["status"]
        == "pending"
    )
    assert (
        services.api.post(
            "/bookings",
            headers=services.headers(),
            json={
                "vehicle_id": vehicle["id"],
                "status": "active",
                "start_date": "2030-07-01",
                "end_date": "2030-07-03",
            },
        ).status_code
        == 422
    )
