"""Generic user-scoped repository — the enforcement layer for per-user data
isolation now that the app connects to Postgres with an RLS-bypassing role.

Every method requires `user_id` as an explicit argument and bakes it into the
WHERE clause internally. This is deliberate: RLS policies remain defined in
supabase/schema.sql as defense-in-depth, but they are not the enforcement
mechanism for traffic coming through this API — this class is.
"""

from typing import Generic, TypeVar
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

ModelT = TypeVar("ModelT")


class UserScopedRepository(Generic[ModelT]):
    model: type[ModelT]
    user_id_column: str = "user_id"

    def __init__(self, session: AsyncSession):
        self.session = session

    def _scoped(self, stmt, user_id: str):
        return stmt.where(getattr(self.model, self.user_id_column) == user_id)

    async def list(self, user_id: str, *, order_by=None) -> list[ModelT]:
        stmt = self._scoped(select(self.model), user_id)
        if order_by is not None:
            stmt = stmt.order_by(order_by)
        return list((await self.session.execute(stmt)).scalars().all())

    async def get(self, user_id: str, id_: str) -> ModelT | None:
        stmt = self._scoped(select(self.model), user_id).where(self.model.id == id_)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def create(self, user_id: str, **fields) -> ModelT:
        obj = self.model(**fields, **{self.user_id_column: user_id})
        self.session.add(obj)
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def update(self, user_id: str, id_: str, **fields) -> ModelT | None:
        obj = await self.get(user_id, id_)
        if obj is None:
            return None
        for k, v in fields.items():
            setattr(obj, k, v)
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def delete(self, user_id: str, id_: str) -> bool:
        obj = await self.get(user_id, id_)
        if obj is None:
            return False
        await self.session.delete(obj)
        await self.session.flush()
        return True
