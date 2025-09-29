"""YAML loading functions for experiment data."""

from pathlib import Path

import yaml

from magentic_marketplace.marketplace.shared.models import Business, Customer


def load_businesses_from_yaml(businesses_dir: Path) -> list[Business]:
    """Load business profiles from YAML files in the given directory."""
    businesses: list[Business] = []

    if not businesses_dir.exists():
        raise FileNotFoundError(f"Businesses directory not found: {businesses_dir}")

    yaml_files = list(businesses_dir.glob("*.yaml")) + list(
        businesses_dir.glob("*.yml")
    )

    if not yaml_files:
        raise ValueError(
            f"No YAML files found in businesses directory: {businesses_dir}"
        )

    for yaml_file in sorted(yaml_files):
        with open(yaml_file, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        business = Business.model_validate(data)
        businesses.append(business)

    return businesses


def load_customers_from_yaml(customers_dir: Path) -> list[Customer]:
    """Load customer profiles from YAML files in the given directory."""
    customers: list[Customer] = []

    if not customers_dir.exists():
        raise FileNotFoundError(f"Customers directory not found: {customers_dir}")

    yaml_files = list(customers_dir.glob("*.yaml")) + list(customers_dir.glob("*.yml"))

    if not yaml_files:
        raise ValueError(f"No YAML files found in customers directory: {customers_dir}")

    for yaml_file in sorted(yaml_files):
        with open(yaml_file, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        customer = Customer.model_validate(data)
        customers.append(customer)

    return customers
