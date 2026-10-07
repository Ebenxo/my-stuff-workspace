"""Composition root: builds and owns every long-lived object."""

from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

from app.agents.context import ContextBuilder
from app.agents.runner import AgentRunner
from app.core.clock import Clock, SystemClock
from app.core.secrets import SecretStore, build_secret_store
from app.core.settings import Settings
from app.events.bus import EventBus
from app.files.artifacts import ArtifactStore
from app.mcp.manager import MCPServerManager
from app.memory.embedder import HashingEmbedder
from app.memory.service import MemoryService
from app.models.database import Database
from app.orchestration.orchestrator import Orchestrator
from app.permissions.approvals import ApprovalService, SessionGrants
from app.providers.gateway import LLMGateway
from app.providers.registry import ProviderRegistry, new_http_client
from app.providers.router import ModelRouter
from app.providers.usage import UsageService
from app.repositories.idea_store import IdeaStore
from app.repositories.integration_store import IntegrationStore
from app.repositories.memory_store import MemoryStore
from app.repositories.orchestration_store import ObjectiveStore, TaskStore
from app.repositories.runtime_store import (
    AgentStore,
    ApprovalStore,
    ArtifactRepo,
    RunStore,
    ToolCallStore,
    ToolRowStore,
)
from app.repositories.search_index import SearchIndex
from app.repositories.workflow_store import ScheduleStore, WorkflowRunStore, WorkflowStore
from app.scheduler.service import Scheduler
from app.schemas.common import PermissionLevel
from app.schemas.providers import Budgets
from app.services.agents import AgentService
from app.services.conversations import ConversationService
from app.services.demo import DemoService
from app.services.files import FilesService
from app.services.health import HealthService, register_core_checks
from app.services.ideas import IdeaService
from app.services.mcp import MCPService
from app.services.notifications import NotificationService
from app.services.objectives import ObjectiveService
from app.services.projects import ProjectService
from app.services.providers import ProviderService
from app.services.settings import SettingsService
from app.services.timeline import TimelineService
from app.services.tools import ToolService
from app.services.universal_search import UniversalSearch
from app.tasks.queue import InProcessJobQueue, JobQueue
from app.tools.builtin import builtin_tools
from app.tools.context import ToolContextFactory
from app.tools.executor import ToolExecutor
from app.tools.netguard import SafeHttpClient
from app.tools.registry import ToolRegistry
from app.tools.sandbox import LocalSandbox, SandboxManager
from app.tools.search import SearchService
from app.workflows.engine import WorkflowEngine
from app.workflows.service import WorkflowService


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
    runner: AgentRunner
    agent_service: AgentService
    objective_store: ObjectiveStore
    task_store: TaskStore
    orchestrator: Orchestrator
    objective_service: ObjectiveService
    demo: DemoService
    tool_service: ToolService
    files: FilesService
    tool_contexts: ToolContextFactory
    sandbox: SandboxManager
    safe_http: SafeHttpClient
    search: SearchService  # web search for agents
    memory_store: MemoryStore
    memory: MemoryService
    search_index: SearchIndex
    universal_search: UniversalSearch  # the app's own search box
    workflow_store: WorkflowStore
    workflow_run_store: WorkflowRunStore
    schedule_store: ScheduleStore
    workflow_engine: WorkflowEngine
    workflows: WorkflowService
    scheduler: Scheduler
    integration_store: IntegrationStore
    mcp_manager: MCPServerManager
    mcp: MCPService
    idea_store: IdeaStore
    ideas: IdeaService
    timeline: TimelineService
    started_at: float

    async def close(self) -> None:
        await self.scheduler.stop()
        await self.workflows.shutdown()  # first: workflows and objectives own agent runs of their own
        await self.objective_service.shutdown()
        await self.agent_service.shutdown()
        await self.mcp.shutdown()  # after the runs that might still call its tools
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
    memory_store = MemoryStore(db, clock)
    search_index = SearchIndex(db)
    memory = MemoryService(memory_store, search_index, bus, HashingEmbedder(), clock)

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
        memory=memory,
    )
    executor = ToolExecutor(tools, approvals, tool_call_store, bus, tool_row_store, clock)
    approvals.set_validator(executor.validate_arguments)
    runner = AgentRunner(
        gateway=gateway,
        runs=run_store,
        agents=agent_store,
        executor=executor,
        tools=tools,
        tool_rows=tool_row_store,
        tool_contexts=tool_contexts,
        approvals=approvals,
        bus=bus,
        context_builder=ContextBuilder(memory),
    )
    agent_service = AgentService(
        agents=agent_store,
        runs=run_store,
        tool_calls=tool_call_store,
        runner=runner,
        approvals=approvals,
        projects=projects,
        settings=settings_service,
        notifications=notifications,
        bus=bus,
        clock=clock,
    )

    async def level_for(project_id: str) -> PermissionLevel:
        project = await projects.get(project_id)
        return project.settings.permission_level or await settings_service.default_permission_level()

    objective_store = ObjectiveStore(db, clock)
    task_store = TaskStore(db, clock)
    orchestrator = Orchestrator(
        objectives=objective_store,
        tasks=task_store,
        runner=runner,
        agents=agent_store,
        runs=run_store,
        registry=tools,
        tool_rows=tool_row_store,
        bus=bus,
        level_for=level_for,
        project_dir_for=projects.project_dir,
        clock=clock,
        memory=memory,
    )
    objective_service = ObjectiveService(
        objectives=objective_store,
        tasks=task_store,
        orchestrator=orchestrator,
        runner=runner,
        runs=run_store,
        agents=agent_store,
        registry=tools,
        tool_rows=tool_row_store,
        projects=projects,
        notifications=notifications,
        bus=bus,
        clock=clock,
    )
    demo = DemoService(
        projects=projects, providers=providers, registry=registry, objectives=objective_service
    )
    tool_service = ToolService(tool_row_store, tool_call_store, tools, bus)
    files = FilesService(projects, bus)
    idea_store = IdeaStore(db, clock)
    ideas = IdeaService(
        store=idea_store,
        index=search_index,
        projects=projects,
        objectives=objective_service,
        notifications=notifications,
        bus=bus,
        clock=clock,
    )
    universal_search = UniversalSearch(
        search_index,
        projects=projects,
        objectives=objective_store,
        artifacts=artifacts,
        memory=memory,
        reindexers=[ideas.reindex_all],
    )
    bus.add_listener(universal_search.on_event)

    async def notify_workflow(kind: str, title: str, body: str, ref: dict[str, object]) -> None:
        await notifications.notify(kind, title, body, ref=ref)

    workflow_store = WorkflowStore(db, clock)
    workflow_run_store = WorkflowRunStore(db, clock)
    schedule_store = ScheduleStore(db, clock)
    workflow_engine = WorkflowEngine(
        workflows=workflow_store,
        runs=workflow_run_store,
        runner=runner,
        agents=agent_store,
        agent_runs=run_store,
        executor=executor,
        tool_contexts=tool_contexts,
        bus=bus,
        level_for=level_for,
        clock=clock,
        notify=notify_workflow,
    )
    workflows = WorkflowService(
        workflows=workflow_store,
        runs=workflow_run_store,
        engine=workflow_engine,
        runner=runner,
        agents=agent_store,
        registry=tools,
        tool_rows=tool_row_store,
        approvals=approvals,
        bus=bus,
        project_exists=projects.get,
        clock=clock,
    )
    scheduler = Scheduler(
        schedules=schedule_store,
        runs=workflow_run_store,
        workflows=workflows,
        bus=bus,
        clock=clock,
        also_on_tick=[ideas.remind_due],
    )
    timeline = TimelineService(
        objectives=objective_store,
        runs=run_store,
        agents=agent_store,
        approvals=approval_store,
        workflows=workflow_store,
        workflow_runs=workflow_run_store,
        schedules=schedule_store,
        ideas=idea_store,
        clock=clock,
    )
    integration_store = IntegrationStore(db, clock)
    mcp_manager = MCPServerManager(tools, tool_row_store, bus, clock)
    mcp = MCPService(integration_store, mcp_manager, tool_row_store, secret_store, bus, settings.home, clock)
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
    health.register("mcp", mcp.health_check)
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
        runner=runner,
        agent_service=agent_service,
        objective_store=objective_store,
        task_store=task_store,
        orchestrator=orchestrator,
        objective_service=objective_service,
        demo=demo,
        tool_service=tool_service,
        files=files,
        tool_contexts=tool_contexts,
        sandbox=sandbox,
        safe_http=safe_http,
        search=search,
        memory_store=memory_store,
        memory=memory,
        search_index=search_index,
        universal_search=universal_search,
        workflow_store=workflow_store,
        workflow_run_store=workflow_run_store,
        schedule_store=schedule_store,
        workflow_engine=workflow_engine,
        workflows=workflows,
        scheduler=scheduler,
        integration_store=integration_store,
        mcp_manager=mcp_manager,
        mcp=mcp,
        idea_store=idea_store,
        ideas=ideas,
        timeline=timeline,
        started_at=started_at,
    )
