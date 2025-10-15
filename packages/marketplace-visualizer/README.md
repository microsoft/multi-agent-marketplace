# Marketplace Visualizer

Visualize the results in the marketplace!

## Quick Start

This visualizer runs against a database after an experiment has finished.

First, run an experiment to get a schema name:

```bash
cd multi-agent-marketplace
docker compose up -d

magentic-marketplace run data/mexican_3_9 --experiment-name myexperiment123
```

Then you can launch the visualizer:

```bash
magentic-marketplace ui myexperiment123
```

## Dev

To make changes you first need to install the frontend code then run the server in dev mode

```bash
cd marketplace-visualizer
uv sync
npm install
npm run build # builds output files
```

Then launch UI in dev mode

```bash
cd marketplace-visualizer
npm run dev
```

And also launch a backend server:

```bash
magentic-marketplace ui <schema-name>
```
