"""FastAPI DI factory for WebhooksService (stateless)."""
from typing import Annotated

from fastapi import Depends

from app.services.webhooks_admin.service import WebhooksService


def get_webhooks_service() -> WebhooksService:
    return WebhooksService()


WebhooksServiceDep = Annotated[WebhooksService, Depends(get_webhooks_service)]
