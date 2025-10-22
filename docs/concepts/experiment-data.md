# Experiment Data

Experiments require agent profile data in YAML format, organized into `businesses/` and `customers/` directories.

## Customer

```yaml
id: customer_0001
name: Customer 1
request: I want to buy...
menu_features:
  - Item_00: 0.00
  - Item_01: 0.00
amenity_features:
  - Amenity_03
```

**Fields:**

- `id` (string): Unique customer identifier
- `name` (string): Customer display name
- `request` (string): What the customer is looking for
- `menu_features` (list): Desired menu items with expected price
- `amenity_features` (list): Desired amenities

## Business

```yaml
id: business_0001
name: Business 1
description: Business 1
rating: 1.0
progenitor_customer: customer_0001
menu_features:
  Item_22: 1.0
  Item_21: 1.09
  Item_24: 0.99
amenity_features:
  Free Wifi: false
  Outdoor Seating: false
  Takes Reservations: false
  Offers Delivery: true
min_price_factor: 0.8
```

**Fields:**

- `id` (string): Unique business identifier
- `name` (string): Business display name
- `description` (string): Business description
- `rating` (float): Business rating (0-1 scale)
- `progenitor_customer` (string): Associated customer ID (used in data generation)
- `menu_features` (dict): Menu items with prices
- `amenity_features` (dict): Available amenities (boolean)
- `min_price_factor` (float): Minimum pricing multiplier

## Directory Structure

```
experiment_data/
├── businesses/
│   ├── business_0001.yaml
│   ├── business_0002.yaml
│   └── ...
└── customers/
    ├── customer_0001.yaml
    ├── customer_0002.yaml
    └── ...
```
