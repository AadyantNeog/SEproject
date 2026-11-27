"""Pure FR-4 collection analytics and valid-timestamp period comparisons."""

from .periods import (
    PeriodComparison,
    PeriodMetricComparison,
    TimePeriod,
    UnavailableTrend,
    compare_periods,
    validate_non_overlapping_periods,
)
from .summaries import (
    ANALYTICS_VERSION,
    AnalysisConfig,
    AnalysisReport,
    CombinedPopulationSummary,
    DurationBandCount,
    LikesPopulationSummary,
    PlaylistPopulationSummary,
    RankedBucket,
    RuntimeStats,
    SubscriptionPopulationSummary,
    summarise_library,
)

__all__ = [
    "ANALYTICS_VERSION",
    "AnalysisConfig",
    "AnalysisReport",
    "CombinedPopulationSummary",
    "DurationBandCount",
    "LikesPopulationSummary",
    "PeriodComparison",
    "PeriodMetricComparison",
    "PlaylistPopulationSummary",
    "RankedBucket",
    "RuntimeStats",
    "SubscriptionPopulationSummary",
    "TimePeriod",
    "UnavailableTrend",
    "compare_periods",
    "summarise_library",
    "validate_non_overlapping_periods",
]
