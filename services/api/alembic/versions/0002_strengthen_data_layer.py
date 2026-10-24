"""Strengthen data layer: routes, demand history, capacities, and batch status.

Revision ID: 0002_strengthen_data_layer
Revises: 0001_initial_schema
Create Date: 2026-10-24 16:30:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = "0002_strengthen_data_layer"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None

def upgrade() -> None:
    # 1. Update warehouses
    with op.batch_alter_table("warehouses") as batch_op:
        batch_op.add_column(
            sa.Column("daily_dispatch_capacity_units", sa.Integer(), nullable=False, server_default="15000")
        )

    # 2. Update destinations
    with op.batch_alter_table("destinations") as batch_op:
        batch_op.add_column(
            sa.Column("daily_receiving_capacity_units", sa.Integer(), nullable=False, server_default="3000")
        )

    # 3. Update products
    with op.batch_alter_table("products") as batch_op:
        batch_op.add_column(
            sa.Column("unit_of_measure", sa.String(length=32), nullable=False, server_default="units")
        )
        batch_op.add_column(
            sa.Column("holding_cost_per_day", sa.Float(), nullable=False, server_default="0.02")
        )
        batch_op.add_column(
            sa.Column("lost_sales_penalty", sa.Float(), nullable=False, server_default="5.0")
        )

    # 4. Update inventory_items
    with op.batch_alter_table("inventory_items") as batch_op:
        batch_op.add_column(
            sa.Column("unit_cost", sa.Float(), nullable=False, server_default="0.0")
        )
        batch_op.add_column(
            sa.Column("received_date", sa.DateTime(), nullable=False, server_default=sa.func.datetime('now'))
        )
        batch_op.add_column(
            sa.Column("batch_status", sa.String(length=32), nullable=False, server_default="AVAILABLE")
        )
        batch_op.create_index("ix_inventory_wh_prod", ["warehouse_id", "product_id"])
        batch_op.create_index("ix_inventory_expiry", ["expiry_date"])

    # 5. Create routes table
    op.create_table(
        "routes",
        sa.Column("id", sa.Integer(), nullable=False, primary_key=True),
        sa.Column("origin_warehouse_id", sa.Integer(), sa.ForeignKey("warehouses.id"), nullable=False),
        sa.Column("destination_id", sa.Integer(), sa.ForeignKey("destinations.id"), nullable=False),
        sa.Column("unit_transport_cost", sa.Float(), nullable=False),
        sa.Column("lead_time_days", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("distance_km", sa.Float(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=True, server_default=sa.func.datetime('now')),
        sa.UniqueConstraint("origin_warehouse_id", "destination_id", name="uq_route_origin_destination"),
    )
    op.create_index("ix_routes_origin", "routes", ["origin_warehouse_id"])
    op.create_index("ix_routes_destination", "routes", ["destination_id"])

    # 6. Create daily_demand_history table
    op.create_table(
        "daily_demand_history",
        sa.Column("id", sa.Integer(), nullable=False, primary_key=True),
        sa.Column("destination_id", sa.Integer(), sa.ForeignKey("destinations.id"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("demand_date", sa.DateTime(), nullable=False),
        sa.Column("quantity_demanded", sa.Integer(), nullable=False),
        sa.Column("quantity_sold", sa.Integer(), nullable=False),
        sa.Column("is_simulated", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=True, server_default=sa.func.datetime('now')),
        sa.UniqueConstraint("destination_id", "product_id", "demand_date", name="uq_daily_demand_dest_prod_date"),
    )
    op.create_index("ix_demand_history_dest", "daily_demand_history", ["destination_id"])
    op.create_index("ix_demand_history_prod", "daily_demand_history", ["product_id"])
    op.create_index("ix_demand_history_date", "daily_demand_history", ["demand_date"])

def downgrade() -> None:
    op.drop_table("daily_demand_history")
    op.drop_table("routes")

    with op.batch_alter_table("inventory_items") as batch_op:
        batch_op.drop_index("ix_inventory_expiry")
        batch_op.drop_index("ix_inventory_wh_prod")
        batch_op.drop_column("batch_status")
        batch_op.drop_column("received_date")
        batch_op.drop_column("unit_cost")

    with op.batch_alter_table("products") as batch_op:
        batch_op.drop_column("lost_sales_penalty")
        batch_op.drop_column("holding_cost_per_day")
        batch_op.drop_column("unit_of_measure")

    with op.batch_alter_table("destinations") as batch_op:
        batch_op.drop_column("daily_receiving_capacity_units")

    with op.batch_alter_table("warehouses") as batch_op:
        batch_op.drop_column("daily_dispatch_capacity_units")
