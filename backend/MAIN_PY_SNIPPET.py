"""
Snippet for app/main.py — register Business Plan and KPI routers.

Add these two import lines AND the two include_router calls below to
your existing main.py. Order doesn't matter.
"""

# At the top, alongside other route imports:
from app.api.routes import business_plan as bp_routes
from app.api.routes import kpi as kpi_routes

# After `app = FastAPI(...)` block, alongside other include_router calls:
app.include_router(bp_routes.router)
app.include_router(kpi_routes.router)
