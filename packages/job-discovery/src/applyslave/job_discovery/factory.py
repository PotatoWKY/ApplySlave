"""Build an aggregator from the default companies.yaml seed list."""

from __future__ import annotations

from importlib import resources
from typing import cast

import httpx
import yaml

from applyslave.job_discovery.aggregator import DiscoveryAggregator
from applyslave.job_discovery.sources.ashby import AshbySource
from applyslave.job_discovery.sources.base import ATSSource
from applyslave.job_discovery.sources.greenhouse import GreenhouseSource
from applyslave.job_discovery.sources.jsearch import JSearchSource
from applyslave.job_discovery.sources.lever import LeverSource
from applyslave.job_discovery.sources.workable import WorkableSource


def load_default_companies() -> dict[str, list[str]]:
    """Read the bundled companies.yaml, returns `{source_name: [slugs]}`."""
    resource = resources.files("applyslave.job_discovery").joinpath("companies.yaml")
    raw = yaml.safe_load(resource.read_text(encoding="utf-8")) or {}
    return cast(dict[str, list[str]], raw)


def build_default_aggregator(
    client: httpx.AsyncClient | None = None,
    companies: dict[str, list[str]] | None = None,
    jsearch_api_key: str | None = None,
) -> tuple[DiscoveryAggregator, list[ATSSource]]:
    """Construct an aggregator with the default ATS sources.

    Returns the aggregator plus the list of source instances so the caller can
    close their HTTP clients (if they want to share a single client, pass one).

    If ``jsearch_api_key`` is provided, a JSearchSource is added alongside the
    ATS sources for broader coverage (Google Jobs aggregation).
    """
    companies = companies or load_default_companies()
    sources: list[ATSSource] = []
    if companies.get("greenhouse"):
        sources.append(GreenhouseSource(companies=companies["greenhouse"], client=client))
    if companies.get("lever"):
        sources.append(LeverSource(companies=companies["lever"], client=client))
    if companies.get("ashby"):
        sources.append(AshbySource(companies=companies["ashby"], client=client))
    if companies.get("workable"):
        sources.append(WorkableSource(companies=companies["workable"], client=client))

    # JSearch is a search-engine source (not per-company). It satisfies the
    # same JobSource protocol so the aggregator treats it uniformly.
    jsearch_sources: list = []
    if jsearch_api_key:
        jsearch_sources.append(JSearchSource(api_key=jsearch_api_key, client=client))

    all_sources = sources + jsearch_sources  # type: ignore[operator]
    return DiscoveryAggregator(sources=all_sources), sources  # type: ignore[arg-type]
