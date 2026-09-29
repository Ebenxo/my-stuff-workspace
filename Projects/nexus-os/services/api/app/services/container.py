"""Composition root: builds and owns every long-lived object."""

from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

from app.core.clock import Clock, SystemClock
from app.core.secrets import SecretStore, build_secret_store
from app.core.settings import Settings
from app.events.bus import EventBus
from app.files.artifacts import ArtifactStore
from app.models.database import Database
from app.permissions.approvals import ApprovalService, SessionGrants
from app.providers.gateway import LLMGateway
from app.providers.registry import ProviderRegistry, new_http_client
from app.providers.router import ModelRouter
from app.providers.usage import UsageService
from app.repositories.runtime_store import (
    AgentStore,
    ApprovalStore,
    ArtifactRepo,
    RunStore,
    ToolCallStore,
    ToolRowStore,
)
from app.schemas.providers import Budgets
from app.services.conversations import ConversationService
from app.services.health import HealthService, register_core_checks
from app.services.notifications import NotificationService
from app.services.projects import ProjectService
from app.services.providers import ProviderService
from app.services.settings import SettingsService
from app.tasks.queue import InProcessJobQueue, JobQueue
from app.tools.builtin import builtin_tools
from app.tools.context import ToolContextFactory
from app.tools.executor import ToolExecutor
from app.tools.netguard import SafeHttpClient
from app.tools.registry import ToolRegistry
from app.tools.sandbox import LocalSandbox, SandboxManager
from app.tools.search import SearchService


@dataclass
class AppContainer:
    settings: Settings
    token: str
    clock: Clock
    db: Database
    bus: EventBus
    secrets: SecretStore
    queue: JobQueue
    settings_service: SettingsService
    projects: ProjectService
    conversations: ConversationService
    notifications: NotificationService
    health: HealthService
    http: httpx.AsyncClient
    registry: ProviderRegistry
    router: ModelRouter
    usage: UsageService
    gateway: LLMGateway
    providers: ProviderService
    agent_store: AgentStore
    run_store: RunStore
    tool_call_store: ToolCallStore
    approval_store: ApprovalStore
    tool_row_store: ToolRowStore
    approvals: ApprovalService
    artifacts: ArtifactStore
    tools: ToolRegistry
    executor: ToolExecutor
    tool_contexts: ToolContextFactory
    sandbox: SandboxManager
    safe_http: SafeHttpClient
    search: SearchService
    started_at: float

    async def close(self) -> None:
        await self.queue.shutdown()
        await self.http.aclose()
        await self.bus.close()
        await self.db.close()


async def build_container(
    settings: Settings,
    *,
    secrets: SecretStore | None = None,
    clock: Clock | None = None,
    http: httpx.AsyncClient | None = None,
) -> AppContainer:
    clock = clock or SystemClock()
    settings.ensure_home()
    token = settings.resolve_api_token()
    db = Database(settings.db_url)
    bus = EventBus(db, clock)
    queue = InProcessJobQueue(concurrency=4)
    secret_store = secrets or build_secret_store(settings.home)
    settings_service = SettingsService(db, bus, settings, clock)
    projects = ProjectService(db, bus, settings_service, clock)
    conversations = ConversationService(db, bus, clock)
    notifications = NotificationService(db, bus, clock)
    health = HealthService()
    http_client = http or new_http_client()
    registry = ProviderRegistry(db, secret_store, http_client)
    router = ModelRouter(registry, settings_service.get_routing_rules)

    async def effective_budgets() -> Budgets:
        # Global limits plus each project's own monthly limit (a project's setting wins).
        budgets = await settings_service.get_budgets()
        merged = {**budgets.per_project_monthly_usd, **await projects.monthly_budgets()}
        return budgets.model_copy(update={"per_project_monthly_usd": merged})

    usage = UsageService(db, bus, clock, effective_budgets)
    gateway = LLMGateway(registry, router, usage, bus)
    providers = ProviderService(db, bus, secret_store, registry, clock, settings)
    agent_store = AgentStore(db, clock)
    run_store = RunStore(db, clock)
    tool_call_store = ToolCallStore(db, clock)
    approval_store = ApprovalStore(db, clock)
    tool_row_store = ToolRowStore(db, clock)
    approvals = ApprovalService(approval_store, bus, SessionGrants(clock), notifications.notify, clock)
    artifacts = ArtifactStore(ArtifactRepo(db), bus, projects.project_dir, clock)
    tools = ToolRegistry()
    for tool in builtin_tools():
        tools.register(tool)
    sandbox = LocalSandbox()
    safe_http = SafeHttpClient()
    search = SearchService(safe_http, settings_service.get_search_config, secret_store.get)

    async def project_domains(project_id: str) -> list[str]:
        return (await projects.get(project_id)).settings.allowed_domains

    tool_contexts = ToolContextFactory(
        project_dir_for=projects.project_dir,
        project_domains_for=project_domains,
        sandbox=sandbox,
        http=safe_http,
        artifacts=artifacts,
        bus=bus,
        search=search,
    )
    executor = ToolExecutor(tools, approvals, tool_call_store, bus, tool_row_store, clock)
    approvals.set_validator(executor.validate_arguments)
    started_at = time.monotonic()
    register_core_checks(
        health,
        settings=settings,
        db=db,
        bus=bus,
        queue=queue,
        secrets=secret_store,
        workspace_root=projects.workspace,
        started_at=started_at,
        registry=registry,
    )
    return AppContainer(
        settings=settings,
        token=token,
        clock=clock,
        db=db,
        bus=bus,
        secrets=secret_store,
        queue=queue,
        settings_service=settings_service,
        projects=projects,
        conversations=conversations,
        notifications=notifications,
        health=health,
        http=http_client,
        registry=registry,
        router=router,
        usage=usage,
        gateway=gateway,
        providers=providers,
        agent_store=agent_store,
        run_store=run_store,
        tool_call_store=tool_call_store,
        approval_store=approval_store,
        tool_row_store=tool_row_store,
        approvals=approvals,
        artifacts=artifacts,
        tools=tools,
        executor=executor,
        tool_contexts=tool_contexts,
        sandbox=sandbox,
        safe_http=safe_http,
        search=search,
        started_at=started_at,
    )
