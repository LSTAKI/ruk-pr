#!/usr/bin/env python3
"""
Seed Demo Data Script for StockWise AI
Generates deterministic FMCG master data, routes, batch inventory, and 120+ days of
daily demand history using a fixed seed (42).
Populates the persistent SQLite database and saves inspectable raw artifacts to data/demo/.
Safe and idempotent to rerun.
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime

# Adjust sys.path to locate services/api
REPO_ROOT = Path(__file__).resolve().parent.parent
API_DIR = REPO_ROOT / "services" / "api"
sys.path.insert(0, str(API_DIR))

from app.config import settings
from app.db.session import engine, Base, SessionLocal
from app.db.models import (
    DatasetVersion,
    Warehouse,
    Product,
    Destination,
    InventoryItem,
    Route,
    DailyDemandHistory,
)
from app.engine.simulator.fmcg_generator import DeterministicFMCGSimulator

def seed_demo_data():
    print("[*] Starting StockWise AI Enhanced Demo Seeding...")
    print(f"[*] Database URL: {settings.database_url}")
    
    # 1. Ensure DB schema exists
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    # 2. Generate Deterministic FMCG Dataset
    seed = settings.simulator_seed
    simulator = DeterministicFMCGSimulator(seed=seed)
    data = simulator.generate_dataset(
        num_warehouses=settings.num_warehouses,
        num_destinations=settings.num_destinations,
        demand_history_days=settings.demand_history_days,
    )

    # 3. Save JSON artifacts to data/demo/
    demo_dir = REPO_ROOT / "data" / "demo"
    demo_dir.mkdir(parents=True, exist_ok=True)

    def json_serial(obj):
        if isinstance(obj, (datetime,)):
            return obj.isoformat()
        raise TypeError(f"Type {type(obj)} not serializable")

    for key in ["warehouses", "products", "destinations", "routes", "inventory_items"]:
        file_path = demo_dir / f"{key}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data[key], f, indent=2, default=json_serial)
        print(f"[+] Wrote inspectable demo artifact: {file_path}")

    # Write a summary / sample of demand history to demo artifacts
    demand_sample_path = demo_dir / "demand_history_sample.json"
    with open(demand_sample_path, "w", encoding="utf-8") as f:
        json.dump(data["demand_history"][:500], f, indent=2, default=json_serial)
    print(f"[+] Wrote inspectable demo artifact: {demand_sample_path} (Sample 500 records)")

    # 4. Check or Create DatasetVersion in DB
    version_tag = f"v1.0-seed-{seed}"
    ds_ver = db.query(DatasetVersion).filter(DatasetVersion.version_tag == version_tag).first()
    if not ds_ver:
        ds_ver = DatasetVersion(
            version_tag=version_tag,
            description=f"Deterministic FMCG baseline dataset (seed {seed})",
            is_active=True,
            random_seed=seed,
            parameters=data["metadata"],
        )
        db.add(ds_ver)
        db.commit()
        db.refresh(ds_ver)
        print(f"[+] Created DatasetVersion: {version_tag}")
    else:
        print(f"[*] DatasetVersion {version_tag} already exists.")

    # 5. Populate Warehouses (idempotent)
    for w in data["warehouses"]:
        existing = db.query(Warehouse).filter(Warehouse.code == w["code"]).first()
        if not existing:
            db.add(Warehouse(
                code=w["code"],
                name=w["name"],
                city=w["city"],
                state=w["state"],
                capacity_units=w["capacity_units"],
                daily_dispatch_capacity_units=w.get("daily_dispatch_capacity_units", 15000),
                latitude=w["latitude"],
                longitude=w["longitude"],
            ))
        else:
            existing.capacity_units = w["capacity_units"]
            existing.daily_dispatch_capacity_units = w.get("daily_dispatch_capacity_units", 15000)
    db.commit()

    # 6. Populate Products (idempotent)
    for p in data["products"]:
        existing = db.query(Product).filter(Product.sku == p["sku"]).first()
        if not existing:
            db.add(Product(
                sku=p["sku"],
                name=p["name"],
                category=p["category"],
                unit_of_measure=p.get("unit_of_measure", "units"),
                shelf_life_days=p["shelf_life_days"],
                unit_cost=p["unit_cost"],
                unit_price=p["unit_price"],
                holding_cost_per_day=p.get("holding_cost_per_day", 0.02),
                lost_sales_penalty=p.get("lost_sales_penalty", 5.0),
                storage_temp_c=p["storage_temp_c"],
                weight_kg=p["weight_kg"],
            ))
        else:
            existing.shelf_life_days = p["shelf_life_days"]
            existing.unit_cost = p["unit_cost"]
            existing.unit_price = p["unit_price"]
            existing.holding_cost_per_day = p.get("holding_cost_per_day", 0.02)
            existing.lost_sales_penalty = p.get("lost_sales_penalty", 5.0)
    db.commit()

    # 7. Populate Destinations (idempotent)
    for d in data["destinations"]:
        existing = db.query(Destination).filter(Destination.code == d["code"]).first()
        if not existing:
            db.add(Destination(
                code=d["code"],
                name=d["name"],
                channel_type=d["channel_type"],
                city=d["city"],
                state=d["state"],
                daily_receiving_capacity_units=d.get("daily_receiving_capacity_units", 3000),
                latitude=d["latitude"],
                longitude=d["longitude"],
            ))
        else:
            existing.daily_receiving_capacity_units = d.get("daily_receiving_capacity_units", 3000)
    db.commit()

    # Lookup Maps
    wh_map = {w.code: w.id for w in db.query(Warehouse).all()}
    prod_map = {p.sku: p.id for p in db.query(Product).all()}
    dst_map = {d.code: d.id for d in db.query(Destination).all()}

    # 8. Populate Routes (idempotent)
    for r in data["routes"]:
        w_id = wh_map.get(r["origin_warehouse_code"])
        d_id = dst_map.get(r["destination_code"])
        if w_id and d_id:
            existing = db.query(Route).filter(
                Route.origin_warehouse_id == w_id,
                Route.destination_id == d_id,
            ).first()
            if not existing:
                db.add(Route(
                    origin_warehouse_id=w_id,
                    destination_id=d_id,
                    unit_transport_cost=r["unit_transport_cost"],
                    lead_time_days=r["lead_time_days"],
                    distance_km=r["distance_km"],
                    is_active=r["is_active"],
                ))
            else:
                existing.unit_transport_cost = r["unit_transport_cost"]
                existing.lead_time_days = r["lead_time_days"]
                existing.distance_km = r["distance_km"]
                existing.is_active = r["is_active"]
    db.commit()

    # 9. Populate Inventory Items (idempotent per dataset version)
    db.query(InventoryItem).filter(InventoryItem.dataset_version_id == ds_ver.id).delete()
    db.commit()

    items_to_add = []
    for item in data["inventory_items"]:
        w_id = wh_map.get(item["warehouse_code"])
        p_id = prod_map.get(item["product_sku"])
        if w_id and p_id:
            items_to_add.append(InventoryItem(
                dataset_version_id=ds_ver.id,
                warehouse_id=w_id,
                product_id=p_id,
                batch_lot=item["batch_lot"],
                on_hand_units=item["on_hand_units"],
                reserved_units=item["reserved_units"],
                unit_cost=item.get("unit_cost", 0.0),
                expiry_date=item["expiry_date"],
                received_date=item.get("received_date", datetime.utcnow()),
                batch_status=item.get("batch_status", "AVAILABLE"),
            ))

    db.bulk_save_objects(items_to_add)
    db.commit()

    # 10. Populate Daily Demand History (idempotent)
    existing_demand_count = db.query(DailyDemandHistory).count()
    if existing_demand_count < len(data["demand_history"]):
        db.query(DailyDemandHistory).delete()
        db.commit()

        # Batch insert using raw connection for maximum speed on large historical datasets
        raw_conn = engine.raw_connection()
        try:
            cursor = raw_conn.cursor()
            insert_sql = """
            INSERT INTO daily_demand_history 
            (destination_id, product_id, demand_date, quantity_demanded, quantity_sold, is_simulated, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """
            rows = [
                (
                    dst_map[h["destination_code"]],
                    prod_map[h["product_sku"]],
                    h["demand_date"].strftime("%Y-%m-%d %H:%M:%S"),
                    h["quantity_demanded"],
                    h["quantity_sold"],
                    1 if h["is_simulated"] else 0,
                    datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                )
                for h in data["demand_history"]
                if h["destination_code"] in dst_map and h["product_sku"] in prod_map
            ]
            cursor.executemany(insert_sql, rows)
            raw_conn.commit()
            print(f"[+] Seeded {len(rows)} daily demand history records ({settings.demand_history_days} days).")
        finally:
            raw_conn.close()
    else:
        print(f"[*] Daily demand history already seeded ({existing_demand_count} records).")

    db.close()

    print(
        f"[OK] Seeding complete: {len(data['warehouses'])} warehouses, {len(data['products'])} products, "
        f"{len(data['destinations'])} destinations, {len(data['routes'])} routes, "
        f"and {len(items_to_add)} inventory batches seeded successfully."
    )

if __name__ == "__main__":
    seed_demo_data()
