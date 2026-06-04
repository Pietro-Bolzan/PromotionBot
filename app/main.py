from fastapi import FastAPI

from app.api.routers.health import router as health_router
from app.api.routers.promotion_router import router as promotions_router
from app.core.config import settings



app = FastAPI(title=settings.app_name)

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
        host="0.0.0.0",
        port=8000,
        reload=True,
    )