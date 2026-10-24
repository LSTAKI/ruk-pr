"""Tests for the deterministic FMCG simulator."""

from app.engine.simulator.fmcg_generator import DeterministicFMCGSimulator

def test_deterministic_reproducibility():
    sim1 = DeterministicFMCGSimulator(seed=42)
    data1 = sim1.generate_dataset(num_warehouses=4, num_destinations=8)

    sim2 = DeterministicFMCGSimulator(seed=42)
    data2 = sim2.generate_dataset(num_warehouses=4, num_destinations=8)

    assert len(data1["warehouses"]) == len(data2["warehouses"])
    assert len(data1["products"]) == len(data2["products"])
    assert len(data1["inventory_items"]) == len(data2["inventory_items"])

    for item1, item2 in zip(data1["inventory_items"], data2["inventory_items"]):
        assert item1["warehouse_code"] == item2["warehouse_code"]
        assert item1["product_sku"] == item2["product_sku"]
        assert item1["on_hand_units"] == item2["on_hand_units"]
        assert item1["reserved_units"] == item2["reserved_units"]
        assert item1["expiry_date"] == item2["expiry_date"]

def test_simulator_different_seeds():
    sim1 = DeterministicFMCGSimulator(seed=42)
    sim2 = DeterministicFMCGSimulator(seed=99)

    data1 = sim1.generate_dataset(num_warehouses=2, num_destinations=4)
    data2 = sim2.generate_dataset(num_warehouses=2, num_destinations=4)

    # Different seeds should yield different inventory batch quantities and lots
    assert data1["inventory_items"][0]["on_hand_units"] != data2["inventory_items"][0]["on_hand_units"]
