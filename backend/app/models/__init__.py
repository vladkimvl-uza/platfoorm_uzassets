"""All ORM models. Importing this package registers them with Base.metadata."""
from app.models.base import TimestampMixin, UUIDMixin

# --- Auth & users ---
from app.models.user import (
    User,
    Role,
    Permission,
    Group,
    RoleByEmail,
    UserSession,
)

# --- Reference / org structure ---
from app.models.company import (
    Company,
    Sector,
    Direction,
    CompanyDirection,
)

# --- Tasks & boards (Kanban) ---
from app.models.task import (
    Task,
    TaskComment,
    TaskAttachment,
    TaskHistory,
)
from app.models.board import (
    Board,
    BoardColumn,
    BoardCard,
)

# --- Ratings & ESG ---
from app.models.rating import (
    Rating,
    RatingHistory,
    RatingMetric,
)
from app.models.esg import (
    ESGMetric,
    ESGIssue,
    ESGNote,
    ESGYearTracked,
)

# --- Financials (IFRS / NSBU) ---
from app.models.financial import (
    FinancialReport,
    FinancialLine,
)

# --- Financial Model — Финансовая модель (Pack 7.69: removed, replaced by finmodel_storage JSONB) ---
# (was: from app.models.financial_model import FinancialModel, FinancialModelMetric, …)

# --- KPI / Business plan (unified into bp_kpi.py, replaces Phase 3b business_plan.py + kpi.py) ---
from app.models.bp_kpi import (
    BpRecord,
    BpComment,
    KpiManager,
    KpiIndicator,
    KpiComment,
    BP_METRICS,
    BP_METRIC_KEYS,
    BP_PERIODS,
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
from app.models.procurement import (
    ProcurementContract,
    ProcurementData,
    ProcurementBenchmark,
    ProductCluster,
)

# --- Governance ---
from app.models.governance import (
    GovernanceData,
    GovernanceRaw,
    BoardMember,
)

# --- Credit portfolio ---
from app.models.credit import (
    CreditPortfolioLoan,
    CreditPortfolioFxRate,
)

# --- Misc ---
from app.models.announcement import Announcement
from app.models.audit import AuditLog
from app.models.comment import Comment
from app.models.note import Note
from app.models.year_registry import YearRegistry
from app.models.system_config import SystemConfig
from app.models.ai import AIConfig, AIAccess, AIHistory, TelemetryLog
from app.models.consultant import ConsultantImport

# --- RBAC v3: group permission grants (overrides + denies) ---
from app.models.rbac_v3 import GroupPermissionGrant

__all__ = [
    "TimestampMixin",
    "UUIDMixin",
    # auth
    "User",
    "Role",
    "Permission",
    "Group",
    "RoleByEmail",
    "UserSession",
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
