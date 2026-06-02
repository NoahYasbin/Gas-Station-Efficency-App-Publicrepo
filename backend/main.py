import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import recommend

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)

app = FastAPI(
    title="Gas Efficiency API",
    description=(
        "Finds the most cost-efficient gas station by factoring in real gas prices "
        "and actual driving distance — not just price per gallon."
    ),
    version="0.3.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

app.include_router(recommend.router, prefix="/api/v1", tags=["recommendations"])


@app.get("/health", tags=["meta"])
async def health():
    return {"status": "ok"}
