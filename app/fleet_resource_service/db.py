import os
import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS vehicles (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL CHECK(length(name) BETWEEN 1 AND 100),
    daily_rate_cents INTEGER NOT NULL CHECK(daily_rate_cents > 0)
);
CREATE TABLE IF NOT EXISTS bookings (
    id INTEGER PRIMARY KEY,
    renter_id TEXT NOT NULL,
    vehicle_id INTEGER NOT NULL REFERENCES vehicles(id),
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL CHECK(end_date > start_date),
    total_cents INTEGER NOT NULL CHECK(total_cents > 0),
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'cancelled'))
);
CREATE TABLE IF NOT EXISTS invoices (
    booking_id INTEGER PRIMARY KEY REFERENCES bookings(id),
    content TEXT NOT NULL CHECK(length(content) BETWEEN 1 AND 100000)
);
"""


def database_path() -> Path:
    return Path(os.environ.get("FLEET_DB_PATH", "runtime/fleet.sqlite3"))


def connect() -> sqlite3.Connection:
    db = sqlite3.connect(database_path(), timeout=10, check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def initialize() -> None:
    database_path().parent.mkdir(parents=True, exist_ok=True)
    with closing(connect()) as db:
        db.executescript(SCHEMA)


def connection() -> Iterator[sqlite3.Connection]:
    with closing(connect()) as db:
        yield db


def seed_vehicles() -> None:
    initialize()
    vehicles = [
        (1, "Toyota Yaris", 35000),
        (2, "Volkswagen Golf", 45000),
        (3, "Skoda Octavia", 55000),
        (4, "Volvo V60", 75000),
        (5, "Ford Transit", 85000),
    ]
    with closing(connect()) as db, db:
        db.executemany(
            "INSERT INTO vehicles (id, name, daily_rate_cents) VALUES (?, ?, ?) "
            "ON CONFLICT(id) DO NOTHING",
            vehicles,
        )


if __name__ == "__main__":
    seed_vehicles()
    print("Fleet seed complete; existing vehicle IDs were left unchanged.")
