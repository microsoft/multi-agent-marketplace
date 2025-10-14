"""Generate synthetic customers and businesses for the marketplace."""

import argparse
import json
import math
import os
import random
import sys

import yaml
from base import Business, Customer, ItemFeature
from utils import find_similar, is_similar, llm_json_query

MIN_DISTRACTOR_ITEMS_PER_BUSINESS = 10
MAX_DISTRACTOR_ITEMS_PER_BUSINESS = 15
MIN_DISTRACTOR_AMENITIES_PER_BUSINESS = 2
MAX_DISTRACTOR_AMENITIES_PER_BUSINESS = 4

BUSINESS_NAME_STYLE_TEMPLATES = {
    "classic": """
- El Cantina Mexicana
- La Fiesta Grande
""".strip(),
    "modern/trendy": """
- Urban Tacos
- The Salsa Spot
- Fresh Mex
""".strip(),
    "alliteration": """
- Taco Town
- Burrito Bros
- Avocado Alley
""".strip(),
    "clever/punny": """
- For the love of Cod
- Total Elclipse of the Tart
- Pita Pan
- Lord of the Fries

The food truck names from Bob's Burgers are a good example of the right level of cleverness.
""".strip(),
}


def _generate_business_name_and_description(
    menu: dict[str, float], competitor_names: list[str]
) -> tuple[str, str]:
    formatted_menu = "\n".join([f"- {item}" for item in menu.keys()])
    formatted_competitors = ""

    # Prepare a list of competitors if any, so that the LLM can avoid similar names
    if len(competitor_names) > 0:
        formatted_competitors = "IMPORTANT: The name MUST NOT be overly similar to any of the competitors and MUST NOT create confusion. For example if 'Nacho Ordinary Kitchen' is a competitor, then DO NOT suggest 'Nacho Average Eatery' because it reuses the same joke or pun. Or if the name is 'El Taco Loco', then DO NOT suggest 'Taco Madness' because it is too similar.\n"
        formatted_competitors += "The competitors in the area are:\n\n"
        formatted_competitors += "\n".join([f"- {name}" for name in competitor_names])

    # Pick a style for the business name
    style = random.choice(list(BUSINESS_NAME_STYLE_TEMPLATES.keys()))

    # Construct the prompt
    prompt = f"""
I am trying to populate a name and short description for a fictional Mexican or Tex-Mex restaurant.
The restaurant serves the following menu items:

{formatted_menu}

IMPORTANT: The chosen name MUST NOT contradict the restaurant's menu items. For example, if the menu does
not contain burritos, the name should not be "Burrito Brothers". Names that don't refer to menu items are
also fine (e.g., 'Sombrero & Spice')

Please generate a restaurant name. The name should be {style}, for example:
{BUSINESS_NAME_STYLE_TEMPLATES[style]}

{formatted_competitors}

Please also generate a short description of the restaurant in 1-2 sentences. If the description
mentions food, it must not contradict the menu items, and should be reasonably generic, not revealing
too much about the specific menu names.

Return a JSON object with the following fields:
{{
  "name": "The restaurant name",
  "description": "A short description of the restaurant in 1-2 sentences."
}}
""".strip()

    for i in range(5):
        try:
            data = llm_json_query(prompt, model="gpt-4.1")
            assert isinstance(data, dict)
            assert "name" in data and isinstance(data["name"], str)
            assert "description" in data and isinstance(data["description"], str)
            return data["name"], data["description"]
        except (json.JSONDecodeError, AssertionError):
            print(f"Warning: Failed to parse LLM response, retrying... ({i + 1}/5)")
            continue
    raise RuntimeError(
        "Error: Failed to generate business name and description after 5 attempts"
    )


def _generate_request(
    menu_features: dict[str, float], amenity_features: list[str]
) -> str:
    """Generate a customer request string given the menu and amenity features."""
    menu_items = json.dumps(dict.fromkeys(menu_features.keys(), 1), indent=2)
    amenity_items = "\n".join([f"- {item}" for item in amenity_features])

    prompt = f"""
Imagine that a customer is contacting a concierge or assistant to place a specific order from a business that meets their needs.
The customer needs a business that serves the following menu items (order quantities are noted):

{menu_items}

AND, that has the following amenities:

{amenity_items}

These needs are very important to the customer, and they will not consider a business that does not meet all of them.
Upon finding such a business, it is the customer's intention to place an order, as reflected above.
Please genertate a short-but-complete and polite request from the customer to the concierge or assistant.

You DO NOT need to start with 'Dear concierge' or similar, just start with the request itself.

Be sure to be precise and use the exact names and quantities of the menu items and amenities as given above,
and express the intention to purchase the items.

Output the request as JSON object with the following field:

{{
  "request": "The customer request"
}}
""".strip()

    for i in range(5):
        try:
            data = llm_json_query(prompt, model="gpt-4o")
            assert isinstance(data, dict)
            assert "request" in data and isinstance(data["request"], str)
            return data["request"]
        except (json.JSONDecodeError, AssertionError):
            print(f"Warning: Failed to parse LLM response, retrying... ({i + 1}/5)")
            continue
    raise RuntimeError("Error: Failed to generate customer request after 5 attempts")


def main(features_dir: str, n_customers: int, output_dir: str) -> None:
    """Generate synthetic customers and businesses."""
    items: list[ItemFeature] = []
    amenities: list[str] = []
    people: list[str] = []

    # Load all the features_dir data
    ######################################
    with open(os.path.join(features_dir, "items.yaml")) as f:
        for i in yaml.safe_load(f):
            items.append(ItemFeature(**i))

    with open(os.path.join(features_dir, "amenities.yaml")) as f:
        for a in yaml.safe_load(f):
            assert isinstance(a, str)
            amenities.append(a)

    with open(os.path.join(features_dir, "people.yaml")) as f:
        for p in yaml.safe_load(f):
            assert isinstance(p, str)
            people.append(p)

    if len(people) < n_customers:
        sys.stderr.write(
            f"Error: Not enough people to generate {n_customers} customers. Need at least {n_customers} people.\n"
        )
        sys.exit(1)

    # Validate the item and amenity names
    #####################################
    overlap = find_similar([i.name for i in items])
    if overlap is not None:
        sys.stderr.write(
            f"Error: Item names '{overlap[0]}' and '{overlap[1]}' are substrings of each other\n"
        )
        sys.exit(1)

    overlap = find_similar(amenities)
    if overlap is not None:
        sys.stderr.write(
            f"Error: Amenity names '{overlap[0]}' and '{overlap[1]}' are substrings of each other\n"
        )
        sys.exit(1)

    overlap = find_similar(people)
    if overlap is not None:
        sys.stderr.write(
            f"Error: Person names '{overlap[0]}' and '{overlap[1]}' are substrings of each other\n"
        )
        sys.exit(1)

    # Split the items into orders and distractors
    #################################################################

    # Randomize everything
    random.shuffle(items)
    random.shuffle(amenities)
    random.shuffle(people)

    orders: list[list[ItemFeature]] = []

    # Determine the set set for each category of orders
    set_size = math.ceil(n_customers / 3.0)
    try:
        # Single items
        idx = 0
        for _ in range(set_size):
            orders.append([items[idx]])
            idx += 1

        # Pairs of items
        for _ in range(set_size):
            orders.append([items[idx], items[idx + 1]])
            random.shuffle(orders[-1])
            idx += random.choice([1, 2])
        idx += 1  # Clear the window

        # Triples of items
        for _ in range(set_size):
            orders.append([items[idx], items[idx + 1], items[idx + 2]])
            random.shuffle(orders[-1])
            idx += random.choice([1, 2, 3])
        idx += 2  # Clear the window

        # The remaining items are distractors
        distractor_items = items[idx:]

    except IndexError:
        sys.stderr.write(
            f"Error: Not enough items to generate {n_customers} customers.\n"
        )
        sys.exit(1)

    # Truncate any remaining orders and shuffle
    assert len(orders) >= n_customers
    orders = orders[:n_customers]
    random.shuffle(orders)

    # Validate that no order is a subset of another
    for i in range(len(orders)):
        for j in range(len(orders)):
            if i != j and all(k in orders[j] for k in orders[i]):
                sys.stderr.write(
                    f"Error: Order {orders[i]} is a subset of order {orders[j]}, please fix the item features.\n"
                )
                sys.exit(1)

    # Make sure we have enough distractor items
    if len(distractor_items) < MAX_DISTRACTOR_ITEMS_PER_BUSINESS:
        sys.stderr.write(
            f"Error: Not enough distractor items to generate businesses. Need at least {MAX_DISTRACTOR_ITEMS_PER_BUSINESS} distractor items.\n"
        )
        sys.exit(1)

    print(f"We have {len(distractor_items)} distractor items.")

    # Generate the customers
    ########################
    customers: list[Customer] = []
    for i in range(0, n_customers):
        # Convert the order to a menu features dict
        menu_features: dict[str, float] = {}
        for item in orders[i]:
            menu_features[item.name] = item.mean_price

        # Randonly sample on desired amenity
        amenity_features = random.sample(amenities, random.randint(1, 2))

        # Generate the customer
        customer = Customer(
            id=f"customer_{len(customers) + 1:04}",
            name=people[i],
            request=_generate_request(menu_features, amenity_features),
            menu_features=menu_features,
            amenity_features=amenity_features,
        )
        customers.append(customer)

        # Write the customer to a file
        os.makedirs(os.path.join(output_dir, "customers"), exist_ok=True)
        fname = os.path.join(output_dir, "customers", f"{customer.id}.yaml")
        print(f"Writing {fname}")
        with open(fname, "w") as f:
            f.write(yaml.safe_dump(customer.model_dump(), sort_keys=False))

    # Generate the businesses
    #########################
    businesses: list[Business] = []
    for customer in customers:
        # Generate 3 menus, each serving the customer, but with different prices and distractor items
        menus: list[dict[str, float]] = []
        for _ in range(3):
            menu: dict[str, float] = {}

            # Add the required items
            for item_name in customer.menu_features:
                item = next(i for i in items if i.name == item_name)
                price = max(0.01, random.gauss(item.mean_price, item.price_stddev))
                menu[item_name] = round(price, 2)

            # Add some distractor items
            n_distractor_items = random.randint(
                MIN_DISTRACTOR_ITEMS_PER_BUSINESS, MAX_DISTRACTOR_ITEMS_PER_BUSINESS
            )
            distractor_item_choices = random.sample(
                distractor_items, n_distractor_items
            )
            for item in distractor_item_choices:
                price = max(0.01, random.gauss(item.mean_price, item.price_stddev))
                menu[item.name] = round(price, 2)

            menus.append(menu)

        # Generate 3 amenity sets, each with different distractor amenities
        amenity_sets: list[dict[str, bool]] = []
        for _ in range(3):
            amenity_set: dict[str, bool] = {}

            # Generate an empty set of amenities
            for a in amenities:
                amenity_set[a] = False

            # Turn on some distractor amenities
            n_distractor_amenities = random.randint(
                MIN_DISTRACTOR_AMENITIES_PER_BUSINESS,
                MAX_DISTRACTOR_AMENITIES_PER_BUSINESS,
            )
            for a in random.sample(amenities, n_distractor_amenities):
                amenity_set[a] = True

            amenity_sets.append(amenity_set)

        # Add the required amenities to all of the sets
        for a in customer.amenity_features:
            for s in amenity_sets:
                s[a] = True

        # Force one of the businesses to NOT have one of the required amenities
        amenity_sets[-1][customer.amenity_features[0]] = False

        # Generate the businesses
        for i in range(len(menus)):
            # Break the insertion order of the menus dict
            _menu_items = list(menus[i].items())
            random.shuffle(_menu_items)
            menus[i] = dict(_menu_items)

            # Generate a business name and description
            all_names = [b.name for b in businesses]
            name, description = _generate_business_name_and_description(
                menus[i], all_names
            )

            # Make sure there aren't any name collisions with existing businesses
            overlaps = [b.name for b in businesses if is_similar(b.name, name)]
            while len(overlaps) > 0:
                print(
                    f"Warning: Business name '{name}' collides with existing name '{overlaps[0]}', regenerating..."
                )
                name, description = _generate_business_name_and_description(
                    menus[i], all_names
                )
                overlaps = [b.name for b in businesses if is_similar(b.name, name)]

            # Create the business
            business = Business(
                id=f"business_{len(businesses) + 1:04}",
                name=name,
                description=description,
                rating=1.0,
                progenitor_customer=customer.id,
                menu_features=menus[i],
                amenity_features=amenity_sets[i],
                min_price_factor=round(random.uniform(0.6, 0.95), 2),
            )
            businesses.append(business)

            # Write the business to a file
            os.makedirs(os.path.join(output_dir, "businesses"), exist_ok=True)
            fname = os.path.join(output_dir, "businesses", f"{business.id}.yaml")
            print(f"Writing {fname}")
            with open(fname, "w") as f:
                f.write(yaml.safe_dump(business.model_dump(), sort_keys=False))


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
        "-c",
        "--customers",
        type=int,
        required=False,
        default=10,
        help="Number of customers to generate",
        metavar="N_CUSTOMERS",
    )
    parser.add_argument(
        "output_dir",
        type=str,
        help="Output directory to save generated customer data",
    )

    args = parser.parse_args()
    main(args.features_dir, args.customers, args.output_dir)
