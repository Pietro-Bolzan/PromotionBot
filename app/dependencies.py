"""Where the application assembles its parts.

Routes receive their collaborators from these providers instead of building
them, so tests can replace any of them through app.dependency_overrides. The
scheduler, which runs outside any request, reuses the same cached clients.
"""

from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.repositories.promotion_repo import PromotionRepository
from app.services.amazon_service import AmazonService
from app.services.openai_service import OpenAIService
from app.services.promotion_delivery_service import PromotionDeliveryService
from app.services.promotion_service import PromotionService
from app.services.telegram_service import TelegramService


def get_promotion_repository(
    db: Annotated[Session, Depends(get_db)],
) -> PromotionRepository:
    return PromotionRepository(db)


# Built once per process. The OpenAI client keeps a connection pool that every
# request can share; the others hold no per-request state.
@lru_cache
def get_openai_service() -> OpenAIService:
    return OpenAIService()


@lru_cache
def get_telegram_service() -> TelegramService:
    return TelegramService()


@lru_cache
def get_amazon_service() -> AmazonService:
    return AmazonService()


PromotionRepositoryDep = Annotated[
    PromotionRepository, Depends(get_promotion_repository)
]
OpenAIServiceDep = Annotated[OpenAIService, Depends(get_openai_service)]
TelegramServiceDep = Annotated[TelegramService, Depends(get_telegram_service)]
AmazonServiceDep = Annotated[AmazonService, Depends(get_amazon_service)]


def get_promotion_service(
    amazon_service: AmazonServiceDep,
    promotion_repository: PromotionRepositoryDep,
) -> PromotionService:
    return PromotionService(
        amazon_service=amazon_service,
        promotion_repository=promotion_repository,
    )


def get_delivery_service(
    promotion_repository: PromotionRepositoryDep,
    openai_service: OpenAIServiceDep,
    telegram_service: TelegramServiceDep,
) -> PromotionDeliveryService:
    return PromotionDeliveryService(
        promotion_repository=promotion_repository,
        openai_service=openai_service,
        telegram_service=telegram_service,
    )


PromotionServiceDep = Annotated[PromotionService, Depends(get_promotion_service)]
DeliveryServiceDep = Annotated[PromotionDeliveryService, Depends(get_delivery_service)]
