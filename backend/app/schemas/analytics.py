from pydantic import BaseModel
from typing import List

class MonthlyRead(BaseModel):
    month: str
    count: int

class TopicCount(BaseModel):
    tag: str
    count: int

class WeeklyGoal(BaseModel):
    completed: int
    target: int

class AnalyticsResponse(BaseModel):
    totalPapersSaved: int
    totalNotes: int
    totalReviews: int
    totalChatQuestions: int
    currentStreakDays: int
    weeklyGoal: WeeklyGoal
    papersReadByMonth: List[MonthlyRead]
    topicBreakdown: List[TopicCount]
