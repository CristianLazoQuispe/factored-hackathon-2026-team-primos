"""Application: the agent's skills as use cases (localize, investigate, protect, resolve, escalate).

Orchestrates domain rules and talks to the outside only through the adapters it is given.
May import `app.domain`; must not import `app.adapters` or frameworks.
"""
