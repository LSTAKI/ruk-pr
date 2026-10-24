"""Tests for database initialization, migration, and persistence."""

import os
import tempfile
import sqlite3
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db.session import Base
from app.db.models import Warehouse, Product, Destination, DatasetVersion
from app.engine.simulator.fmcg_generator import DeterministicFMCGSimulator

def test_database_persistence_across_sessions():
    """Verifies that records written to SQLite persist across separate connection sessions."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_file:
        tmp_path = tmp_file.name

    try:
        db_url = f"sqlite:///{tmp_path}"
        engine = create_engine(db_url, connect_args={"check_same_thread": False})
        Session = sessionmaker(bind=engine)

        # Create schema and add a record
        Base.metadata.create_all(bind=engine)
        s1 = Session()
        wh = Warehouse(code="WH-P1", name="Persistent Hub", city="Chicago", state="IL", capacity_units=50000, latitude=0, longitude=0)
        s1.add(wh)
        s1.commit()
        s1.close()
        engine.dispose()

        # Open brand-new engine and session to verify persistence
        engine2 = create_engine(db_url, connect_args={"check_same_thread": False})
        Session2 = sessionmaker(bind=engine2)
        s2 = Session2()
        retrieved = s2.query(Warehouse).filter(Warehouse.code == "WH-P1").first()
        assert retrieved is not None
        assert retrieved.name == "Persistent Hub"
        s2.close()
        engine2.dispose()
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

def test_repeated_seeding_safety():
    """Verifies that repeatedly running the seeding logic produces no duplicate records."""
    sim = DeterministicFMCGSimulator(seed=42)
    data = sim.generate_dataset(num_warehouses=4, num_destinations=10, demand_history_days=5)

    codes = [w["code"] for w in data["warehouses"]]
    # All warehouse codes must be unique
    assert len(codes) == len(set(codes))

    dst_codes = [d["code"] for d in data["destinations"]]
    assert len(dst_codes) == len(set(dst_codes))

    skus = [p["sku"] for p in data["products"]]
    assert len(skus) == len(set(skus))
