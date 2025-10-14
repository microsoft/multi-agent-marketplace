"""Validate the generated customers and businesses."""

import argparse
import os
import sys

import yaml
from base import Business, Customer, ItemFeature
from utils import find_similar


def search_by_menu_item(
    businesses: dict[str, Business], items: list[str]
) -> list[Business]:
    """Return all businesses that have all of the specified menu items."""
    results: list[Business] = []
    for b in businesses.values():
        if all(item in b.menu_features for item in items):
            results.append(b)
    return results


def find_overlapping_orders(
    customer: Customer, customers: dict[str, Customer]
) -> list[Customer]:
    """Find other customers with overlapping orders."""
    overlapping_customers: list[Customer] = []
    customer_items = set(customer.menu_features.keys())
    for other in customers.values():
        if other.id == customer.id:
            continue
        other_items = set(other.menu_features.keys())
        intersection = customer_items & other_items
        assert len(intersection) < len(customer_items), (
            "Customers should not have identical orders."
        )
        if len(intersection) > 0:
            overlapping_customers.append(other)
    return overlapping_customers


def main(features_dir: str, data_dir: str) -> None:
    """Validate the generated customers and businesses."""
    # Load the menu item distributions
    menu_items: dict[str, ItemFeature] = {}
    with open(os.path.join(features_dir, "items.yaml")) as file:
        data = yaml.safe_load(file)
        for item in data:
            menu_items[item["name"]] = ItemFeature(**item)
    print(f"Loaded {len(menu_items)} item.")

    # Load the customers
    customers: dict[str, Customer] = {}
    for filename in sorted(os.listdir(os.path.join(data_dir, "customers"))):
        if filename.endswith(".yaml") or filename.endswith(".yml"):
            with open(os.path.join(data_dir, "customers", filename)) as f:
                data = yaml.safe_load(f)
                customers[data["id"]] = Customer(**data)

    if len(customers) == 0:
        sys.stderr.write("No customers found.\n")
        sys.exit(1)
    print(f"Loaded {len(customers)} customers.")

    # Load the businesses
    businesses: dict[str, Business] = {}
    for filename in sorted(os.listdir(os.path.join(data_dir, "businesses"))):
        if filename.endswith(".yaml") or filename.endswith(".yml"):
            with open(os.path.join(data_dir, "businesses", filename)) as f:
                data = yaml.safe_load(f)
                businesses[data["id"]] = Business(**data)

    if len(businesses) == 0:
        sys.stderr.write("No businesses found.\n")
        sys.exit(1)
    print(f"Loaded {len(businesses)} businesses.")

    if len(businesses) != 3 * len(customers):
        sys.stderr.write(
            f"Expected {3 * len(customers)} businesses, but found {len(businesses)}.\n"
        )
        sys.exit(1)

    print("\U00002705 Business count matches expectation.")

    # Check for name collisions in business names
    business_names = [b.name for b in businesses.values()]
    collision = find_similar(business_names)
    if collision is not None:
        sys.stderr.write(
            f"Business name overlap found: '{collision[0]}' and '{collision[1]}'.\n"
        )
        sys.exit(1)
    print("\U00002705 No significant business name overlap found.")

    # Check for collisions in menu items
    all_menu_items = list(
        {item for b in businesses.values() for item in b.menu_features.keys()}
    )
    collision = find_similar(all_menu_items)
    if collision is not None:
        sys.stderr.write(
            f"Menu item name overlap found: '{collision[0]}' and '{collision[1]}'.\n"
        )
        sys.exit(1)
    print("\U00002705 No significant menu item overlap found.")

    # Check that each business has a matching customer
    for b in businesses.values():
        if b.progenitor_customer not in customers:
            sys.stderr.write(
                f"Business '{b.name}' has unknown progenitor customer '{b.progenitor_customer}'.\n"
            )
            sys.exit(1)
    print("\U00002705 All businesses have valid progenitor customers.")
    print()

    # Check that min_price_factor is always greater than 0 and less than or equal to 1
    for b in businesses.values():
        if b.min_price_factor <= 0.0 or b.min_price_factor > 1.0:
            sys.stderr.write(
                f"Business '{b.name}' has invalid min_price_factor '{b.min_price_factor}'.\n"
            )
            sys.exit(1)

    # Check the scenarios for each customer
    n_greedy_fails = 0
    n_negotiation_changes_choice = 0
    n_overlapping_orders = 0

    for c in customers.values():
        print("Validating customer:", c.name)

        # Check that the requested_price is set correctly
        for item in c.menu_features:
            if item not in menu_items:
                sys.stderr.write(
                    f"Customer '{c.name}' requests unknown menu item '{item}'.\n"
                )
                sys.exit(1)

            if c.menu_features[item] != menu_items[item].mean_price:
                sys.stderr.write(
                    f"Customer '{c.name}' requests item '{item}' does not match expected price {menu_items[item].mean_price}.\n"
                )
                sys.exit(1)
        print("  \U00002705 All requested menu items have valid requested prices.")

        # Check for overlapping orders with other customers
        overlapping_customers = find_overlapping_orders(c, customers)
        n_overlapping_orders += len(overlapping_customers)
        print(
            f"  \U00002139 Found {len(overlapping_customers)} other customers with partially overlapping orders."
        )

        # How many many items are requested?
        if len(c.menu_features) == 1:
            print("  \U00002139 Customer requests 1 menu item.")
        else:
            print(f"  \U00002139 Customer requests {len(c.menu_features)} menu items.")

        # How many amenities are requested?
        if len(c.amenity_features) == 1:
            print("  \U00002139 Customer requests 1 amenity.")
        else:
            print(
                f"  \U00002139 Customer requests {len(c.amenity_features)} amenities."
            )

        # Get all matching businesses
        matching_businesses = search_by_menu_item(
            businesses, list(c.menu_features.keys())
        )
        print(
            "  \U00002139 Found",
            len(matching_businesses),
            "businesses matching menu items.",
        )

        # Check that each lists this customer as progenitor
        for b in matching_businesses:
            if b.progenitor_customer != c.id:
                sys.stderr.write(
                    f"Business '{b.name}' does not list customer '{c.name}' as progenitor.\n"
                )
                sys.exit(1)
        print("  \U00002705 All matching businesses list this customer as progenitor.")

        # Get some details about the matching businesses
        prices: list[float] = []
        negotiated_prices: list[float] = []
        matches_amenities: list[bool] = []
        for b in matching_businesses:
            order_price = sum(b.menu_features[item] for item in c.menu_features)
            prices.append(round(order_price, 2))
            negotiated_price = round(order_price * b.min_price_factor, 2)
            negotiated_prices.append(negotiated_price)
            amenity_match = all(
                b.amenity_features.get(amenity, False) for amenity in c.amenity_features
            )
            matches_amenities.append(amenity_match)

        if len(set(prices)) != len(prices):
            sys.stderr.write("Prices are not unique.\n")
            sys.exit(1)
        if len(set(negotiated_prices)) != len(negotiated_prices):
            sys.stderr.write("Negotiated prices are not unique.\n")
            sys.exit(1)
        print("  \U00002705 Prices and negotiated prices are unique.")

        print(f"      Posted Prices: {prices}")
        print(f"  Negotiated prices: {negotiated_prices}")
        print(f"  Matches amenities: {matches_amenities}")

        # Make sure a mix of matches and non-matches on amenities
        if all(matches_amenities) or not any(matches_amenities):
            sys.stderr.write(
                "All or none of the matching businesses meet the amenity requirements.\n"
            )
            sys.exit(1)

        # Get the index of the lowest posted price
        lowest_price_index = prices.index(min(prices))

        # Get the index of the lowest negotiated price that meets amenities
        optimal_index = -1
        for i in range(len(negotiated_prices)):
            if matches_amenities[i]:
                if (
                    optimal_index == -1
                    or negotiated_prices[i] < negotiated_prices[optimal_index]
                ):
                    optimal_index = i

        # Would the lowest price change the outcome?
        if not matches_amenities[lowest_price_index]:
            print(
                "  \U00002139 Ignoring negotiation, the lowest price DOES NOT meet amenities."
            )
            n_greedy_fails += 1
        else:
            print(
                "  \U00002139 Ignoring negotiation, the lowest price MEETS amenities."
            )
            if lowest_price_index != optimal_index:
                n_negotiation_changes_choice += 1
                print(
                    "      But the business with the lowest posted price is NOT the optimal choice when negotiating."
                )
            else:
                print(
                    "      And the business with the lowest posted price IS the optimal choice when negotiating."
                )
        print()

    print(f"{n_overlapping_orders} customers have partially overlapping orders.")
    print(
        f"{n_greedy_fails} customers would NOT get their amenity request if greedily selecting on price."
    )
    print(
        f"{n_negotiation_changes_choice} customers would change their choice when negotiating."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-f",
        "--features-dir",
        type=str,
        required=False,
        default=os.path.join(
            os.path.pardir, os.path.pardir, "data", "features", "mexican"
        ),
        help="Directory containing item and amenity features",
    )
    parser.add_argument(
        "data_dir",
        type=str,
        help="Folder containing the data to validate.",
    )

    args = parser.parse_args()
    main(args.features_dir, args.data_dir)
