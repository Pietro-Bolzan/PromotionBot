from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.api.routers.health import router as health_router
from app.api.routers.promotion_router import router as promotions_router
from app.core.config import settings
from app.scheduler.jobs import start_scheduler, stop_scheduler
from app.services.promotion_delivery_service import (
    DeliveryInProgressError,
    PromotionAlreadySentError,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    title=settings.app_name,
    lifespan=lifespan,
)

app.include_router(health_router)
app.include_router(promotions_router)


@app.exception_handler(DeliveryInProgressError)
async def delivery_in_progress(request: Request, error: DeliveryInProgressError):
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"detail": "Another delivery is in progress; try again shortly"},
    )


@app.exception_handler(PromotionAlreadySentError)
async def promotion_already_sent(request: Request, error: PromotionAlreadySentError):
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"detail": "Promotion was already sent"},
    )


@app.get("/")
def root():
    return {
        "message": "Amazon Bot API",
        "docs": "/docs",
        "health": "/health",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
    )
