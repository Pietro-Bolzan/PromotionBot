from app.core.security import validate_api_key
from app.db.database import get_db
from sqlalchemy.orm import Session
from uuid import UUID

from app.models.promotions import Promotion

from fastapi import (
    APIRouter, 
    HTTPException, 
    status, 
    Depends, 
    Query
)

from app.repositories.promotion_repo import (
    PromotionRepository
)

from app.schemas.promotion_shema import (
    PromotionResponse, 
    PromotionProcessingResult,
    GeneratedCopyResponse,
    PromotionDeliveryResponse
)

from app.services.openai_service import (
    OpenAIService
)
from app.services.telegram_service import (
    TelegramService
)
from app.services.promotion_service import (
    AmazonService,
    PromotionService,
)
from app.services.promotion_delivery_service import (
    PromotionDeliveryService
)


router = APIRouter(prefix="/api/promotions", tags=["promotions"])


@router.post(
    "/run",
    response_model=PromotionProcessingResult,
    dependencies=[Depends(validate_api_key)]
) 
def run_promotions(
    db: Session = Depends(get_db)
):
    amazon_service = AmazonService()
    promotion_repository = PromotionRepository(db)
    promotion_service = PromotionService(
        amazon_service=amazon_service,
        promotion_repository=promotion_repository,
    )

    return promotion_service.collect_pending_promotions()

@router.post(
    "/{promotion_id}/generate-copy",
    response_model=GeneratedCopyResponse
)
def generate_promotion_copy(
    promotion_id: UUID,
    db: Session = Depends(get_db),
):
    promotion_repository = PromotionRepository(db)
    promotion = promotion_repository.get_by_id(promotion_id)

    if promotion is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Promotion not found",
        )

    openai_service = OpenAIService()
    message = openai_service.generate_sales_copy(promotion)
    
    promotion_repository.update_generated_message(
        promotion=promotion,
        generated_message=message,
    )
    return GeneratedCopyResponse(
        promotion_id=promotion.id,
        message=message,
    )


@router.get(
    "",
    response_model=list[PromotionResponse]
)
def list_promotions(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    promotion_repository = PromotionRepository(db)
    return promotion_repository.list_all(limit=limit, offset=offset)

@router.post(
    "/{promotion_id}/send-telegram", 
    response_model=PromotionDeliveryResponse,
    dependencies=[Depends(validate_api_key)],
)
def send_promotion_to_telegram(
    promotion_id: UUID,
    db: Session = Depends(get_db),
):
    promotion_repository = PromotionRepository(db)
    promotion = promotion_repository.get_by_id(promotion_id)

    if promotion is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Promotion not found",
        )

    delivery_service = PromotionDeliveryService(
        promotion_repository=promotion_repository,
        openai_service=OpenAIService(),
        telegram_service=TelegramService(),
    )

    delivered_promotion = delivery_service.deliver_to_telegram(promotion)

    return PromotionDeliveryResponse(
        promotion_id=delivered_promotion.id,
        status=delivered_promotion.status.value,
        message="Promotion sent to Telegram",
    )

