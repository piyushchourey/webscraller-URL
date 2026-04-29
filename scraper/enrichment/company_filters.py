"""Configurable company exclusion filters for enrichment workflows."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value.strip())
    except ValueError:
        return default


def _env_csv(name: str) -> List[str]:
    value = os.getenv(name, "")
    return [item.strip() for item in value.split(",") if item and item.strip()]


def _parse_compact_number(raw: str) -> Optional[int]:
    text = (raw or "").strip().lower().replace(",", "")
    match = re.match(r"^(\d+(?:\.\d+)?)\s*([km]?)$", text)
    if not match:
        return None

    numeric = float(match.group(1))
    suffix = match.group(2)
    if suffix == "k":
        numeric *= 1000
    elif suffix == "m":
        numeric *= 1_000_000

    return int(numeric)


@dataclass
class HeadcountRange:
    min_value: Optional[int]
    max_value: Optional[int]
    raw_value: str

    def as_dict(self) -> Dict[str, Any]:
        return {
            "raw": self.raw_value,
            "min": self.min_value,
            "max": self.max_value,
        }


def parse_headcount_range(raw_value: Optional[str]) -> Optional[HeadcountRange]:
    """
    Parse common Smartlead headcount formats into numeric bounds.

    Handles examples such as:
    - "> 100K"
    - "<100k"
    - "0-25"
    - "less than 15"
    - "2000-5000"
    - "5000+"
    """
    raw = (raw_value or "").strip()
    if not raw:
        return None

    text = raw.lower().replace(",", "").strip()

    less_match = re.search(r"less\s+than\s+([\d\.]+\s*[km]?)", text)
    if less_match:
        number = _parse_compact_number(less_match.group(1))
        if number is None:
            return None
        return HeadcountRange(min_value=None, max_value=max(0, number - 1), raw_value=raw)

    greater_match = re.search(r"more\s+than\s+([\d\.]+\s*[km]?)", text)
    if greater_match:
        number = _parse_compact_number(greater_match.group(1))
        if number is None:
            return None
        return HeadcountRange(min_value=number + 1, max_value=None, raw_value=raw)

    lt_match = re.match(r"^<\s*([\d\.]+\s*[km]?)$", text)
    if lt_match:
        number = _parse_compact_number(lt_match.group(1))
        if number is None:
            return None
        return HeadcountRange(min_value=None, max_value=max(0, number - 1), raw_value=raw)

    gt_match = re.match(r"^>\s*([\d\.]+\s*[km]?)$", text)
    if gt_match:
        number = _parse_compact_number(gt_match.group(1))
        if number is None:
            return None
        return HeadcountRange(min_value=number + 1, max_value=None, raw_value=raw)

    plus_match = re.match(r"^([\d\.]+\s*[km]?)\+$", text)
    if plus_match:
        number = _parse_compact_number(plus_match.group(1))
        if number is None:
            return None
        return HeadcountRange(min_value=number, max_value=None, raw_value=raw)

    range_match = re.match(r"^([\d\.]+\s*[km]?)\s*[-–]\s*([\d\.]+\s*[km]?)$", text)
    if range_match:
        left = _parse_compact_number(range_match.group(1))
        right = _parse_compact_number(range_match.group(2))
        if left is None or right is None:
            return None
        return HeadcountRange(min_value=min(left, right), max_value=max(left, right), raw_value=raw)

    exact = _parse_compact_number(text)
    if exact is not None:
        return HeadcountRange(min_value=exact, max_value=exact, raw_value=raw)

    return None


@dataclass
class RuleMatch:
    rule_id: str
    reason: str


@dataclass
class FilterDecision:
    excluded: bool
    matches: List[RuleMatch]
    evaluated_fields: Dict[str, Any]

    @property
    def reasons(self) -> List[str]:
        return [match.reason for match in self.matches]

    @property
    def rule_ids(self) -> List[str]:
        return [match.rule_id for match in self.matches]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "excluded": self.excluded,
            "reasons": self.reasons,
            "rule_ids": self.rule_ids,
            "evaluated_fields": self.evaluated_fields,
        }


class BaseCompanyFilterRule:
    """Base class for exclusion rules."""

    rule_id: str
    enabled: bool

    def evaluate(self, context: Dict[str, Any]) -> Optional[RuleMatch]:
        raise NotImplementedError


class HeadcountGreaterThanRule(BaseCompanyFilterRule):
    def __init__(self, threshold: int, enabled: bool = True, reason_template: str = ""):
        self.threshold = threshold
        self.enabled = enabled
        self.rule_id = f"headcount_gt_{threshold}"
        self.reason_template = reason_template or "Headcount indicates more than {threshold} employees"

    def evaluate(self, context: Dict[str, Any]) -> Optional[RuleMatch]:
        if not self.enabled:
            return None
        headcount: Optional[HeadcountRange] = context.get("headcount_range")
        if not headcount:
            return None

        min_value = headcount.min_value
        max_value = headcount.max_value

        exceeds = False
        if min_value is not None and min_value > self.threshold:
            exceeds = True
        elif min_value is not None and max_value is not None and min_value >= self.threshold and max_value > self.threshold:
            exceeds = True

        if not exceeds:
            return None

        return RuleMatch(
            rule_id=self.rule_id,
            reason=self.reason_template.format(
                threshold=self.threshold,
                observed=headcount.raw_value,
            ),
        )


class HeadcountLessThanRule(BaseCompanyFilterRule):
    def __init__(self, threshold: int, enabled: bool = True, reason_template: str = ""):
        self.threshold = threshold
        self.enabled = enabled
        self.rule_id = f"headcount_lt_{threshold}"
        self.reason_template = reason_template or "Headcount indicates fewer than {threshold} employees"

    def evaluate(self, context: Dict[str, Any]) -> Optional[RuleMatch]:
        if not self.enabled:
            return None
        headcount: Optional[HeadcountRange] = context.get("headcount_range")
        if not headcount:
            return None

        max_value = headcount.max_value
        min_value = headcount.min_value

        below = False
        if max_value is not None and max_value < self.threshold:
            below = True
        elif min_value is not None and max_value is not None and max_value <= self.threshold and min_value < self.threshold:
            below = True

        if not below:
            return None

        return RuleMatch(
            rule_id=self.rule_id,
            reason=self.reason_template.format(
                threshold=self.threshold,
                observed=headcount.raw_value,
            ),
        )


class IndustryExclusionRule(BaseCompanyFilterRule):
    def __init__(self, excluded_keywords: List[str], enabled: bool = True):
        self.excluded_keywords = [item.strip().lower() for item in excluded_keywords if item and item.strip()]
        self.enabled = enabled
        self.rule_id = "industry_exclusion"

    def evaluate(self, context: Dict[str, Any]) -> Optional[RuleMatch]:
        if not self.enabled or not self.excluded_keywords:
            return None

        industry = str(context.get("industry") or "").strip().lower()
        if not industry:
            return None

        for keyword in self.excluded_keywords:
            if keyword in industry:
                return RuleMatch(
                    rule_id=self.rule_id,
                    reason=f"Industry '{industry}' matched excluded keyword '{keyword}'",
                )
        return None


class LocationExclusionRule(BaseCompanyFilterRule):
    def __init__(self, excluded_keywords: List[str], enabled: bool = True):
        self.excluded_keywords = [item.strip().lower() for item in excluded_keywords if item and item.strip()]
        self.enabled = enabled
        self.rule_id = "location_exclusion"

    def evaluate(self, context: Dict[str, Any]) -> Optional[RuleMatch]:
        if not self.enabled or not self.excluded_keywords:
            return None

        location = str(context.get("location") or "").strip().lower()
        if not location:
            return None

        for keyword in self.excluded_keywords:
            if keyword in location:
                return RuleMatch(
                    rule_id=self.rule_id,
                    reason=f"Location '{location}' matched excluded keyword '{keyword}'",
                )
        return None


class CompanyFilterEngine:
    """Evaluates configured exclusion rules for a company context."""

    def __init__(self, enabled: bool = True, rules: Optional[List[BaseCompanyFilterRule]] = None):
        self.enabled = enabled
        self.rules = rules or []

    def evaluate(self, context: Dict[str, Any]) -> FilterDecision:
        if not self.enabled:
            return FilterDecision(excluded=False, matches=[], evaluated_fields={"engine_enabled": False})

        matches: List[RuleMatch] = []
        for rule in self.rules:
            result = rule.evaluate(context)
            if result:
                matches.append(result)

        headcount_range: Optional[HeadcountRange] = context.get("headcount_range")
        evaluated_fields = {
            "engine_enabled": True,
            "headcount_raw": (headcount_range.raw_value if headcount_range else None),
            "headcount_min": (headcount_range.min_value if headcount_range else None),
            "headcount_max": (headcount_range.max_value if headcount_range else None),
            "industry": context.get("industry"),
            "location": context.get("location"),
        }

        return FilterDecision(excluded=bool(matches), matches=matches, evaluated_fields=evaluated_fields)


@dataclass
class CompanyFilterConfig:
    enabled: bool = True
    min_employees: int = 15
    max_employees: int = 2000
    industry_exclusions: List[str] = None
    location_exclusions: List[str] = None

    @classmethod
    def from_env(cls) -> "CompanyFilterConfig":
        return cls(
            enabled=_env_bool("ENRICHMENT_COMPANY_FILTER_ENABLED", True),
            min_employees=_env_int("ENRICHMENT_COMPANY_MIN_EMPLOYEES", 15),
            max_employees=_env_int("ENRICHMENT_COMPANY_MAX_EMPLOYEES", 2000),
            industry_exclusions=_env_csv("ENRICHMENT_EXCLUDED_INDUSTRIES"),
            location_exclusions=_env_csv("ENRICHMENT_EXCLUDED_LOCATIONS"),
        )


def build_filter_engine(config: Optional[CompanyFilterConfig] = None) -> CompanyFilterEngine:
    cfg = config or CompanyFilterConfig.from_env()
    rules: List[BaseCompanyFilterRule] = [
        HeadcountGreaterThanRule(
            threshold=cfg.max_employees,
            enabled=True,
            reason_template="Company excluded: headcount '{observed}' indicates more than {threshold} employees",
        ),
        HeadcountLessThanRule(
            threshold=cfg.min_employees,
            enabled=True,
            reason_template="Company excluded: headcount '{observed}' indicates fewer than {threshold} employees",
        ),
        IndustryExclusionRule(cfg.industry_exclusions or [], enabled=True),
        LocationExclusionRule(cfg.location_exclusions or [], enabled=True),
    ]
    return CompanyFilterEngine(enabled=cfg.enabled, rules=rules)


def extract_company_filter_context(
    contacts: List[Dict[str, Any]],
    company_location: Optional[str],
    company_industry: Optional[str],
) -> Dict[str, Any]:
    """Extract filter context from Smartlead contact payload + known company fields."""
    headcount_raw = ""
    inferred_industry = ""
    inferred_location = company_location or ""

    for contact in contacts:
        if not headcount_raw and contact.get("companyHeadCount"):
            headcount_raw = str(contact.get("companyHeadCount") or "").strip()
        if not inferred_industry and contact.get("industry"):
            inferred_industry = str(contact.get("industry") or "").strip()
        if not inferred_location and contact.get("country"):
            inferred_location = str(contact.get("country") or "").strip()

    headcount_range = parse_headcount_range(headcount_raw)

    return {
        "headcount_raw": headcount_raw,
        "headcount_range": headcount_range,
        "industry": (company_industry or inferred_industry or "").strip(),
        "location": (inferred_location or "").strip(),
    }
