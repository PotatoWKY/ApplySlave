"""Job discovery via ATS public APIs."""

from applyslave.job_discovery.aggregator import DiscoveryAggregator
from applyslave.job_discovery.factory import build_default_aggregator, load_default_companies
from applyslave.job_discovery.sources.ashby import AshbySource
from applyslave.job_discovery.sources.base import ATSSource, apply_query_filters
from applyslave.job_discovery.sources.greenhouse import GreenhouseSource
from applyslave.job_discovery.sources.lever import LeverSource
from applyslave.job_discovery.sources.workable import WorkableSource

__all__ = [
    "ATSSource",
    "AshbySource",
    "DiscoveryAggregator",
    "GreenhouseSource",
    "LeverSource",
    "WorkableSource",
    "apply_query_filters",
    "build_default_aggregator",
    "load_default_companies",
]
