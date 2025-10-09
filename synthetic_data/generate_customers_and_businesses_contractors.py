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


def _generate_business_name_and_description(
    menu: dict[str, float], competitor_names: list[str]
) -> tuple[str, str]:
    formatted_menu = "\n".join([f"- {item}" for item in menu.keys()])
    formatted_competitors = ""

    # Prepare a list of competitors if any, so that the LLM can avoid similar names
    if len(competitor_names) > 0:
        formatted_competitors = "IMPORTANT: The name MUST NOT be overly similar to any of the competitors and MUST NOT create confusion. For example if 'Cornerstone Builders' is a competitor, then DO NOT suggest 'Cornerstone Renovations' because it reuses the same base name. Or if the name is 'Nailed It Carpentry', then DO NOT suggest 'NailedIt Remodeling' because it is too similar.\n"
        formatted_competitors += "The competitors in the area are:\n\n"
        formatted_competitors += "\n".join([f"- {name}" for name in competitor_names])

    # Construct the prompt
    prompt = f"""
I am trying to populate a business name and a short description for a fictional contractor / local services business. The business offers the following services:

{formatted_menu}

Goal: Generate a clear, professional, and descriptive business name (avoid puns, jokes, whimsy, or overt cleverness). The name should communicate the business’s purpose, positioning, or service focus (for example: residential remodeling, neighborhood trades, specialty contractors, emergency repairs, or value-oriented general contracting), and be easy to remember and pronounce.

Please generate:
A business name that is straightforward and appropriate for a contractor/local services business. Do NOT use puns, playful wordplay, or intentionally humorous phrasing. Favor straightforward options such as "Riverside Contractors", "Oak Street Builders", or "Neighborhood Trades".
A short description of the business in 1–2 sentences. If the description mentions service categories or positioning, it must not contradict {formatted_menu} and should remain reasonably generic (do not list or repeat specific service item names). The description should communicate the target customers and the business’s service positioning (e.g., “residential remodeling focused on timely, code-compliant work”), but must not claim attributes (like "licensed" or "24/7") unless those attributes are explicitly supported by {formatted_menu} or {formatted_competitors}.

{formatted_competitors}

IMPORTANT:
The chosen name MUST NOT contradict the business's service list. For example, if the service list does not include electrical work, the name should not reference electrical services.
Do NOT use clever, punny, or humorous names (e.g., avoid names like "Nail It Right" or "Hammer Time"). Use straightforward, professional names.
Avoid overly specific claims in the name (e.g., "Licensed Only" or "24/7 Emergency") unless those attributes are explicitly present in {formatted_menu} or {formatted_competitors}.
The description must not repeat individual service line items verbatim from {formatted_menu}; it may reference categories (e.g., "home remodeling", "landscaping", "emergency repairs") only if those categories are consistent with {formatted_menu}.

Return a JSON object with the following fields and nothing else:
{{
"name": "The business name",
"description": "A short description of the business in 1-2 sentences."
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
    # Clean up the menu features to remove (type: ...) portion
    cleaned_menu_features = {}
    for item_name, price in menu_features.items():
        # Remove everything from '(type:' onwards
        if "(type:" in item_name:
            cleaned_name = item_name.split("(type:")[0].strip()
        else:
            cleaned_name = item_name
        cleaned_menu_features[cleaned_name] = price

    menu_items = json.dumps(dict.fromkeys(menu_features.keys(), 1), indent=2)
    amenity_items = "\n".join([f"- {item}" for item in amenity_features])

    prompt = f"""
Imagine a customer is contacting an assistant to hire a contractor or local service business to perform specific services.
The customer needs a contractor who can provide the following services (scope/quantities are noted):
{menu_items}

AND, that has the following amenities:
{amenity_items}

These requirements are essential, the customer will only consider a contractor that meets all of them. Once such a contractor is found, the customer intends to hire them and schedule the work as specified above.
Please generate a short-but-complete, polite request from the customer to the assistant that makes this intent clear.
Do NOT start with "Dear Assistant" or similar, begin directly with the request.
Be precise and use the exact service names, scopes/quantities, and amenity names as given above, and explicitly state the intention to hire/engage the contractor and to schedule/confirm the work.
Express the customer’s intention to hire and schedule the work in a natural, professional way, and vary the closing phrasing (do not always use the same sentence).

Output the request as a JSON object with exactly the following field:

{{
"request": "The customer request"
}}

Return only the JSON object and no other text.
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
