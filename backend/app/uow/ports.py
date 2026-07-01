"""Abstract Unit of Work port. Services depend on this interface, not on
concrete `UnitOfWork` — что позволяет в тестах подменить на FakeUnitOfWork
с in-memory repositories.
"""
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
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


class UnitOfWorkABC(ABC):
    # Repositories — concrete implementations populate these in __aenter__.
    admin_broadcasts: "AdminBroadcastsRepository"
    ai: "AiRepository"
    api_catalog: "ApiCatalogRepository"
    api_keys: "ApiKeysRepository"
    attachments: "AttachmentsRepository"
    bot_callbacks: "BotCallbacksRepository"
    bp: "BpRepository"
    comments: "CommentsRepository"
    companies: "CompaniesRepository"
    companies_admin_v2: "CompaniesAdminV2Repository"
    company_library: "CompanyLibraryRepository"
    consultants: "ConsultantsRepository"
    credit_portfolio: "CreditPortfolioRepository"
    credit_scenario: "CreditScenarioRepository"
    dashboard: "DashboardRepository"
    esg: "EsgRepository"
    exec_dashboard: "ExecDashboardRepository"
    external_apis: "ExternalApisRepository"
    finmodel: "FinModelRepository"
    forensic: "ForensicRepository"
    governance: "GovernanceRepository"
    kpi: "KpiRepository"
    moderation: "ModerationRepository"
    notes: "NotesRepository"
    notifications: "NotificationsRepository"
    partners: "PartnersRepository"
    procurement: "ProcurementRepository"
    production: "ProductionRepository"
    projects: "ProjectsRepository"
    ratings: "RatingsRepository"
    scenarios: "ScenariosRepository"
    system_config: "SystemConfigRepository"
    tasks: "TasksRepository"

    @abstractmethod
    async def __aenter__(self) -> "UnitOfWorkABC":
        raise NotImplementedError()

    @abstractmethod
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def commit(self) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def rollback(self) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def flush(self) -> None:
        """Push pending changes to DB without committing the transaction.
        Нужно когда service хочет получить auto-generated id'шку (RETURNING)
        перед side-effect'ом, но без финальной фиксации транзакции."""
        raise NotImplementedError()
