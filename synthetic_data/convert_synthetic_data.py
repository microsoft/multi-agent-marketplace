#!/usr/bin/env python3
"""Adapter to convert synthetic data format to original simulation format.

Usage:
    python convert_synthetic_data.py --input data/synthetic_10_30 --output data/converted_synthetic
"""

import argparse
from pathlib import Path
from typing import Any

import yaml

from agentic_economics.marketplace.base import BusinessMetadata, CustomerMetadata


def convert_business_yaml(synthetic_business: dict[str, Any]) -> dict[str, Any]:
    """Convert synthetic business format to original format."""
    # Use amenities directly without mapping
    feature_values = synthetic_business.get("amenity_features", {})

    data = {
        "name": synthetic_business["name"] + f" ({synthetic_business['id']})",
        "rating": synthetic_business.get("rating", 1.0),
        "description": synthetic_business.get(
            "description", "A restaurant serving great food."
        ),
        "hours": "Unknown",  # Synthetic data does not provide hours
        "feature_values": feature_values,
        "menu_item_price": synthetic_business.get("menu_features", {}),
    }

    try:
        business = BusinessMetadata.from_dict(data)
        return business.model_dump(mode="json")
    except Exception as e:
        raise ValueError(f"Incompatible business data: {data}") from e


def convert_customer_yaml(synthetic_customer: dict[str, Any]) -> dict[str, Any]:
    """Convert synthetic customer format to original format."""
    # Extract menu items and prices
    menu_items = synthetic_customer.get("menu_features", {})
    menu_prices = list(synthetic_customer.get("menu_features", {}).values())

    # Calculate requested price and willingness to pay
    if not menu_prices:
        raise ValueError(f"Customer data missing menu_features: {synthetic_customer}")

    requested_price = sum(menu_prices)
    willingness_to_pay = requested_price * 2.0  # Assume 2x willingness to pay

    # Use amenities directly without mapping
    selected_binary_features: list[str] = synthetic_customer.get("amenity_features", [])

    # Flatten data structure to match CustomerMetadata model
    data = {
        "user_request": synthetic_customer["request"],
        "name": synthetic_customer.get("name", "Unknown Customer")
        + f" ({synthetic_customer['id']})",
        "requested_price": round(requested_price, 2),
        "willingness_to_pay": round(willingness_to_pay, 2),
        "city": None,
        "state": None,
        "requested_time": None,
        "selected_binary_features": list(
            set(selected_binary_features)
        ),  # Remove duplicates
        "selected_menu_items": menu_items,
    }

    # Validate with the CustomerMetadata model
    try:
        customer = CustomerMetadata.model_validate(data)
        return customer.model_dump(mode="json")
    except Exception as e:
        raise ValueError(f"Incompatible customer data: {data}") from e


def convert_directory(input_dir: Path, output_dir: Path) -> None:
    """Convert entire directory structure from synthetic to original format."""
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)

    # Create output directories
    (output_dir / "businesses").mkdir(parents=True, exist_ok=True)
    (output_dir / "customers").mkdir(parents=True, exist_ok=True)

    # Convert businesses
    business_dir = input_dir / "businesses"
    if business_dir.exists():
        for yaml_file in business_dir.glob("*.yaml"):
            print(f"Converting business: {yaml_file.name}")

            with open(yaml_file) as f:
                synthetic_data = yaml.safe_load(f)

            converted_data = convert_business_yaml(synthetic_data)

            # Use original filename or derive from name
            output_file = output_dir / "businesses" / yaml_file.name

            with open(output_file, "w") as f:
                yaml.dump(converted_data, f, default_flow_style=False, sort_keys=False)

    # Convert customers
    customer_dir = input_dir / "customers"
    if customer_dir.exists():
        for yaml_file in customer_dir.glob("*.yaml"):
            print(f"Converting customer: {yaml_file.name}")

            with open(yaml_file) as f:
                synthetic_data = yaml.safe_load(f)

            converted_data = convert_customer_yaml(synthetic_data)

            # Use original filename
            output_file = output_dir / "customers" / yaml_file.name

            with open(output_file, "w") as f:
                yaml.dump(converted_data, f, default_flow_style=False, sort_keys=False)


def main():
    """Entry point for the synthetic data conversion script."""
    parser = argparse.ArgumentParser(
        description="Convert synthetic data format to original simulation format"
    )
    parser.add_argument(
        "--input", "-i", required=True, help="Input directory with synthetic data"
    )
    parser.add_argument(
        "--output", "-o", required=True, help="Output directory for converted data"
    )

    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    if not input_path.exists():
        print(f"Error: Input directory {input_path} does not exist")
        return 1

    print(f"Converting synthetic data from {input_path} to {output_path}")
    convert_directory(input_path, output_path)
    print("Conversion complete!")

    return 0


if __name__ == "__main__":
    exit(main())
