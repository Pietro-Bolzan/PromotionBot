from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.error_handlers import UnhandledErrorMiddleware, register_error_handlers
from app.api.routers.health import router as health_router
from app.api.routers.promotion_router import router as promotions_router
from app.core.config import settings
from app.core.logging_config import configure_logging
from app.core.request_context import RequestIdMiddleware
from app.scheduler.jobs import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(settings.log_level, settings.log_format)
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    title=settings.app_name,
    lifespan=lifespan,
)
# The last one added runs first: RequestIdMiddleware wraps the error
# boundary, so even an unexpected 500 is logged and answered with the id.
app.add_middleware(UnhandledErrorMiddleware)
app.add_middleware(RequestIdMiddleware)
register_error_handlers(app)

app.include_router(health_router)
app.include_router(promotions_router)


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
