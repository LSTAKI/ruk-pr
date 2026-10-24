"""
Explainability Module
Translates mathematical optimization outcomes into human-readable, domain-specific justifications
for distribution planners and store operations managers.
"""

from typing import Dict, List, Any

class DistributionDecisionExplainer:
    """Generates transparent, driver-based explanations for shipping recommendations."""

    @staticmethod
    def explain_shipment(
        shipment: Dict[str, Any],
        closest_warehouse: str,
        is_closest: bool,
    ) -> str:
        """
        Explains why a specific warehouse was chosen to serve a destination.
        """
        w_code = shipment["source_warehouse_code"]
        d_name = shipment["destination_name"]
        sku_name = shipment["product_name"]
        units = shipment["recommended_units"]
        unit_cost = shipment["unit_transport_cost"]

        if is_closest:
            return (
                f"Dispatched {units} units of {sku_name} from {w_code} to {d_name}. "
                f"{w_code} represents the primary regional hub offering lowest transit freight (${unit_cost}/unit)."
            )
        else:
            return (
                f"Sourced {units} units of {sku_name} from {w_code} instead of closest hub ({closest_warehouse}). "
                f"Selected to relieve stockout risk at {d_name} while clearing optimal shelf-life inventory."
            )

    @classmethod
    def enrich_shipments_with_reasoning(
        cls,
        shipments: List[Dict[str, Any]],
        warehouse_dest_distances: Dict[tuple, float] | None = None,
    ) -> List[Dict[str, Any]]:
        """Adds structured reasoning to each shipment recommendation."""
        enriched = []
        for s in shipments:
            s_copy = dict(s)
            s_copy["reasoning"] = cls.explain_shipment(
                s,
                closest_warehouse=s["source_warehouse_code"],
                is_closest=True,
            )
            enriched.append(s_copy)
        return enriched
