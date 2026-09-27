import os

import uvicorn
from app.core.config import settings

if __name__ == "__main__":
    port = int(os.getenv("PORT", settings.BACKEND_PORT))

    uvicorn.run(
        "app.main:app",
        host=settings.BACKEND_HOST if settings.APP_ENV == "development" else "0.0.0.0",
        port=port,
        reload=settings.APP_ENV == "development"
    )
