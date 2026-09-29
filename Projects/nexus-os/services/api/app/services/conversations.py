"""Conversation and message use cases."""

from __future__ import annotations

from app.core.clock import Clock
from app.core.errors import NotFoundError
from app.core.ids import new_id
from app.events.bus import EventBus
from app.events.types import EventType
from app.models.database import Database
from app.models.foundation import Conversation, Message
from app.repositories.projects import ConversationRepository, ProjectRepository
from app.schemas.projects import ConversationCreate, ConversationOut, MessageOut


class ConversationService:
    def __init__(self, db: Database, bus: EventBus, clock: Clock) -> None:
        self._db = db
        self._bus = bus
        self._clock = clock

    async def list_for_project(self, project_id: str) -> list[ConversationOut]:
        async with self._db.session() as session:
            if await ProjectRepository(session).get(project_id) is None:
                raise NotFoundError(f"Project {project_id} not found")
            rows = await ConversationRepository(session).list_for_project(project_id)
            return [ConversationOut.model_validate(r) for r in rows]

    async def create(self, project_id: str, data: ConversationCreate) -> ConversationOut:
        async with self._db.session() as session:
            if await ProjectRepository(session).get(project_id) is None:
                raise NotFoundError(f"Project {project_id} not found")
            now = self._clock.now()
            row = await ConversationRepository(session).add(
                Conversation(
                    id=new_id("conv"),
                    project_id=project_id,
                    title=data.title,
                    created_at=now,
                    updated_at=now,
                )
            )
            out = ConversationOut.model_validate(row)
        await self._bus.emit(
            EventType.CONVERSATION_CREATED,
            project_id=project_id,
            actor="user",
            payload={"conversation_id": out.id, "title": out.title},
        )
        return out

    async def messages(
        self, conversation_id: str, *, after_id: str | None = None, limit: int = 200
    ) -> list[MessageOut]:
        async with self._db.session() as session:
            repo = ConversationRepository(session)
            if await repo.get(conversation_id) is None:
                raise NotFoundError(f"Conversation {conversation_id} not found")
            rows = await repo.messages(conversation_id, after_id=after_id, limit=limit)
            return [MessageOut.model_validate(r) for r in rows]

    async def add_message(
        self,
        conversation_id: str,
        *,
        role: str,
        content: str,
        agent_id: str | None = None,
        meta: dict[str, object] | None = None,
        actor: str = "user",
    ) -> MessageOut:
        async with self._db.session() as session:
            repo = ConversationRepository(session)
            conversation = await repo.get(conversation_id)
            if conversation is None:
                raise NotFoundError(f"Conversation {conversation_id} not found")
            now = self._clock.now()
            conversation.updated_at = now
            row = await repo.add_message(
                Message(
                    id=new_id("msg"),
                    conversation_id=conversation_id,
                    role=role,
                    agent_id=agent_id,
                    content=content,
                    meta=meta or {},
                    created_at=now,
                )
            )
            out = MessageOut.model_validate(row)
            project_id = conversation.project_id
        await self._bus.emit(
            EventType.MESSAGE_CREATED,
            project_id=project_id,
            agent_id=agent_id,
            actor=actor,
            payload={"conversation_id": conversation_id, "message_id": out.id, "role": role},
        )
        return out
