import { api } from "./client";

export interface CalendarEvent {
  entity_type: "project" | "task";
  entity_id: string;
  num: string | null;
  title: string;
  status: string;
  due_date: string | null;
  company_id: string | null;
  company_name: string | null;
  current_health: string | null;
}

export const calendarApi = {
  async events(from: string, to: string, companyId?: string): Promise<CalendarEvent[]> {
    const { data } = await api.get<CalendarEvent[]>("/calendar/events", {
      params: { from, to, company_id: companyId },
    });
    return data;
  },
  // Персональный iCal-токен + относительный путь фида.
  async icalToken(): Promise<{ token: string; path: string }> {
    const { data } = await api.post<{ token: string; path: string }>("/calendar/ical-token");
    return data;
  },
};
