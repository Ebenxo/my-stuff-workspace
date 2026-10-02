"""Project, conversation and message persistence."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.foundation import Conversation, Message, Project


class ProjectRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, project_id: str) -> Project | None:
        return await self.session.get(Project, project_id)

    async def list_all(self, *, status: str | None = None) -> Sequence[Project]:
        stmt = select(Project).order_by(Project.updated_at.desc())
        if status:
            stmt = stmt.where(Project.status == status)
        return (await self.session.execute(stmt)).scalars().all()

    async def slug_exists(self, slug: str) -> bool:
        stmt = select(func.count()).select_from(Project).where(Project.slug == slug)
        return bool((await self.session.execute(stmt)).scalar_one())

    async def count(self) -> int:
        return int((await self.session.execute(select(func.count()).select_from(Project))).scalar_one())

    async def add(self, project: Project) -> Project:
        self.session.add(project)
        await self.session.flush()
        return project


class ConversationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, conversation_id: str) -> Conversation | None:
        return await self.session.get(Conversation, conversation_id)

    async def list_for_project(self, project_id: str) -> Sequence[Conversation]:
        stmt = (
            select(Conversation)
            .where(Conversation.project_id == project_id)
            .order_by(Conversation.updated_at.desc())
        )
        return (await self.session.execute(stmt)).scalars().all()

    async def add(self, conversation: Conversation) -> Conversation:
        self.session.add(conversation)
        await self.session.flush()
        return conversation

    async def messages(
        self, conversation_id: str, *, after_id: str | None = None, limit: int = 200
    ) -> Sequence[Message]:
        stmt = select(Message).where(Message.conversation_id == conversation_id)
        if after_id:
            stmt = stmt.where(Message.id > after_id)
        stmt = stmt.order_by(Message.id.asc()).limit(limit)
        return (await self.session.execute(stmt)).scalars().all()

    async def add_message(self, message: Message) -> Message:
        self.session.add(message)
        await self.session.flush()
        return message
