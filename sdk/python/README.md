# UzAssets SDK · Python

Official Python SDK for the UzAssets Platform API.

## Install

```bash
pip install -e ./sdk/python      # local install
# or once published:
pip install uzassets-sdk
```

## Quickstart

```python
from uzassets_sdk import UzAssetsClient

with UzAssetsClient(
    base_url="https://platform.uz-assets.uz/api",
    token="<your_jwt_here>",
) as sdk:
    # 22 portfolio companies
    companies = sdk.companies.list()
    for c in companies:
        print(c["code"], c["name_short"])

    # Library MDM view — sector-filtered, with computed metrics
    library = sdk.library.list(sector="mining")
    for row in library["items"]:
        f = row["fields"]
        print(f"{row['name_short']:20s}  rev={f.get('revenue')}  ebitda={f.get('ebitda')}")

    # Latest credit ratings
    ratings = sdk.ratings.by_company("ngmk")
    print(ratings)
```

## Sync helpers

```python
# Write back to library — routes to finmodel / ratings / custom_data automatically
sdk.library.update_field(
    company_id="<uuid>",
    field_code="rating_fitch",
    value="BB+",
    reason="Updated after Fitch upgrade announcement"
)
```

## Refresh generated types

The SDK uses hand-written wrappers. If you want full type coverage:

```bash
cd sdk/python
pip install openapi-python-client
openapi-python-client generate --url http://localhost:8000/api-catalog/openapi.json
```

This produces `uzassets_sdk_client/` with full Pydantic models for every endpoint
in the platform. Use whichever style fits your project.

## Errors

All HTTP errors throw `UzAssetsApiError(status_code, message, body)`.
`401` should trigger your re-auth flow.
