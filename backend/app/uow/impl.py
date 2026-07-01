"""Concrete UnitOfWork — owns an AsyncSession, exposes repositories.

Usage:
    async with UnitOfWork(session_factory) as uow:
        managers = await uow.kpi.get_managers_with_indicators(co_id, 2026)
        ...  # автоматический commit при выходе без exception
"""
from collections.abc import Callable
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.admin_broadcasts_repository import AdminBroadcastsRepository
from app.repositories.ai_repository import AiRepository
from app.repositories.api_catalog_repository import ApiCatalogRepository
from app.repositories.api_keys_repository import ApiKeysRepository
from app.repositories.attachments_repository import AttachmentsRepository
from app.repositories.bot_callbacks_repository import BotCallbacksRepository
from app.repositories.bp_repository import BpRepository
from app.repositories.comments_repository import CommentsRepository
from app.repositories.companies_admin_v2_repository import CompaniesAdminV2Repository
from app.repositories.companies_repository import CompaniesRepository
from app.repositories.company_library_repository import CompanyLibraryRepository
from app.repositories.consultants_repository import ConsultantsRepository
from app.repositories.credit_portfolio_repository import CreditPortfolioRepository
from app.repositories.credit_scenario_repository import CreditScenarioRepository
from app.repositories.dashboard_repository import DashboardRepository
from app.repositories.esg_repository import EsgRepository
from app.repositories.exec_dashboard_repository import ExecDashboardRepository
from app.repositories.external_apis_repository import ExternalApisRepository
from app.repositories.finmodel_repository import FinModelRepository
from app.repositories.forensic_repository import ForensicRepository
from app.repositories.governance_repository import GovernanceRepository
from app.repositories.kpi_repository import KpiRepository
from app.repositories.moderation_repository import ModerationRepository
from app.repositories.notes_repository import NotesRepository
from app.repositories.notifications_repository import NotificationsRepository
from app.repositories.partners_repository import PartnersRepository
from app.repositories.procurement_repository import ProcurementRepository
from app.repositories.production_repository import ProductionRepository
from app.repositories.projects_repository import ProjectsRepository
from app.repositories.ratings_repository import RatingsRepository
from app.repositories.scenarios_repository import ScenariosRepository
from app.repositories.system_config_repository import SystemConfigRepository
from app.repositories.tasks_repository import TasksRepository
from app.uow.ports import UnitOfWorkABC


class UnitOfWork(UnitOfWorkABC):
    """Default UoW backed by SQLAlchemy AsyncSession."""

    def __init__(self, session_factory: Callable[[], AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None

    async def __aenter__(self) -> Self:
        self._session = self._session_factory()
        # Wire repositories. По мере миграции других модулей сюда
        # добавляются: self.bp = BpRepository(self._session), и т.д.
        self.admin_broadcasts = AdminBroadcastsRepository(self._session)
        self.ai = AiRepository(self._session)
        self.api_catalog = ApiCatalogRepository(self._session)
        self.api_keys = ApiKeysRepository(self._session)
        self.attachments = AttachmentsRepository(self._session)
        self.bot_callbacks = BotCallbacksRepository(self._session)
        self.bp = BpRepository(self._session)
        self.comments = CommentsRepository(self._session)
        self.companies = CompaniesRepository(self._session)
        self.companies_admin_v2 = CompaniesAdminV2Repository(self._session)
        self.company_library = CompanyLibraryRepository(self._session)
        self.consultants = ConsultantsRepository(self._session)
        self.credit_portfolio = CreditPortfolioRepository(self._session)
        self.credit_scenario = CreditScenarioRepository(self._session)
        self.dashboard = DashboardRepository(self._session)
        self.esg = EsgRepository(self._session)
        self.exec_dashboard = ExecDashboardRepository(self._session)
        self.external_apis = ExternalApisRepository(self._session)
        self.finmodel = FinModelRepository(self._session)
        self.forensic = ForensicRepository(self._session)
        self.governance = GovernanceRepository(self._session)
        self.kpi = KpiRepository(self._session)
        self.moderation = ModerationRepository(self._session)
        self.notes = NotesRepository(self._session)
        self.notifications = NotificationsRepository(self._session)
        self.partners = PartnersRepository(self._session)
        self.procurement = ProcurementRepository(self._session)
        self.production = ProductionRepository(self._session)
        self.projects = ProjectsRepository(self._session)
        self.ratings = RatingsRepository(self._session)
        self.scenarios = ScenariosRepository(self._session)
        self.system_config = SystemConfigRepository(self._session)
        self.tasks = TasksRepository(self._session)
        return self

    async def __aexit__(self, exc_type, exc_value, traceback) -> None:
        if self._session is None:
            return
        try:
            if exc_type:
                await self._session.rollback()
            else:
                await self._session.commit()
        finally:
            await self._session.close()
            self._session = None

    async def commit(self) -> None:
        if self._session is None:
            raise RuntimeError("Session not initialised; use as `async with`")
        await self._session.commit()

    async def rollback(self) -> None:
        if self._session is None:
            return
        await self._session.rollback()

    async def flush(self) -> None:
        if self._session is None:
            raise RuntimeError("Session not initialised; use as `async with`")
        await self._session.flush()
