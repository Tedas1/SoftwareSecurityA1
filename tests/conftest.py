import os
import secrets
import socket
import subprocess
import sys
import time
from contextlib import ExitStack
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import jwt
import pytest

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Services:
    api: httpx.Client
    fleet: httpx.Client
    processor: httpx.Client
    key: str = field(repr=False)
    tokens: dict[str, str] = field(repr=False)

    def headers(self, username: str = "alice") -> dict[str, str]:
        return {"Authorization": f"Bearer {self.tokens[username]}"}

    def sign(self, **changes: object) -> str:
        now = int(time.time())
        claims: dict[str, object] = {
            "sub": "alice",
            "role": "renter",
            "iat": now,
            "exp": now + 900,
        }
        claims.update(changes)
        return jwt.encode(claims, self.key, algorithm="HS256")


def stop_service(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        powershell = (
            Path(os.environ["SystemRoot"])
            / "System32"
            / "WindowsPowerShell"
            / "v1.0"
            / "powershell.exe"
        )
        subprocess.run(
            [
                str(powershell),
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                f"Stop-Process -Id {process.pid} -ErrorAction Stop",
            ],
            check=True,
            capture_output=True,
        )
    else:
        process.terminate()
    process.wait(timeout=10)


@pytest.fixture(scope="session")
def services(tmp_path_factory):
    directory = tmp_path_factory.mktemp("services")
    key = secrets.token_urlsafe(32)
    passwords = {
        username: secrets.token_urlsafe(20) for username in ("alice", "bob", "carol")
    }
    with ExitStack() as reservations:
        listeners = [reservations.enter_context(socket.socket()) for _ in range(3)]
        for listener in listeners:
            listener.bind(("127.0.0.1", 0))
        fleet_port, processor_port, api_port = (
            listener.getsockname()[1] for listener in listeners
        )
    fleet_url = f"http://127.0.0.1:{fleet_port}"
    processor_url = f"http://127.0.0.1:{processor_port}"
    base_environment = os.environ.copy()
    for name in (
        "FLEET_DB_PATH",
        "FLEET_SERVICE_URL",
        "AGREEMENT_SERVICE_URL",
        "ALICE_PASSWORD",
        "BOB_PASSWORD",
        "CAROL_PASSWORD",
    ):
        base_environment.pop(name, None)
    base_environment["JWT_SECRET"] = key
    fleet_environment = {
        **base_environment,
        "FLEET_DB_PATH": str(directory / "fleet.sqlite3"),
    }
    subprocess.run(
        [sys.executable, "-m", "app.fleet_resource_service.db"],
        cwd=ROOT,
        env=fleet_environment,
        check=True,
        capture_output=True,
    )
    targets = [
        ("fleet_resource_service", fleet_port, fleet_environment),
        (
            "agreement_processor",
            processor_port,
            {**base_environment, "FLEET_SERVICE_URL": fleet_url},
        ),
        (
            "rental_api",
            api_port,
            {
                **base_environment,
                "FLEET_SERVICE_URL": fleet_url,
                "AGREEMENT_SERVICE_URL": processor_url,
                **{
                    f"{username.upper()}_PASSWORD": password
                    for username, password in passwords.items()
                },
            },
        ),
    ]
    with ExitStack() as stack:
        clients = {}
        for module, port, environment in targets:
            log_path = directory / f"{module}.log"
            log = stack.enter_context(log_path.open("w", encoding="utf-8"))
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    f"app.{module}.main:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                    "--log-level",
                    "warning",
                ],
                cwd=ROOT,
                env=environment,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            stack.callback(stop_service, process)
            client = stack.enter_context(
                httpx.Client(
                    base_url=f"http://127.0.0.1:{port}", timeout=10, trust_env=False
                )
            )
            clients[module] = client
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    pytest.fail(log_path.read_text(encoding="utf-8"))
                try:
                    response = client.get("/openapi.json")
                except httpx.ConnectError:
                    time.sleep(0.1)
                    continue
                response.raise_for_status()
                break
            else:
                pytest.fail(f"{module} did not become ready")
        api = clients["rental_api"]
        tokens = {}
        for username, password in passwords.items():
            response = api.post(
                "/login", json={"username": username, "password": password}
            )
            assert response.status_code == 200, response.text
            tokens[username] = response.json()["access_token"]
        yield Services(
            api,
            clients["fleet_resource_service"],
            clients["agreement_processor"],
            key,
            tokens,
        )


@pytest.fixture
def vehicle(services):
    response = services.api.post(
        "/vehicles",
        headers=services.headers("carol"),
        json={"name": "Test vehicle", "daily_rate_cents": 35000},
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def booking(services, vehicle):
    response = services.api.post(
        "/bookings",
        headers=services.headers(),
        json={
            "vehicle_id": vehicle["id"],
            "start_date": "2030-06-01",
            "end_date": "2030-06-03",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()
