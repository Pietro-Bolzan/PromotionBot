from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.security import validate_api_key
from app.dependencies import (
    DeliveryServiceDep,
    OpenAIServiceDep,
    PromotionRepositoryDep,
    PromotionServiceDep,
)
from app.models.promotions import Promotion
from app.repositories.promotion_repo import PromotionRepository
from app.schemas.error_schema import ErrorResponse
from app.schemas.promotion_schema import (
    GeneratedCopyResponse,
    PendingDeliveryResponse,
    PromotionDeliveryResponse,
    PromotionProcessingResult,
    PromotionResponse,
)


def _errors(*status_codes: int) -> dict:
    """Document the error body for these statuses in the OpenAPI schema."""
    return {status_code: {"model": ErrorResponse} for status_code in status_codes}


# Authentication is declared on the router, so every route here is protected by
# default -- including routes added later. Exposing something publicly requires
# deliberately moving it out of this router.
router = APIRouter(
    prefix="/api/promotions",
    tags=["promotions"],
    dependencies=[Depends(validate_api_key)],
    responses=_errors(401, 422, 500),
)


def _get_promotion_or_404(
    promotion_id: UUID, promotion_repository: PromotionRepository
) -> Promotion:
    promotion = promotion_repository.get_by_id(promotion_id)

    if promotion is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Promotion not found",
        )

    return promotion


@router.post("/run", response_model=PromotionProcessingResult)
def run_promotions(promotion_service: PromotionServiceDep):
    return promotion_service.collect_pending_promotions()


@router.post(
    "/{promotion_id}/generate-copy",
    response_model=GeneratedCopyResponse,
    responses=_errors(404),
)
def generate_promotion_copy(
    promotion_id: UUID,
    promotion_repository: PromotionRepositoryDep,
    openai_service: OpenAIServiceDep,
):
    promotion = _get_promotion_or_404(promotion_id, promotion_repository)
    message = openai_service.generate_sales_copy(promotion)

    promotion_repository.update_generated_message(
        promotion=promotion,
        generated_message=message,
    )
    return GeneratedCopyResponse(
        promotion_id=promotion.id,
        message=message,
    )


@router.get("", response_model=list[PromotionResponse])
def list_promotions(
    promotion_repository: PromotionRepositoryDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return promotion_repository.list_all(limit=limit, offset=offset)


@router.post(
    "/{promotion_id}/send-telegram",
    response_model=PromotionDeliveryResponse,
    responses=_errors(404, 409, 502, 503),
)
def send_promotion_to_telegram(
    promotion_id: UUID,
    promotion_repository: PromotionRepositoryDep,
    delivery_service: DeliveryServiceDep,
):
    # Both dependencies share one repository (FastAPI caches it per request),
    # so the promotion loaded here belongs to the session that delivers it.
    promotion = _get_promotion_or_404(promotion_id, promotion_repository)
    delivered_promotion = delivery_service.deliver_to_telegram(promotion)

    return PromotionDeliveryResponse(
        promotion_id=delivered_promotion.id,
        status=delivered_promotion.status.value,
        message="Promotion sent to Telegram",
    )


@router.post(
    "/send-pending-telegram",
    response_model=PendingDeliveryResponse,
    responses=_errors(409, 502, 503),
)
def send_pending_promotions_to_telegram(
    delivery_service: DeliveryServiceDep,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
):
    return delivery_service.deliver_pending_to_telegram(limit=limit)
