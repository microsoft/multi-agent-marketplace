# Marketplace Protocol Cookbook

This directory contains example marketplace protocols demonstrating how to build custom protocols for the magentic-marketplace framework.

## Available Examples

### Text-Only Protocol

A minimal marketplace protocol supporting only text messaging between agents.

**Path**: `text_only_protocol/`

**What it demonstrates**:
- Creating custom actions (SendTextMessage, CheckMessages)
- Implementing action handlers
- Writing database queries
- Building a complete protocol
- Testing protocols with unit and integration tests
- Running example agents

**Quick start**:
```bash
# Run tests
uv run pytest cookbook/text_only_protocol/tests/ -v

# Run example
uv run python cookbook/text_only_protocol/example/run_example.py
```

See [text_only_protocol/README.md](text_only_protocol/README.md) for full documentation.

## Creating Your Own Protocol

Each protocol example in this cookbook follows the same structure:

```
your_protocol/
├── README.md                 # Documentation and tutorial
├── messaging.py              # Message type definitions
├── actions.py                # Action definitions and response models
├── protocol.py               # Protocol implementation
├── handlers/                 # Action handler implementations
│   └── *.py
├── database/
│   └── queries.py            # Database query helpers
├── tests/
│   ├── conftest.py           # Test fixtures
│   └── test_*.py             # Unit tests
└── example/
    ├── agents.py             # Example agent implementations
    └── run_example.py        # Integration test runner
```

## Key Concepts

### Protocol Components

1. **Message Models**: Define the structure of data exchanged between agents
2. **Actions**: Define what agents can do (inherit from BaseAction)
3. **Handlers**: Implement business logic for each action
4. **Protocol Class**: Routes actions to handlers and defines available actions
5. **Database Queries**: Provide composable filters for data retrieval

### Testing Strategy

Each protocol example includes two types of tests:

1. **Unit Tests**: Test individual actions in isolation using pytest fixtures
2. **Integration Tests**: Run real agents communicating via the protocol

### Development Workflow

1. Define your message types
2. Create action models
3. Implement handlers
4. Build protocol class
5. Write tests
6. Create example agents
7. Document usage

## Resources

- Main documentation: See project README
- Platform code: `packages/magentic-marketplace/src/magentic_marketplace/platform/`
- Full marketplace implementation: `packages/magentic-marketplace/src/magentic_marketplace/marketplace/`
