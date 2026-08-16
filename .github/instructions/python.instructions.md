---
description: Python conventions for the FastAPI host
applyTo: "**/*.py"
---

# Python in edim-dde-api

- Keep middleware / request context / safe logging free of product agent logic.
- Lifespan configures planes from env; domain bootstrap registers agents.
- Docstrings: Business purpose on modules; HTTP contract on route handlers.
- Prefer small helpers next to routes for persist/projection rather than new packages unless reused widely.
