/**
 * Governance API client.
 *
 * Wraps /governance endpoints: overview, company detail, GovernanceData edit,
 * board members CRUD.
 *
 * Note: this is the structured editable side (`governance_data` table).
 * Raw Excel snapshots (`governance_raw`) are separate and never conflated.
 */
import { api, type ModerationQueuedTag } from "./client";

export type RoleType = "chairman" | "independent" | "state_rep";

export const ROLE_TYPE_META: { key: RoleType; label: string; color: string }[] = [
  { key: "chairman",      label: "Председатель",       color: "#7F77DD" },
  { key: "independent",   label: "Независимый",        color: "#1D9E75" },
  { key: "state_rep",     label: "Представитель гос.", color: "#A855F7" },
];

// ---------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------

export interface GovernanceOverviewKpis {
  total_companies: number;
  companies_with_data: number;
  avg_board_size: number | null;
  avg_independent_pct: number | null;
  avg_women_pct: number | null;
  avg_foreign_pct: number | null;
  avg_attendance_pct: number | null;
  avg_meetings_per_year: number | null;
  committees_audit_count: number;
  committees_remuneration_count: number;
  committees_nomination_count: number;
  committees_strategy_count: number;
}

export interface DiversityStat {
  label: string;
  color: string;
  pct: number;
  count: number;
}

export interface GovernanceCompanyScore {
  company_id: string;
  company_code: string;
  company_name: string | null;
  company_abbr: string | null;
  sector_code: string | null;
  sector_color: string | null;
  year: number | null;
  board_size: number | null;
  independent_count: number | null;
  women_count: number | null;
  foreign_count: number | null;
  vacant_seats: number | null;
  exec_count: number | null;
  nonexec_count: number | null;
  independent_pct: number | null;
  women_pct: number | null;
  foreign_pct: number | null;
  committees_count: number;
  has_all_4_committees: boolean;
  has_audit_committee: boolean | null;
  has_remuneration_committee: boolean | null;
  has_nomination_committee: boolean | null;
  has_strategy_committee: boolean | null;
  has_anticorr_committee: boolean | null;
  has_procurement_committee: boolean | null;
  has_esg_committee: boolean | null;
  has_dno_insurance: boolean | null;
  has_induction_program: boolean | null;
  meetings_per_year: number | null;
  attendance_pct: number | null;
  governance_score: number | null;          // 0..100 composite (computed)
  governance_score_1200: number | null;     // legacy raw 0..1200 (from payload)
  rank: number;
  age_avg: number | null;
  age_min: number | null;
  age_max: number | null;
}

export interface GovernanceOverviewResponse {
  year: number | null;
  sector_code: string | null;
  kpis: GovernanceOverviewKpis;
  diversity_split: DiversityStat[];
  rankings: GovernanceCompanyScore[];
  available_years: number[];
  sectors: { code: string; count: number }[];
  generated_at: string;
}

export interface BoardMemberBrief {
  id: string;
  company_id: string;
  full_name: string;
  position: string | null;
  role_type: RoleType | null;
  is_independent: boolean | null;
  is_woman: boolean | null;
  is_foreign: boolean | null;
  appointed_date: string | null;
  term_end_date: string | null;
  email: string | null;
  phone: string | null;
  bio: string | null;
}

export interface GovernanceDataBrief {
  id: string;
  company_id: string;
  year: number;
  board_size: number | null;
  independent_directors_count: number | null;
  women_directors_count: number | null;
  foreign_directors_count: number | null;
  avg_age: number | null;
  has_audit_committee: boolean | null;
  has_remuneration_committee: boolean | null;
  has_nomination_committee: boolean | null;
  has_strategy_committee: boolean | null;
  has_anticorr_committee: boolean | null;
  has_procurement_committee: boolean | null;
  has_esg_committee: boolean | null;
  has_dno_insurance: boolean | null;
  has_induction_program: boolean | null;
  meetings_per_year: number | null;
  avg_attendance_pct: number | null;
  notes: string | null;
  updated_at: string;
}

export interface GovernanceCompanyDetail {
  company_id: string;
  company_code: string;
  company_name: string | null;
  sector_code: string | null;
  year: number;
  data: GovernanceDataBrief | null;
  board_members: BoardMemberBrief[];
  score: number | null;
  independent_pct: number | null;
  women_pct: number | null;
  foreign_pct: number | null;
  available_years: number[];
}

export interface GovernanceDataEditPayload {
  company_id: string;
  year: number;
  board_size?: number | null;
  independent_directors_count?: number | null;
  women_directors_count?: number | null;
  foreign_directors_count?: number | null;
  avg_age?: number | null;
  has_audit_committee?: boolean | null;
  has_remuneration_committee?: boolean | null;
  has_nomination_committee?: boolean | null;
  has_strategy_committee?: boolean | null;
  has_anticorr_committee?: boolean | null;
  has_procurement_committee?: boolean | null;
  has_esg_committee?: boolean | null;
  has_dno_insurance?: boolean | null;
  has_induction_program?: boolean | null;
  meetings_per_year?: number | null;
  avg_attendance_pct?: number | null;
  notes?: string | null;
}

export interface BoardMemberCreatePayload {
  company_id: string;
  full_name: string;
  position?: string | null;
  role_type?: RoleType | null;
  is_independent?: boolean | null;
  is_woman?: boolean | null;
  is_foreign?: boolean | null;
  appointed_date?: string | null;
  term_end_date?: string | null;
  email?: string | null;
  phone?: string | null;
  bio?: string | null;
}

export type BoardMemberUpdatePayload = Partial<Omit<BoardMemberCreatePayload, "company_id">>;

// ---------------------------------------------------------------------
// Committee meetings — КОЛИЧЕСТВО заседаний НС/комитетов по периодам
// ---------------------------------------------------------------------

/** Поля-счётчики ячеек (whitelist; совпадает с backend COMMITTEE_MEETING_FIELDS). */
export type CommitteeMeetingField =
  | "sb_meetings"
  | "sb_decisions"
  | "audit_mtg"
  | "strategy_mtg"
  | "nomrem_mtg"
  | "anticorr_mtg";

export interface CommitteeMeetingPeriod {
  year: number;
  quarter: number | null;   // null = годовой/полный период; 1..4 = квартал
  label: string;            // "2025" | "2026 · Q1"
}

export interface CommitteeMeetingCell {
  sb_meetings: number | null;
  sb_decisions: number | null;
  audit_mtg: number | null;
  strategy_mtg: number | null;
  nomrem_mtg: number | null;
  anticorr_mtg: number | null;
}

export interface CommitteeMeetingCompanyRow {
  company_id: string;
  name: string | null;
  name_short: string | null;
  sector_code: string | null;
  cells: Record<string, CommitteeMeetingCell>;   // ключ "<year>:<quarter|0>"
}

export interface CommitteeMeetingsResponse {
  periods: CommitteeMeetingPeriod[];
  companies: CommitteeMeetingCompanyRow[];
}

export interface CommitteeMeetingUpsertPayload {
  company_id: string;
  year: number;
  quarter: number | null;
  field: CommitteeMeetingField;
  value: number | null;
}

export interface CommitteeMeetingUpsertResult {
  company_id: string;
  year: number;
  quarter: number | null;
  cell: CommitteeMeetingCell;
}

// ---------------------------------------------------------------------
// API
// ---------------------------------------------------------------------

export const governanceApi = {
  async getOverview(params: { year?: number; sector_code?: string; rankings_limit?: number } = {}) {
    const r = await api.get<GovernanceOverviewResponse>("/governance/overview", { params });
    return r.data;
  },

  async getCompanyDetail(companyId: string, year?: number) {
    const r = await api.get<GovernanceCompanyDetail>(
      `/governance/companies/${companyId}`,
      { params: year ? { year } : {} },
    );
    return r.data;
  },

  async upsertData(payload: GovernanceDataEditPayload): Promise<GovernanceDataBrief | ModerationQueuedTag> {
    const r = await api.put<GovernanceDataBrief | ModerationQueuedTag>("/governance/data", payload);
    return r.data;
  },

  async listMembers(companyId: string, includePast = false) {
    const r = await api.get<BoardMemberBrief[]>(
      `/governance/companies/${companyId}/members`,
      { params: { include_past: includePast } },
    );
    return r.data;
  },

  async createMember(payload: BoardMemberCreatePayload): Promise<BoardMemberBrief | ModerationQueuedTag> {
    const r = await api.post<BoardMemberBrief | ModerationQueuedTag>("/governance/member", payload);
    return r.data;
  },

  async updateMember(memberId: string, payload: BoardMemberUpdatePayload): Promise<BoardMemberBrief | ModerationQueuedTag> {
    const r = await api.patch<BoardMemberBrief | ModerationQueuedTag>(`/governance/member/${memberId}`, payload);
    return r.data;
  },

  async deleteMember(memberId: string) {
    await api.delete(`/governance/member/${memberId}`);
  },

  // ─── Committee meetings (кол-во заседаний по периодам) ─────────

  async getCommitteeMeetings(): Promise<CommitteeMeetingsResponse> {
    const r = await api.get<CommitteeMeetingsResponse>("/governance/committee-meetings");
    return r.data;
  },

  async putCommitteeMeeting(payload: CommitteeMeetingUpsertPayload): Promise<CommitteeMeetingUpsertResult> {
    const r = await api.put<CommitteeMeetingUpsertResult>("/governance/committee-meetings", payload);
    return r.data;
  },

  async addCommitteePeriod(year: number, quarter: number | null): Promise<{ ok: boolean; period: CommitteeMeetingPeriod }> {
    const r = await api.post<{ ok: boolean; period: CommitteeMeetingPeriod }>(
      "/governance/committee-meetings/period",
      { year, quarter },
    );
    return r.data;
  },
};

// ---------------------------------------------------------------------
// Display helpers
// ---------------------------------------------------------------------

export function roleTypeMeta(r: RoleType | string | null | undefined): { label: string; color: string } {
  if (!r) return { label: "—", color: "#94A3B8" };
  const m = ROLE_TYPE_META.find((x) => x.key === r);
  return m ? { label: m.label, color: m.color } : { label: String(r), color: "#94A3B8" };
}

/** Color for governance_score 0-100. */
export function scoreColor(s: number | null | undefined): string {
  if (s == null) return "#94A3B8";
  if (s >= 75) return "#1D9E75";
  if (s >= 50) return "#7DC4A0";
  if (s >= 25) return "#EF9F27";
  return "#E24B4A";
}

/** Color for diversity %. Independence target 33%, women 20%, foreign 10%. */
export function diversityColor(pct: number | null | undefined, target: number): string {
  if (pct == null) return "#94A3B8";
  if (pct >= target) return "#1D9E75";
  if (pct >= target * 0.6) return "#EF9F27";
  return "#E24B4A";
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (!m) return iso;
  return `${m[3]}.${m[2]}.${m[1]}`;
}
