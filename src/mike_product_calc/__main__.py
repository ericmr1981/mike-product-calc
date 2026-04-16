"""mike_product_calc __main__ entrypoint.

Usage:
    python -m mike_product_calc <command> [args...]
    mpc <command> [args...]       # via pyproject.toml scripts entry
    mike-product-calc <command>   # via pyproject.toml scripts entry
"""
from mike_product_calc.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
