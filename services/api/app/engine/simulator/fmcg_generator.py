"""
Deterministic FMCG Distribution Dataset Generator
Generates realistic, reproducible warehouse, destination, product, batch inventory,
transportation routes, and 120+ days of historical demand using a fixed random seed.

All generated data is explicitly identified as simulated.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Any
import numpy as np
import math

FMCG_CATEGORIES = {
    "Dairy": [
        ("Fresh Milk 1L", "L", 14, 1.20, 1.80, 0.04, 3.50, 4.0),
        ("Greek Yogurt 500g", "units", 28, 1.80, 2.70, 0.03, 4.00, 4.0),
        ("Cheddar Cheese 200g", "units", 60, 2.40, 3.80, 0.02, 6.00, 4.0),
        ("Butter Unsalted 250g", "units", 90, 2.10, 3.20, 0.02, 5.50, 4.0),
    ],
    "Beverages": [
        ("Cold Brew Coffee 330ml", "units", 45, 1.50, 2.99, 0.02, 4.50, 4.0),
        ("Sparkling Mineral Water 1L", "bottles", 180, 0.45, 1.10, 0.01, 2.00, 20.0),
        ("Organic Orange Juice 1L", "bottles", 30, 1.60, 2.50, 0.03, 4.00, 4.0),
        ("Green Tea 500ml", "bottles", 120, 0.70, 1.60, 0.01, 2.50, 20.0),
    ],
    "Snacks": [
        ("Sea Salt Potato Chips 150g", "bags", 120, 0.90, 2.20, 0.01, 3.00, 22.0),
        ("Almond Protein Bar 60g", "bars", 180, 1.10, 2.50, 0.01, 3.50, 22.0),
        ("Dark Chocolate Pretzel 100g", "packs", 150, 1.30, 2.80, 0.01, 4.00, 20.0),
        ("Baked Pita Crackers 125g", "boxes", 140, 0.85, 2.10, 0.01, 2.80, 22.0),
    ],
    "Personal Care": [
        ("Moisturizing Hand Wash 250ml", "bottles", 365, 1.40, 3.50, 0.005, 5.00, 20.0),
        ("Eco Bamboo Toothpaste 100ml", "tubes", 365, 1.20, 3.20, 0.005, 4.50, 20.0),
        ("Hydrating Shower Gel 400ml", "bottles", 365, 1.70, 4.20, 0.005, 6.00, 20.0),
        ("Gentle Facial Cleanser 150ml", "bottles", 365, 2.50, 6.00, 0.005, 8.00, 20.0),
    ],
}

WAREHOUSE_LOCATIONS = [
    ("Central Metro DC", "North Central", 41.8781, -87.6298, 75000, 25000),   # Chicago
    ("Eastern Logistics Hub", "Northeast", 40.7128, -74.0060, 95000, 35000),  # NYC
    ("Southern Regional Hub", "South", 33.7490, -84.3880, 65000, 20000),      # Atlanta
    ("Western Gateway Hub", "West Coast", 34.0522, -118.2437, 50000, 15000),  # LA
]

DESTINATION_BASE_CITIES = [
    # IL / Midwest
    ("Metro Mart Express 101", "supermarket", "Chicago", "IL", 41.8818, -87.6231, 3500),
    ("Lakeside Convenience 04", "convenience", "Evanston", "IL", 42.0451, -87.6877, 1200),
    ("Midwest Wholesale 12", "wholesaler", "Peoria", "IL", 40.6936, -89.5890, 8000),
    ("Lincoln Park Fresh Mart", "supermarket", "Chicago", "IL", 41.9214, -87.6513, 3000),
    ("Naperville Daily Goods", "supermarket", "Naperville", "IL", 41.7508, -88.1535, 3200),
    ("Rockford QuickMart", "convenience", "Rockford", "IL", 42.2711, -89.0940, 1500),
    ("Springfield Depot", "wholesaler", "Springfield", "IL", 39.7817, -89.6501, 6000),
    ("Champaign Pantry", "convenience", "Champaign", "IL", 40.1164, -88.2434, 1100),
    # NY / Northeast
    ("Manhattan Fresh 52", "supermarket", "New York", "NY", 40.7580, -73.9855, 4000),
    ("Brooklyn Corner Bodega 09", "convenience", "Brooklyn", "NY", 40.6782, -73.9442, 1000),
    ("Jersey Wholesale Depot", "wholesaler", "Newark", "NJ", 40.7357, -74.1724, 9000),
    ("Queens Boulevard Mart", "supermarket", "Queens", "NY", 40.7282, -73.7949, 3200),
    ("Bronx Community Grocer", "supermarket", "Bronx", "NY", 40.8448, -73.8648, 2800),
    ("Hoboken River Market", "convenience", "Hoboken", "NJ", 40.7439, -74.0324, 1300),
    ("Philadelphia Food Hall", "supermarket", "Philadelphia", "PA", 39.9526, -75.1652, 3800),
    ("Boston Harbor Grocer", "supermarket", "Boston", "MA", 42.3601, -71.0589, 3600),
    ("Providence QuickStop", "convenience", "Providence", "RI", 41.8240, -71.4128, 1200),
    ("Hartford Wholesale Club", "wholesaler", "Hartford", "CT", 41.7658, -72.6734, 7500),
    # GA / Southeast
    ("Buckhead Organic Grocer", "supermarket", "Atlanta", "GA", 33.8378, -84.3813, 3500),
    ("Savannah Coastal Market", "convenience", "Savannah", "GA", 32.0809, -81.0912, 1400),
    ("Dixie Cash & Carry", "wholesaler", "Macon", "GA", 32.8407, -83.6324, 6500),
    ("Midtown Atlanta Mart", "convenience", "Atlanta", "GA", 33.7840, -84.3830, 1600),
    ("Charlotte Daily Goods", "supermarket", "Charlotte", "NC", 35.2271, -80.8431, 3400),
    ("Raleigh Triangle Market", "supermarket", "Raleigh", "NC", 35.7796, -78.6382, 3100),
    ("Nashville Music City Grocer", "supermarket", "Nashville", "TN", 36.1627, -86.7816, 3600),
    ("Memphis River Wholesale", "wholesaler", "Memphis", "TN", 35.1495, -90.0490, 7000),
    ("Jacksonville Sun Market", "supermarket", "Jacksonville", "FL", 30.3322, -81.6557, 3300),
    ("Orlando Theme Pantry", "convenience", "Orlando", "FL", 28.5383, -81.3792, 1500),
    ("Tampa Bay Grocers", "supermarket", "Tampa", "FL", 27.9506, -82.4572, 3200),
    ("Miami Beach Fresh Corner", "convenience", "Miami", "FL", 25.7617, -80.1918, 1800),
    # CA / West Coast
    ("Bay Area Gourmet 88", "supermarket", "San Francisco", "CA", 37.7749, -122.4194, 3800),
    ("SoCal QuickStop 19", "convenience", "Long Beach", "CA", 33.7701, -118.1937, 1400),
    ("Pacific Rim Wholesale", "wholesaler", "Oakland", "CA", 37.8044, -122.2712, 8500),
    ("Silicon Valley Mart", "convenience", "San Jose", "CA", 37.3382, -121.8863, 1700),
    ("Hollywood Sunset Foods", "supermarket", "Los Angeles", "CA", 34.0928, -118.3287, 3900),
    ("San Diego Border Grocer", "supermarket", "San Diego", "CA", 32.7157, -117.1611, 3500),
    ("Pasadena Valley Market", "convenience", "Pasadena", "CA", 34.1478, -118.1445, 1300),
    ("Sacramento Capitol Foods", "supermarket", "Sacramento", "CA", 38.5816, -121.4944, 3200),
    ("Fresno Central Wholesale", "wholesaler", "Fresno", "CA", 36.7468, -119.7726, 6800),
    ("Seattle Sound Grocers", "supermarket", "Seattle", "WA", 47.6062, -122.3321, 3700),
    ("Portland Rose Pantry", "convenience", "Portland", "OR", 45.5152, -122.6784, 1500),
    # Central / South Central
    ("Midtown Pantry 03", "convenience", "Indianapolis", "IN", 39.7684, -86.1581, 1400),
    ("Columbus Metro Foods", "supermarket", "Columbus", "OH", 39.9612, -82.9988, 3300),
    ("Cleveland Lakefront Mart", "supermarket", "Cleveland", "OH", 41.4993, -81.6944, 3100),
    ("Detroit Motor Market", "supermarket", "Detroit", "MI", 42.3314, -83.0458, 3400),
    ("Milwaukee River Pantry", "convenience", "Milwaukee", "WI", 43.0389, -87.9065, 1300),
    ("Minneapolis Twin Mart", "supermarket", "Minneapolis", "MN", 44.9778, -93.2650, 3600),
    ("Dallas Lone Star Grocer", "supermarket", "Dallas", "TX", 32.7767, -96.7970, 4200),
    ("Houston Gulf Wholesale", "wholesaler", "Houston", "TX", 29.7604, -95.3698, 9200),
    ("Austin River City Mart", "convenience", "Austin", "TX", 30.2672, -97.7431, 1600),
]

def calculate_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2.0) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return round(R * c, 2)

class DeterministicFMCGSimulator:
    """Generates synthetic, deterministic supply chain data for FMCG distribution."""

    def __init__(self, seed: int = 42):
        self.seed = seed
        self.rng = np.random.default_rng(seed)

    def generate_dataset(
        self,
        num_warehouses: int = 4,
        num_destinations: int = 50,
        demand_history_days: int = 120,
        base_date: datetime | None = None,
    ) -> Dict[str, Any]:
        """Generates all entities: warehouses, products, destinations, routes, batches, and demand history."""
        if base_date is None:
            base_date = datetime(2026, 10, 24, 0, 0, 0)

        # 1. Warehouses
        warehouses = []
        for i, (name, region, lat, lon, cap, dispatch_cap) in enumerate(WAREHOUSE_LOCATIONS[:num_warehouses]):
            warehouses.append({
                "code": f"WH-{i+1:02d}",
                "name": name,
                "city": name.split()[0],
                "state": region,
                "capacity_units": cap,
                "daily_dispatch_capacity_units": dispatch_cap,
                "latitude": lat,
                "longitude": lon,
            })

        # 2. Products
        products = []
        sku_counter = 1
        for category, items in FMCG_CATEGORIES.items():
            for name, uom, shelf_days, cost, price, hold_cost, penalty, temp in items:
                products.append({
                    "sku": f"SKU-{sku_counter:04d}",
                    "name": name,
                    "category": category,
                    "unit_of_measure": uom,
                    "shelf_life_days": shelf_days,
                    "unit_cost": cost,
                    "unit_price": price,
                    "holding_cost_per_day": hold_cost,
                    "lost_sales_penalty": penalty,
                    "storage_temp_c": temp,
                    "weight_kg": round(float(self.rng.uniform(0.2, 1.5)), 2),
                })
                sku_counter += 1

        # 3. Destinations (50 distinct stores)
        destinations = []
        for i, (name, channel, city, state, lat, lon, rec_cap) in enumerate(DESTINATION_BASE_CITIES[:num_destinations]):
            destinations.append({
                "code": f"DST-{i+1:03d}",
                "name": name,
                "channel_type": channel,
                "city": city,
                "state": state,
                "daily_receiving_capacity_units": rec_cap,
                "latitude": lat,
                "longitude": lon,
            })

        # 4. Transportation Routes (4 Warehouses x 50 Destinations = 200 Routes)
        routes = []
        for wh in warehouses:
            for dst in destinations:
                dist = calculate_distance_km(wh["latitude"], wh["longitude"], dst["latitude"], dst["longitude"])
                # Transit freight: $0.40 base + $0.0015/km/unit
                unit_cost = max(0.45, round(dist * 0.0015, 2))
                # Lead time: ~650km per transit day, minimum 1.0 day
                lead_days = max(1.0, round(dist / 650.0, 1))

                # Edge case 6: Inactive routes for remote pairs (e.g. WH-04 to remote Northeast stores)
                is_active = True
                if wh["code"] == "WH-04" and dst["state"] in ("NY", "MA", "RI", "CT") and dist > 3500:
                    is_active = False

                routes.append({
                    "origin_warehouse_code": wh["code"],
                    "destination_code": dst["code"],
                    "unit_transport_cost": unit_cost,
                    "lead_time_days": lead_days,
                    "distance_km": dist,
                    "is_active": is_active,
                })

        # 5. Inventory Batches with Realistic Edge Cases
        inventory_items = []
        batch_counter = 1000

        for wh in warehouses:
            for prod in products:
                sku = prod["sku"]
                # Edge case 5: SKU-0004 (Butter) has network-wide shortage
                is_scarce_product = (sku == "SKU-0004")

                # Edge case 1: WH-04 has low stock across products
                is_low_stock_warehouse = (wh["code"] == "WH-04")

                # Edge case 3: WH-02 has excess stock
                is_excess_stock_warehouse = (wh["code"] == "WH-02")

                num_batches = 1 if is_scarce_product or is_low_stock_warehouse else int(self.rng.integers(2, 5))

                for b_idx in range(num_batches):
                    # Shelf life and expiration scheduling
                    shelf = prod["shelf_life_days"]

                    # Edge case 4: Near-expiry inventory for first batch of perishables in WH-01 & WH-03
                    if b_idx == 0 and prod["category"] == "Dairy" and wh["code"] in ("WH-01", "WH-03"):
                        days_remaining = int(self.rng.integers(3, 6))  # Expiring in 3-5 days
                    elif b_idx == 1 and wh["code"] == "WH-04" and self.rng.random() < 0.15:
                        days_remaining = -2  # Expired 2 days ago (Edge case for accounting exclusion)
                    else:
                        days_remaining = int(self.rng.integers(10, max(12, shelf + 1)))

                    expiry_date = base_date + timedelta(days=days_remaining)
                    received_date = base_date - timedelta(days=int(self.rng.integers(1, 30)))

                    # Units quantity calibration
                    if is_scarce_product:
                        on_hand = int(self.rng.integers(15, 35))
                    elif is_low_stock_warehouse:
                        on_hand = int(self.rng.integers(40, 120))
                    elif is_excess_stock_warehouse:
                        on_hand = int(self.rng.integers(2500, 4500))
                    else:
                        on_hand = int(self.rng.integers(400, 1500))

                    # Edge case 7: Reserved stock (locks 60-80% of units on specific lots)
                    if b_idx == 0 and self.rng.random() < 0.25:
                        reserved = int(on_hand * self.rng.uniform(0.60, 0.85))
                    else:
                        reserved = int(on_hand * self.rng.uniform(0.05, 0.15))

                    batch_status = "EXPIRED" if days_remaining <= 0 else "AVAILABLE"
                    # Small chance of quarantine
                    if days_remaining > 0 and self.rng.random() < 0.03:
                        batch_status = "QUARANTINED"

                    inventory_items.append({
                        "warehouse_code": wh["code"],
                        "product_sku": sku,
                        "batch_lot": f"LOT-{batch_counter}",
                        "on_hand_units": on_hand,
                        "reserved_units": reserved,
                        "unit_cost": prod["unit_cost"],
                        "expiry_date": expiry_date,
                        "received_date": received_date,
                        "batch_status": batch_status,
                    })
                    batch_counter += 1

        # 6. Daily Product-Destination Demand History (>= 120 Days)
        # Vectorized/fast deterministic historical generation
        demand_history = []
        channel_mult = {"supermarket": 2.2, "wholesaler": 4.8, "convenience": 0.8}
        cat_mult = {"Dairy": 1.7, "Beverages": 1.3, "Snacks": 1.2, "Personal Care": 0.6}

        start_date = base_date - timedelta(days=demand_history_days)
        # Generate daily records for all 50 destinations and 16 products
        for dst in destinations:
            ch_factor = channel_mult.get(dst["channel_type"], 1.0)
            is_stockout_destination = (dst["code"] == "DST-001")  # Edge case 2: DST-001 has surging demand

            for prod in products:
                cat_factor = cat_mult.get(prod["category"], 1.0)
                base_demand = 12.0 * ch_factor * cat_factor
                if is_stockout_destination:
                    base_demand *= 1.8  # Elevated demand driving stockout risk

                # Generate daily demand over the 120-day window
                for day_idx in range(demand_history_days):
                    cur_date = start_date + timedelta(days=day_idx)
                    weekday = cur_date.weekday()

                    # Day of week pattern:
                    # Dairy: Mon(0)-Thu(3) higher
                    # Snacks/Beverages: Fri(4)-Sun(6) weekend spikes
                    day_factor = 1.0
                    if prod["category"] == "Dairy":
                        day_factor = 1.25 if weekday in (0, 1, 2) else 0.85
                    elif prod["category"] in ("Snacks", "Beverages"):
                        day_factor = 1.35 if weekday in (4, 5, 6) else 0.85

                    # Noise factor
                    noise = float(self.rng.normal(1.0, 0.12))
                    qty_demanded = max(1, int(round(base_demand * day_factor * noise)))
                    # Quantity sold: occasionally short on stockout-prone stores
                    fulfillment_rate = 0.85 if is_stockout_destination and day_idx > 110 else 1.0
                    qty_sold = int(round(qty_demanded * fulfillment_rate))

                    demand_history.append({
                        "destination_code": dst["code"],
                        "product_sku": prod["sku"],
                        "demand_date": cur_date,
                        "quantity_demanded": qty_demanded,
                        "quantity_sold": qty_sold,
                        "is_simulated": True,
                    })

        return {
            "metadata": {
                "seed": self.seed,
                "generated_at": base_date.isoformat(),
                "history_start_date": start_date.isoformat(),
                "history_end_date": base_date.isoformat(),
                "demand_history_days": demand_history_days,
                "total_warehouses": len(warehouses),
                "total_products": len(products),
                "total_destinations": len(destinations),
                "total_routes": len(routes),
                "total_inventory_records": len(inventory_items),
                "total_demand_history_records": len(demand_history),
                "is_simulated": True,
                "simulation_disclaimer": "This dataset is deterministically simulated for FMCG supply chain intelligence and testing.",
            },
            "warehouses": warehouses,
            "products": products,
            "destinations": destinations,
            "routes": routes,
            "inventory_items": inventory_items,
            "demand_history": demand_history,
        }
