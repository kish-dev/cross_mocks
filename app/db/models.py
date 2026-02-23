from datetime import datetime
from sqlalchemy import BigInteger, String, Boolean, DateTime, ForeignKey, Integer, Text, JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    tg_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    full_name: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class InterviewTrack(Base):
    __tablename__ = "interview_tracks"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    title: Mapped[str] = mapped_column(String(128), unique=True)


class TaskPack(Base):
    __tablename__ = "task_packs"
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    track_id: Mapped[int] = mapped_column(ForeignKey("interview_tracks.id"))
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    pack_id: Mapped[int] = mapped_column(ForeignKey("task_packs.id"))
    position: Mapped[int] = mapped_column(Integer)
    question: Mapped[str] = mapped_column(Text)


class MatchRequest(Base):
    __tablename__ = "match_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    requester_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    mode: Mapped[str] = mapped_column(String(32))  # find_interviewer / find_student
    track_code: Mapped[str] = mapped_column(String(32))
    pack_id: Mapped[int | None] = mapped_column(ForeignKey("task_packs.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Session(Base):
    __tablename__ = "sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    interviewer_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    track_code: Mapped[str] = mapped_column(String(32))
    pack_id: Mapped[int] = mapped_column(ForeignKey("task_packs.id"))
    starts_at: Mapped[datetime] = mapped_column(DateTime)
    ends_at: Mapped[datetime] = mapped_column(DateTime)
    meeting_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="scheduled")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SessionFeedback(Base):
    __tablename__ = "session_feedback"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id"))
    author_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    about_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    role_context: Mapped[str] = mapped_column(String(32))  # interviewer_report / student_report
    score: Mapped[int] = mapped_column(Integer)
    feedback: Mapped[str] = mapped_column(Text)
    rubric: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PairStats(Base):
    __tablename__ = "pair_stats"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_a_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    user_b_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    interviews_count: Mapped[int] = mapped_column(Integer, default=0)
    last_interview_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    __table_args__ = (UniqueConstraint("user_a_id", "user_b_id", name="uq_pair"),)


class PackSubmission(Base):
    __tablename__ = "pack_submissions"
    id: Mapped[int] = mapped_column(primary_key=True)
    student_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    content_text: Mapped[str] = mapped_column(Text)
    source_message_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")  # pending/changes_requested/approved
    admin_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
