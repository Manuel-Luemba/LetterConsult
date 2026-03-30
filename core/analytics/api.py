from ninja import Router
from .services.stats_service import StatsService
from datetime import date
from typing import Optional

router = Router(tags=["Analytics"])

@router.get("/dashboard-stats")
def get_stats(request, start_date: Optional[date] = None, end_date: Optional[date] = None):
    return StatsService.get_dashboard_stats(start_date, end_date)
