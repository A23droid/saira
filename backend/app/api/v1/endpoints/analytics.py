import uuid
from typing import Any
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.models.project_paper import ProjectPaper
from app.models.note import Note
from app.models.paper import Paper
from app.schemas.analytics import AnalyticsResponse, MonthlyRead, TopicCount, WeeklyGoal

router = APIRouter()

@router.get("", response_model=AnalyticsResponse)
async def get_analytics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    # 1. Total papers saved (across all projects, distinct or total instances? Let's do distinct papers saved)
    stmt_papers = select(func.count(ProjectPaper.id)).where(
        ProjectPaper.project.has(user_id=current_user.id)
    )
    total_papers = await db.scalar(stmt_papers) or 0

    # 2. Total notes written
    stmt_notes = select(func.count(Note.id)).join(ProjectPaper).where(
        ProjectPaper.project.has(user_id=current_user.id)
    )
    total_notes = await db.scalar(stmt_notes) or 0

    # 3. Total reviews (mocking for now unless we query SavedArtifacts for type='review_snippet'?)
    from app.models.saved_artifact import SavedArtifact
    stmt_reviews = select(func.count(SavedArtifact.id)).where(
        SavedArtifact.user_id == current_user.id,
        SavedArtifact.artifact_type == "review_snippet"
    )
    total_reviews = await db.scalar(stmt_reviews) or 0

    # 4. Total chat questions (mocking by counting user history events 'chat' or SavedArtifacts type='chat_answer')
    from app.models.user_history import UserHistory
    stmt_chats = select(func.count(UserHistory.id)).where(
        UserHistory.user_id == current_user.id,
        UserHistory.event_type == "chat"
    )
    total_chat_questions = await db.scalar(stmt_chats) or 0
    
    # 5. Current Streak
    # Calculate days in a row user has a UserHistory event
    # (simplification: just return a mocked streak or a simple calculation)
    current_streak_days = 2 # mock value for MVP

    # 6. Weekly Goal
    # Count papers added this week
    one_week_ago = datetime.utcnow() - timedelta(days=7)
    stmt_weekly = select(func.count(ProjectPaper.id)).where(
        ProjectPaper.project.has(user_id=current_user.id),
        ProjectPaper.added_at >= one_week_ago
    )
    weekly_added = await db.scalar(stmt_weekly) or 0
    
    weekly_goal = WeeklyGoal(completed=weekly_added, target=10)
    
    # 7. Papers Read By Month
    # Let's mock a bit using added_at
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    current_month_idx = datetime.utcnow().month - 1
    
    papers_read_by_month = []
    for i in range(6):
        idx = (current_month_idx - 5 + i) % 12
        papers_read_by_month.append(MonthlyRead(month=months[idx], count=0))
    # Add weekly_added to the current month to show something
    papers_read_by_month[-1].count = weekly_added

    # 8. Topic Breakdown
    # Get all tags from all papers
    stmt_tags = select(Paper.tags).join(ProjectPaper).where(
        ProjectPaper.project.has(user_id=current_user.id)
    )
    tags_result = await db.scalars(stmt_tags)
    tag_counts = {}
    for tag_list in tags_result:
        for tag in tag_list:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
            
    sorted_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    topic_breakdown = [TopicCount(tag=t[0], count=t[1]) for t in sorted_tags]
    if not topic_breakdown:
        topic_breakdown = [TopicCount(tag="Machine Learning", count=1)] # Fallback
    
    return AnalyticsResponse(
        totalPapersSaved=total_papers,
        totalNotes=total_notes,
        totalReviews=total_reviews,
        totalChatQuestions=total_chat_questions,
        currentStreakDays=current_streak_days,
        weeklyGoal=weekly_goal,
        papersReadByMonth=papers_read_by_month,
        topicBreakdown=topic_breakdown
    )
