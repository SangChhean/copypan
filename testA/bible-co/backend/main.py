import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../back_mic/backend")))

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "../../../back_mic/backend/.env"))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from bible_co_router import router as bible_co_router

app = FastAPI(title="testA BibleCo API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(bible_co_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8033)
