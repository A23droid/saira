from pydantic import BaseModel
from typing import Optional
from app.schemas.paper import PaperResponse

class TrendData(BaseModel):
    weeklyCitationDelta: int
    trendScore: float
    reason: str

class TrendingPaperResponse(BaseModel):
    paper: PaperResponse
    entry: TrendData
