#!/usr/bin/env python3
"""
StockWise AI - Local Developer Environment & Dependency Verification Script
Checks local requirements: Python version, Node.js, npm, SQLite, and packages.
"""

import sys
import os
import subprocess
import sqlite3
import importlib.util

def print_status(component: str, ok: bool, details: str = ""):
    symbol = "[PASS]" if ok else "[FAIL]"
    message = f"{symbol:<7} | {component:<24} | {details}"
    print(message)
    return ok

def check_python():
    version = sys.version_info
    valid = (version.major == 3 and version.minor >= 11)
    return print_status(
        "Python Runtime",
        valid,
        f"{version.major}.{version.minor}.{version.micro} (Requires Python >= 3.11)"
    )

def check_node():
    try:
        res = subprocess.run(["node", "--version"], capture_output=True, text=True, check=True)
        version = res.stdout.strip()
        major = int(version.lstrip("v").split(".")[0])
        return print_status("Node.js Runtime", major >= 18, f"{version} (Requires Node.js >= 18)")
    except Exception as e:
        return print_status("Node.js Runtime", False, f"Not found or error: {e}")

def check_npm():
    try:
        res = subprocess.run(["npm", "--version"], capture_output=True, text=True, check=True, shell=True)
        return print_status("npm Package Manager", True, f"v{res.stdout.strip()}")
    except Exception as e:
        return print_status("npm Package Manager", False, f"Not found or error: {e}")

def check_sqlite():
    try:
        conn = sqlite3.connect(":memory:")
        cursor = conn.cursor()
        cursor.execute("SELECT sqlite_version();")
        version = cursor.fetchone()[0]
        conn.close()
        return print_status("SQLite3 Support", True, f"SQLite v{version} ready")
    except Exception as e:
        return print_status("SQLite3 Support", False, f"Failed: {e}")

def check_python_modules():
    modules = [
        ("fastapi", "FastAPI"),
        ("pydantic", "Pydantic v2"),
        ("sqlalchemy", "SQLAlchemy 2"),
        ("alembic", "Alembic"),
        ("ortools", "Google OR-Tools"),
        ("pandas", "Pandas"),
        ("numpy", "NumPy"),
        ("pytest", "Pytest"),
    ]
    all_ok = True
    print("\n--- Python Backend Dependency Check ---")
    for mod_name, label in modules:
        spec = importlib.util.find_spec(mod_name)
        if spec is not None:
            print_status(label, True, f"Module '{mod_name}' is installed")
        else:
            print_status(label, False, f"Missing. Run: pip install -r services/api/requirements.txt")
            all_ok = False
    return all_ok

def check_docker():
    try:
        res = subprocess.run(["docker", "--version"], capture_output=True, text=True)
        if res.returncode == 0:
            print_status("Docker Engine", True, res.stdout.strip())
        else:
            print_status("Docker Engine", False, "Docker not running / installed (Use local no-Docker workflow)")
    except Exception:
        print_status("Docker Engine", False, "Docker not in PATH (Use local no-Docker workflow)")

def main():
    print("=" * 70)
    print("StockWise AI - System Environment Verification")
    print("=" * 70)
    
    r_py = check_python()
    r_node = check_node()
    r_npm = check_npm()
    r_sql = check_sqlite()
    check_docker()
    check_python_modules()
    
    print("=" * 70)
    if r_py and r_node and r_npm and r_sql:
        print("Core Developer System Requirements: OK")
        print("Ready for local setup and testing.")
    else:
        print("WARNING: Some core requirements are not satisfied. Please review the table above.")

if __name__ == "__main__":
    main()
