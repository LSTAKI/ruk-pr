"""Initial schema for StockWise AI.

Revision ID: 0001_initial_schema
Revises: 
Create Date: 2026-10-24 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        "dataset_versions",
        sa.Column("id", sa.Integer(), nullable=False, primary_key=True),
        sa.Column("version_tag", sa.String(length=64), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), default=True),
        sa.Column("random_seed", sa.Integer(), default=42, nullable=False),
        sa.Column("parameters", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(op.f("ix_dataset_versions_version_tag"), "dataset_versions", ["version_tag"], unique=True)

    op.create_table(
        "warehouses",
        sa.Column("id", sa.Integer(), nullable=False, primary_key=True),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("city", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=64), nullable=False),
        sa.Column("capacity_units", sa.Integer(), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index(op.f("ix_warehouses_code"), "warehouses", ["code"], unique=True)

    op.create_table(
        "destinations",
        sa.Column("id", sa.Integer(), nullable=False, primary_key=True),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("channel_type", sa.String(length=64), nullable=False),
        sa.Column("city", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=64), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index(op.f("ix_destinations_code"), "destinations", ["code"], unique=True)

    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), nullable=False, primary_key=True),
        sa.Column("sku", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("shelf_life_days", sa.Integer(), nullable=False),
        sa.Column("unit_cost", sa.Float(), nullable=False),
        sa.Column("unit_price", sa.Float(), nullable=False),
        sa.Column("storage_temp_c", sa.Float(), nullable=True),
        sa.Column("weight_kg", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index(op.f("ix_products_sku"), "products", ["sku"], unique=True)

    op.create_table(
        "inventory_items",
        sa.Column("id", sa.Integer(), nullable=False, primary_key=True),
        sa.Column("dataset_version_id", sa.Integer(), sa.ForeignKey("dataset_versions.id"), nullable=False),
        sa.Column("warehouse_id", sa.Integer(), sa.ForeignKey("warehouses.id"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("batch_lot", sa.String(length=64), nullable=False),
        sa.Column("on_hand_units", sa.Integer(), nullable=False),
        sa.Column("reserved_units", sa.Integer(), nullable=False),
        sa.Column("expiry_date", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )

    op.create_table(
        "planning_runs",
        sa.Column("id", sa.Integer(), nullable=False, primary_key=True),
        sa.Column("run_code", sa.String(length=64), nullable=False),
        sa.Column("dataset_version_id", sa.Integer(), sa.ForeignKey("dataset_versions.id"), nullable=False),
        sa.Column("forecast_identifier", sa.String(length=128), nullable=False),
        sa.Column("optimization_parameters", sa.JSON(), nullable=True),
        sa.Column("solver_status", sa.String(length=32), nullable=False),
        sa.Column("total_transport_cost", sa.Float(), nullable=True),
        sa.Column("total_shipped_units", sa.Integer(), nullable=True),
        sa.Column("stockout_risk_count", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index(op.f("ix_planning_runs_run_code"), "planning_runs", ["run_code"], unique=True)

    op.create_table(
        "shipment_recommendations",
        sa.Column("id", sa.Integer(), nullable=False, primary_key=True),
        sa.Column("planning_run_id", sa.Integer(), sa.ForeignKey("planning_runs.id"), nullable=False),
        sa.Column("source_warehouse_id", sa.Integer(), sa.ForeignKey("warehouses.id"), nullable=False),
        sa.Column("destination_id", sa.Integer(), sa.ForeignKey("destinations.id"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("recommended_units", sa.Integer(), nullable=False),
        sa.Column("unit_transport_cost", sa.Float(), nullable=False),
        sa.Column("total_transport_cost", sa.Float(), nullable=False),
        sa.Column("estimated_expiry_risk_pct", sa.Float(), nullable=True),
        sa.Column("priority_score", sa.Float(), nullable=True),
        sa.Column("reasoning", sa.Text(), nullable=True),
    )

def downgrade() -> None:
    op.drop_table("shipment_recommendations")
    op.drop_table("planning_runs")
    op.drop_table("inventory_items")
    op.drop_table("products")
    op.drop_table("destinations")
    op.drop_table("warehouses")
    op.drop_table("dataset_versions")
