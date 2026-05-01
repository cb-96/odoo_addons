#!/usr/bin/env python3
"""Validate the managed integration OpenAPI contract files."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = REPO_ROOT / "openapi" / "integration_v1.yaml"
REQUIRED_PATHS = {
    "/integration/v1/contracts": {"get"},
    "/integration/v1/outbound/finance/events": {"get"},
    "/integration/v1/inbound/{contract_code}/deliveries": {"post"},
}
REQUIRED_SECURITY_SCHEMES = {
    "FederationPartnerCode",
    "FederationPartnerToken",
    "FederationPartnerBearer",
}

PUBLIC_FEEDS_SPEC_PATH = REPO_ROOT / "openapi" / "public_feeds_v1.yaml"
PUBLIC_FEEDS_REQUIRED_PATHS = {
    "/api/v1/tournaments/{slug}/feed": {"get"},
    "/tournaments/{slug}/schedule.ics": {"get"},
}


def _load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle)
    if not isinstance(loaded, dict):
        raise ValueError(
            f"{path.relative_to(REPO_ROOT)} must contain a top-level mapping."
        )
    return loaded


def _expect(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    failures: list[str] = []
    _expect(
        SPEC_PATH.exists(),
        f"Missing OpenAPI contract: {SPEC_PATH.relative_to(REPO_ROOT)}",
        failures,
    )
    if failures:
        print("\n".join(failures))
        return 1

    try:
        spec = _load_yaml(SPEC_PATH)
    except Exception as error:  # pragma: no cover - exercised through CLI use
        print(f"Unable to parse {SPEC_PATH.relative_to(REPO_ROOT)}: {error}")
        return 1

    _expect(
        str(spec.get("openapi", "")).startswith("3."),
        "OpenAPI version must be 3.x.",
        failures,
    )

    info = spec.get("info")
    _expect(isinstance(info, dict), "OpenAPI info section is required.", failures)
    if isinstance(info, dict):
        _expect(bool(info.get("title")), "OpenAPI info.title is required.", failures)
        _expect(
            bool(info.get("version")), "OpenAPI info.version is required.", failures
        )

    paths = spec.get("paths")
    _expect(isinstance(paths, dict), "OpenAPI paths section is required.", failures)
    if isinstance(paths, dict):
        for route, methods in REQUIRED_PATHS.items():
            _expect(route in paths, f"Missing required OpenAPI path: {route}", failures)
            route_entry = paths.get(route, {})
            if isinstance(route_entry, dict):
                for method in methods:
                    operation = route_entry.get(method)
                    _expect(
                        isinstance(operation, dict),
                        f"Missing {method.upper()} operation for {route}",
                        failures,
                    )
                    if isinstance(operation, dict):
                        _expect(
                            bool(operation.get("operationId")),
                            f"{method.upper()} {route} requires an operationId.",
                            failures,
                        )
                        _expect(
                            bool(operation.get("summary")),
                            f"{method.upper()} {route} requires a summary.",
                            failures,
                        )
                        responses = operation.get("responses")
                        _expect(
                            isinstance(responses, dict) and bool(responses),
                            f"{method.upper()} {route} requires responses.",
                            failures,
                        )

    components = spec.get("components")
    _expect(
        isinstance(components, dict),
        "OpenAPI components section is required.",
        failures,
    )
    if isinstance(components, dict):
        security_schemes = components.get("securitySchemes")
        _expect(
            isinstance(security_schemes, dict),
            "OpenAPI security schemes are required.",
            failures,
        )
        if isinstance(security_schemes, dict):
            missing_schemes = sorted(REQUIRED_SECURITY_SCHEMES - set(security_schemes))
            _expect(
                not missing_schemes,
                f"Missing required security schemes: {', '.join(missing_schemes)}",
                failures,
            )

    if failures:
        print("OpenAPI contract validation failed:\n")
        print("\n".join(f"- {failure}" for failure in failures))
        return 1

    print(f"OpenAPI contract validation passed for {SPEC_PATH.relative_to(REPO_ROOT)}")

    # ── public_feeds_v1.yaml ─────────────────────────────────────────────────
    public_failures: list[str] = []
    _expect(
        PUBLIC_FEEDS_SPEC_PATH.exists(),
        f"Missing OpenAPI contract: {PUBLIC_FEEDS_SPEC_PATH.relative_to(REPO_ROOT)}",
        public_failures,
    )
    if public_failures:
        print("\n".join(public_failures))
        return 1

    try:
        public_spec = _load_yaml(PUBLIC_FEEDS_SPEC_PATH)
    except Exception as error:  # pragma: no cover - exercised through CLI use
        print(
            f"Unable to parse {PUBLIC_FEEDS_SPEC_PATH.relative_to(REPO_ROOT)}: {error}"
        )
        return 1

    _expect(
        str(public_spec.get("openapi", "")).startswith("3."),
        "public_feeds_v1.yaml: OpenAPI version must be 3.x.",
        public_failures,
    )
    public_paths = public_spec.get("paths")
    _expect(
        isinstance(public_paths, dict),
        "public_feeds_v1.yaml: paths section is required.",
        public_failures,
    )
    if isinstance(public_paths, dict):
        for route, methods in PUBLIC_FEEDS_REQUIRED_PATHS.items():
            _expect(
                route in public_paths,
                f"public_feeds_v1.yaml: missing required path: {route}",
                public_failures,
            )
            route_entry = public_paths.get(route, {})
            if isinstance(route_entry, dict):
                for method in methods:
                    operation = route_entry.get(method)
                    _expect(
                        isinstance(operation, dict),
                        f"public_feeds_v1.yaml: missing {method.upper()} for {route}",
                        public_failures,
                    )
                    if isinstance(operation, dict):
                        _expect(
                            bool(operation.get("operationId")),
                            f"public_feeds_v1.yaml: {method.upper()} {route} requires operationId.",
                            public_failures,
                        )
                        _expect(
                            bool(operation.get("summary")),
                            f"public_feeds_v1.yaml: {method.upper()} {route} requires summary.",
                            public_failures,
                        )
                        _expect(
                            isinstance(operation.get("responses"), dict),
                            f"public_feeds_v1.yaml: {method.upper()} {route} requires responses.",
                            public_failures,
                        )

    if public_failures:
        print("OpenAPI public-feeds contract validation failed:\n")
        print("\n".join(f"- {f}" for f in public_failures))
        return 1

    print(
        f"OpenAPI contract validation passed for "
        f"{PUBLIC_FEEDS_SPEC_PATH.relative_to(REPO_ROOT)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
