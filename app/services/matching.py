from datetime import datetime
from sqlalchemy import select
from app.db.models import User, PairStats


class MatchingService:
    @staticmethod
    def pair_key(a: int, b: int) -> tuple[int, int]:
        return (a, b) if a < b else (b, a)

    async def rank_candidates(self, session, requester_id: int) -> list[int]:
        users = (await session.execute(select(User).where(User.is_active.is_(True), User.id != requester_id))).scalars().all()
        scored: list[tuple[tuple[int, float], int]] = []
        now = datetime.utcnow()
        for u in users:
            a, b = self.pair_key(requester_id, u.id)
            ps = (await session.execute(select(PairStats).where(PairStats.user_a_id == a, PairStats.user_b_id == b))).scalar_one_or_none()
            if ps is None or ps.last_interview_at is None:
                score = (10**9, 0.0)
            else:
                age = (now - ps.last_interview_at).total_seconds()
                score = (int(age), float(-ps.interviews_count))
            scored.append((score, u.id))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [u for _, u in scored]
