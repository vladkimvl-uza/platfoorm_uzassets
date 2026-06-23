"""All ORM models. Importing this package registers them with Base.metadata."""
from app.models.base import TimestampMixin, UUIDMixin
from app.models.board import (
    Board,
    BoardCard,
    BoardColumn,
)

# --- Financial Model — Финансовая модель removed, replaced by finmodel_storage JSONB) ---
# (was: from app.models.financial_model import FinancialModel, FinancialModelMetric, …)
# --- KPI / Business plan (unified into bp_kpi.py, replaces Phase 3b business_plan.py + kpi.py) ---
from app.models.bp_kpi import (
    BP_METRIC_KEYS,
    BP_METRICS,
    BP_PERIODS,
    BpComment,
    BpRecord,
    KpiComment,
    KpiIndicator,
    KpiManager,
)

# --- Reference / org structure ---
from app.models.company import (
    Company,
    CompanyDirection,
    Direction,
    Sector,
)
from app.models.esg import (
    ESGIssue,
    ESGMetric,
    ESGNote,
    ESGYearTracked,
)

# --- Financials (IFRS / NSBU) ---
from app.models.financial import (
    FinancialLine,
    FinancialReport,
)

# --- Ratings & ESG ---
from app.models.rating import (
    Rating,
    RatingHistory,
    RatingMetric,
)

# --- Tasks & boards (Kanban) ---
from app.models.task import (
    Task,
    TaskAttachment,
    TaskComment,
    TaskDependency,
    TaskHistory,
)
from app.models.project import Project, ProjectComment

# --- PMO (P2+): RAID + статус-отчёты + стейкхолдеры + журнал ---
from app.models.pmo import (
    PmoChange,
    PmoLesson,
    PmoStakeholder,
    RaidItem,
    StatusReport,
)

# --- Auth & users ---
from app.models.user import (
    Group,
    Permission,
    Role,
    User,
    UserGroupRole,
    UserSession,
)

# Backward-compat aliases — old class names point to new equivalents.
# Remove once all Phase 3b code paths (app/routers/business_plans.py, app/routers/kpi.py)
# are deleted or rewritten to use bp_kpi names directly.
BusinessPlan = BpRecord                # tablename: bp_records
BusinessPlanComment = BpComment        # tablename: bp_comments
KPIRecord = KpiIndicator               # CLOSEST equivalent; verify field-level usage if old code reads it
KPIComment = KpiComment                # tablename: kpi_comments
# KPIDraft — no direct equivalent in new schema. Old "draft" semantics (in-progress saves)
# are now handled via localStorage in the frontend KpiEditor. Removed intentionally;
# any code still importing KPIDraft must be updated.

# --- Procurement ---
from app.models.ai import AIAccess, AIConfig, AIHistory, TelemetryLog

# --- Misc ---
from app.models.announcement import Announcement
from app.models.audit import AuditLog
from app.models.comment import Comment
from app.models.consultant import ConsultantImport

# --- Credit portfolio ---
from app.models.credit import (
    CreditPortfolioFxRate,
    CreditPortfolioLoan,
)

# --- Governance ---
from app.models.governance import (
    BoardMember,
    GovernanceData,
    GovernanceRaw,
)
from app.models.note import Note
from app.models.procurement import (
    ProcurementBenchmark,
    ProcurementContract,
    ProcurementData,
    ProductCluster,
)

# --- Subsidies registry (реестр субсидий) ---
from app.models.subsidies import Subsidy

# --- Overview matrix config (настройка квартальной матрицы Сводного обзора) ---
from app.models.overview_matrix import OverviewMatrixConfig

# --- IFRS report history (даты публикации МСФО-отчётности) ---
from app.models.ifrs_report_history import IfrsReportHistory

# --- RBAC v3: group permission grants (overrides + denies) ---
from app.models.rbac_v3 import GroupPermissionGrant
from app.models.system_config import SystemConfig
from app.models.year_registry import YearRegistry

__all__ = [
    "TimestampMixin",
    "UUIDMixin",
    # auth
    "User",
    "Role",
    "Permission",
    "Group",
    "UserSession",
    "UserGroupRole",
    # org
    "Company",
    "Sector",
    "Direction",
    "CompanyDirection",
    # tasks
    "Task",
    "TaskComment",
    "TaskAttachment",
    "TaskHistory",
    "Board",
    "BoardColumn",
    "BoardCard",
    # ratings & esg
    "Rating",
    "RatingHistory",
    "RatingMetric",
    "ESGMetric",
    "ESGIssue",
    "ESGNote",
    "ESGYearTracked",
    # financials
    "FinancialReport",
    "FinancialLine",
    # kpi & bp (NEW unified)
    "BpRecord",
    "BpComment",
    "KpiManager",
    "KpiIndicator",
    "KpiComment",
    "BP_METRICS",
    "BP_METRIC_KEYS",
    "BP_PERIODS",
    # kpi & bp (LEGACY aliases — for transitional period)
    "BusinessPlan",
    "BusinessPlanComment",
    "KPIRecord",
    "KPIComment",
    # procurement
    "ProcurementContract",
    "ProcurementData",
    "ProcurementBenchmark",
    "ProductCluster",
    # subsidies
    "Subsidy",
    # overview matrix
    "OverviewMatrixConfig",
    # ifrs report history
    "IfrsReportHistory",
    # governance
    "GovernanceData",
    "GovernanceRaw",
    "BoardMember",
    # credit
    "CreditPortfolioLoan",
    "CreditPortfolioFxRate",
    # misc
    "Announcement",
    "AuditLog",
    "Comment",
    "Note",
    "YearRegistry",
    "SystemConfig",
    "AIConfig",
    "AIAccess",
    "AIHistory",
    "TelemetryLog",
    "ConsultantImport",
    # rbac v3
    "GroupPermissionGrant",
]
