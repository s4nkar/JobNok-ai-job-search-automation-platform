"""Generic user-scoped repository — the sole enforcement layer for per-user
data isolation. There is no Row Level Security or PostgREST underneath this;
the app connects to Postgres with a single ordinary role.

Every method requires `user_id` as an explicit argument and bakes it into the
WHERE clause internally. This class is the enforcement mechanism for every
query made through this API — nothing else scopes access.
"""

# Required here: this class defines a method literally named `list`, which
# shadows the builtin `list` for the rest of the class body once Python
# executes that def statement - without lazy (string) annotations, a later
# method's `list[ModelT]` return-type annotation would eagerly resolve
# against that method object instead of the builtin and crash at import
# time ("'function' object is not subscriptable").
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Generic, TypeVar
from sqlalchemy import select, tuple_
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

    async def list_page(
        self, user_id: str, *, limit: int, cursor: str | None = None,
    ) -> tuple[list[ModelT], str | None]:
        """Keyset ("cursor") pagination, newest first, for a list endpoint
        that opts into it - every other caller of plain list() above is
        unaffected. Ordered by (created_at, id) descending - created_at
        alone isn't a unique key (two rows can share a timestamp), so id
        breaks ties and keeps the cursor unambiguous regardless of insert
        timing. Unlike OFFSET pagination, this stays correct (no skipped or
        duplicated rows) even if the user adds a new row while paging
        through an older page - the cursor is anchored to a value, not a
        position. Requires the model to have `created_at` and `id` columns,
        true for every model via CreatedAtMixin/UUIDPKMixin.

        Returns (rows, next_cursor) - next_cursor is None once there are no
        more rows after this page. A malformed cursor (tampered query param,
        stale link) is treated as "start from the top" rather than a 500.
        """
        stmt = self._scoped(select(self.model), user_id)
        if cursor:
            created_at_str, _, id_str = cursor.partition("_")
            try:
                cursor_created_at = datetime.fromisoformat(created_at_str)
                cursor_id = uuid.UUID(id_str)
            except ValueError:
                cursor_created_at = cursor_id = None
            if cursor_created_at is not None and cursor_id is not None:
                stmt = stmt.where(
                    tuple_(self.model.created_at, self.model.id) < tuple_(cursor_created_at, cursor_id)
                )
        stmt = stmt.order_by(self.model.created_at.desc(), self.model.id.desc()).limit(limit + 1)
        rows = list((await self.session.execute(stmt)).scalars().all())
        next_cursor = None
        if len(rows) > limit:
            rows = rows[:limit]
            last = rows[-1]
            next_cursor = f"{last.created_at.isoformat()}_{last.id}"
        return rows, next_cursor

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
