"""Adapters: the only layer that touches the outside world.

inbound/   drives the application: HTTP API, Telegram, MCP tool server, the LLM agent.
outbound/  is driven by it: Postgres, LLM providers, tracing.
"""
