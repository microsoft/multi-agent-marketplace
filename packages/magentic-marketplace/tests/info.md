# Running tests

Run all:
```bash
uv run pytest tests
```

Individually
```bash
# Search
uv run pytest tests/protocol/test_search.py   

# Send 
uv run pytest tests/protocol/test_send_message.py 

# Fetch
uv run pytest tests/protocol/test_fetch_messages.py 
```