from band.config import get_settings
from langchain_core.tools import StructuredTool
from thenvoi.runtime.custom_tools import CustomToolDef
from band.tools import demo_app
from agents.log_analyst.agent_core.schema import FetchLogsInput, FetchMetricsInput, FetchChaosStatusInput, FetchHealthInput

def _featherless_configured() -> bool:
    key = get_settings().featherless_api_key
    return bool(key) and not key.startswith("fn-xxx") and key != "your-featherless-key"


def _make_langchain_tools() -> list[StructuredTool]:
    return [
        StructuredTool.from_function(
            func=demo_app.fetch_logs,
            name="fetch_logs",
            description="Fetch recent structured JSON logs from checkout-api",
        ),
        StructuredTool.from_function(
            func=demo_app.fetch_metrics,
            name="fetch_metrics",
            description="Fetch Prometheus metrics from checkout-api",
        ),
        StructuredTool.from_function(
            func=demo_app.fetch_chaos_status,
            name="fetch_chaos_status",
            description="Get active fault injection state",
        ),
        StructuredTool.from_function(
            func=demo_app.fetch_health,
            name="fetch_health",
            description="Get current health check response",
        ),
    ]


def _make_claude_tools() -> list[CustomToolDef]:
    return [
        (FetchLogsInput, lambda inp: demo_app.fetch_logs(limit=inp.limit, level=inp.level)),
        (FetchMetricsInput, lambda _: demo_app.fetch_metrics()),
        (FetchChaosStatusInput, lambda _: demo_app.fetch_chaos_status()),
        (FetchHealthInput, lambda _: demo_app.fetch_health()),
    ]
