"""
Fetches ReSharper release versions and dates from JetBrains' public data service.

This is the same data the https://www.jetbrains.com/resharper/download/other/ page
renders client-side. Each entry is (version, date) where date is ISO yyyy-mm-dd.
"""

import requests
from datetime import date

DATA_URL = "https://data.services.jetbrains.com/products"
PRODUCT_CODE = "RSU"  # ReSharper Tools


def fetch_releases() -> list[dict]:
    """Fetches all ReSharper release entries (release, eap, rc)."""
    response = requests.get(
        DATA_URL,
        params={"code": PRODUCT_CODE},
        timeout=30,
    )
    response.raise_for_status()
    products = response.json()
    if not products:
        raise RuntimeError(f"No product returned for code {PRODUCT_CODE}")
    return products[0].get("releases", [])


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
