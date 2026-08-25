"""
Fetches release versions and dates from JetBrains' public data service.

This is the same data the https://www.jetbrains.com/resharper/download/other/ page
renders client-side. Each entry is (version, date) where date is ISO yyyy-mm-dd.

Defaults to ReSharper (RSU); pass another product code to build a calendar for a different
product (e.g. IIU for IntelliJ IDEA Ultimate, which IJPL/JBR ship on).
"""

import requests
from datetime import date

DATA_URL = "https://data.services.jetbrains.com/products"
PRODUCT_CODE = "RSU"  # ReSharper Tools


def fetch_releases(product_code: str = PRODUCT_CODE) -> list[dict]:
    """Fetches all release entries (release, eap, rc) for a product code."""
    response = requests.get(
        DATA_URL,
        params={"code": product_code},
        timeout=30,
    )
    response.raise_for_status()
    products = response.json()
    if not products:
        raise RuntimeError(f"No product returned for code {product_code}")
    return products[0].get("releases", [])


GA_TYPE = "release"


def get_release_calendar(product_code: str = PRODUCT_CODE) -> dict[str, date]:
    """{version: date}, with the GA entry winning when a version appears more than once.

    RSU gives every build its own version string ("2025.3 EAP 4"), so this is just a dict of
    the pairs. IIU instead repeats one version string across GA, RC and every EAP — twelve rows
    for "2025.1" — so without GA precedence the earliest EAP date would win and every interval
    measured against the calendar would be inflated by weeks.
    """
    calendar: dict[str, date] = {}
    ga_versions: set[str] = set()
    for r in fetch_releases(product_code):
        version, raw_date = r.get("version"), r.get("date")
        if not version or not raw_date:
            continue
        is_ga = r.get("type") == GA_TYPE
        if version in ga_versions and not is_ga:
            continue                      # never let a pre-release overwrite a shipped date
        calendar[version] = date.fromisoformat(raw_date)
        if is_ga:
            ga_versions.add(version)
    return calendar


def get_version_dates() -> list[tuple[str, date]]:
    """Returns [(version, release_date), ...] sorted from newest to oldest."""
    pairs = []
    for r in fetch_releases():
        version = r.get("version")
        raw_date = r.get("date")
        if not version or not raw_date:
            continue
        pairs.append((version, date.fromisoformat(raw_date)))
    pairs.sort(key=lambda p: p[1], reverse=True)
    return pairs


def main() -> None:
    pairs = get_version_dates()
    print(f"Found {len(pairs)} ReSharper releases\n")
    for version, released in pairs:
        print(f"{released.isoformat()}  {version}")


if __name__ == "__main__":
    main()
