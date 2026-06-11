import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../back_mic/backend')))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '../../../back_mic/backend/.env'))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from ministerialize_router import router as ministerialize_router

app = FastAPI(title="testA Ministerialize API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ministerialize_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8030, reload=True)
