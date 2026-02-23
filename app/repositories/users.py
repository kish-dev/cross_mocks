from sqlalchemy import select
from app.db.models import User


class UsersRepo:
    async def get_by_tg_id(self, session, tg_user_id: int):
        return (await session.execute(select(User).where(User.tg_user_id == tg_user_id))).scalar_one_or_none()

    async def upsert(self, session, tg_user_id: int, username: str | None, full_name: str) -> User:
        u = await self.get_by_tg_id(session, tg_user_id)
        if u:
            u.username = username
            u.full_name = full_name
            return u
        u = User(tg_user_id=tg_user_id, username=username, full_name=full_name)
        session.add(u)
        await session.flush()
        return u
