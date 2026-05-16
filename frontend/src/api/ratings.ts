import { api } from "./client";

export interface AgencyRatingBrief {
  id: string;
  company_id: string;
  company_code: string | null;
  company_name: string | null;
  agency: string;
  is_esg: boolean;
  rating: string | null;
  outlook: string | null;
  score: string | null;
  rating_date_text: string | null;
  rating_date: string | null;
  report_url: string | null;
  created_at: string;
  updated_at: string;
}

export interface AgencyRatingListResponse {
  items: AgencyRatingBrief[];
  total: number;
  by_agency: Record<string, number>;
  by_company: Record<string, number>;
  credit_count: number;
  esg_count: number;
}

export interface CompanyRatingsResponse {
  company_id: string;
  company_code: string;
  company_name: string;
  credit: AgencyRatingBrief[];
  esg: AgencyRatingBrief[];
}

export interface AgencyRatingListQuery {
  company_id?: string;
  company_code?: string;
  agency?: string;
  is_esg?: boolean;
  search?: string;
  sort_by?: "rating_date" | "agency" | "company_code" | "updated_at";
  sort_dir?: "asc" | "desc";
  limit?: number;
  offset?: number;
}

export const ratingsApi = {
  async list(query: AgencyRatingListQuery = {}) {
    const { data } = await api.get<AgencyRatingListResponse>("/ratings", { params: query });
    return data;
  },
  async getCompanyRatings(code: string) {
    const { data } = await api.get<CompanyRatingsResponse>(`/companies/${code}/ratings`);
    return data;
  },
  async create(payload: {
    company_id: string; agency: string;
    rating?: string; outlook?: string; score?: string;
    rating_date_text?: string; rating_date?: string;
    report_url?: string;
  }) {
    const { data } = await api.post<AgencyRatingBrief>("/ratings", payload);
    return data;
  },
  async update(id: string, payload: Partial<AgencyRatingBrief>) {
    const { data } = await api.patch<AgencyRatingBrief>(`/ratings/${id}`, payload);
    return data;
  },
  async remove(id: string) {
    await api.delete(`/ratings/${id}`);
  },
};
