# Magentic Marketplace

A Python SDK for running generative simulations of agentic markets. Configure business and customer agents that transact, then run simulations to evaluate market welfare and agent behavior.

## What is a Marketplace Simulation?

Imagine a food delivery marketplace where:
- **Customer agents** search for restaurants that match their preferences (menu items, price, amenities)
- **Business agents** respond to customer queries and adjust their offerings
- The marketplace coordinates multi-agent communication to match customers with businesses
- You can analyze outcomes like customer satisfaction, pricing efficiency, and market dynamics

## Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/microsoft/multi-agent-marketplace.git
cd multi-agent-marketplace

# Install dependencies with uv (https://docs.astral.sh/uv/)
uv sync --all-extras
source .venv/bin/activate

# Configure API keys for LLM providers
cp sample.env .env
# Edit .env with your API keys

# Start the database server
docker compose up -d
```

### Run a Simulation

```bash
# Run a marketplace experiment with Mexican restaurants
magentic-marketplace experiment data/mexican_3_9

# Analyze the results
magentic-marketplace analytics data/mexican_3_9
```

## What Gets Simulated?

In a marketplace experiment, you define:

1. **Businesses** (YAML files) - Each with:
   - Menu items and prices
   - Amenities (parking, wifi, outdoor seating, etc.)
   - Initial rating

2. **Customers** (YAML files) - Each with:
   - Desired menu items and price preferences
   - Required amenities
   - A natural language request

The simulation runs with AI agents representing each customer and business, using LLMs to:
- Search for matching businesses
- Communicate about offerings
- Place orders
- All interactions are logged for analysis

### Example Data

**Customer** (`customer_0001.yaml`):
```yaml
id: customer_0001
name: Susan Young
request: Could you find a restaurant with Pineapple Jalapeno Agua Fresca 
  and Savory Pumpkin Empanadas with outdoor seating?
menu_features:
  Pineapple Jalapeno Agua Fresca: 3.99
  Savory Pumpkin Empanadas: 9.49
amenity_features:
  - Outdoor Seating
```

**Business** (`business_0001.yaml`):
```yaml
id: business_0001
name: Poblano Palate
description: Bold and vibrant Mexican and Tex-Mex flavors
menu_features:
  Pineapple Jalapeno Agua Fresca: 2.73
  Savory Pumpkin Empanadas: 10.78
  # ... more items
amenity_features:
  Outdoor Seating: true
  Live Music: true
  # ... more amenities
```

## CLI Reference

### Run an Experiment

```bash
magentic-marketplace experiment DATA_DIR [OPTIONS]
```

**Arguments:**
- `DATA_DIR` - Directory containing `businesses/` and `customers/` subdirectories with YAML files

**Options:**
- `--experiment-name NAME` - Name for this experiment (used as database schema)
- `--search-algorithm TYPE` - Search algorithm for customers (default: `simple`)
- `--postgres-host HOST` - PostgreSQL host (default: `localhost`)
- `--postgres-port PORT` - PostgreSQL port (default: `5432`)
- `--env-file PATH` - Path to `.env` file (default: `.env`)
- `--log-level LEVEL` - Logging level (default: `INFO`)

**Example:**
```bash
magentic-marketplace experiment data/mexican_3_9 \
  --experiment-name my_experiment \
  --log-level DEBUG
```

### Analyze Results

```bash
magentic-marketplace analytics DATA_DIR [OPTIONS]
```

Generates analytics from the experiment data:
- Customer satisfaction metrics
- Transaction success rates
- Pricing analysis
- Market efficiency metrics

## Data Structure

Your experiment directory should follow this structure:

```
data/my_experiment/
├── businesses/
│   ├── business_0001.yaml
│   ├── business_0002.yaml
│   └── ...
└── customers/
    ├── customer_0001.yaml
    ├── customer_0002.yaml
    └── ...
```

See `data/mexican_3_9/` for a complete working example.

## Key Features

- **AI-Powered Agents**: Customer and business agents use LLMs to make decisions
- **PostgreSQL Storage**: All interactions logged to database for analysis
- **Configurable**: Define markets with simple YAML files
- **Analytics Built-in**: Analyze market outcomes, agent behavior, and efficiency

## Advanced Usage

For developers who want to create custom marketplace protocols and agents, see the [Developer Guide](DEV.md).

## Architecture

The marketplace uses a clean, layered architecture:
- **Agents** interact through a client API (no direct server/database access)
- **Protocol** contains business logic for the marketplace
- **Server** orchestrates agent communication
- **Database** provides persistent storage and queryable history