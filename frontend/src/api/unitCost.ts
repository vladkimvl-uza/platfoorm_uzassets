import { api } from "@/api/client";

export const FUELS = ["electricity", "gas", "diesel", "mazut", "coal", "kerosene"] as const;
export type Fuel = typeof FUELS[number];

export interface EnergyBreakdown { fuel: string; label: string; norm: number; cost: number }
export interface CostComponent { name: string; value: number }
export interface UCProduct {
  name: string; unit: string; output: number;
  energy_cost: number; components_cost: number; unit_cost: number;
  energy_share: number | null; total_cost: number | null;
  energy_breakdown: EnergyBreakdown[]; energy: Record<string, number>;
  components: CostComponent[]; has_energy: boolean;
}
export interface UCImport { name: string; unit: string; usd: number; qty: number; cost: number }
export interface UCCompany {
  code: string; name: string; sector: string; color: string;
  product_count: number; priced_count: number;
  total_cost: number | null; energy_cost: number | null; energy_share: number | null;
  import_cost: number | null; imports: UCImport[];
  products: UCProduct[];
}
export interface UCPriceEntry { price?: number; unit: string; usd?: number }
export interface UCPrices { [fuel: string]: UCPriceEntry }
export interface UCWorld { usd_rate: number; brent: number; gold: number; copper: number }
export interface EnergyMix { fuel: string; label: string; cost: number; share: number }
export interface UCOverview {
  energyPrices: UCPrices;
  world: UCWorld;
  fuel_labels: Record<string, string>;
  companies: UCCompany[];
  energy_mix: EnergyMix[];
  portfolio: {
    total_cost: number | null; energy_cost: number | null; components_cost: number | null;
    import_cost: number | null; energy_share: number | null;
    company_count: number; product_count: number; priced_count: number;
  };
  generated_at: string;
}

// сырьё для редактора (то, что храним, а не считаем)
export interface EditProduct {
  name: string; unit: string; output: number;
  energy: Record<string, number | null>;
  components: CostComponent[];
}
export interface EditImport { name: string; unit: string; usd: number; qty: number }

export const unitCostApi = {
  async overview(): Promise<UCOverview> {
    return (await api.get<UCOverview>("/unit-cost/overview")).data;
  },
  async savePrices(prices: UCPrices, world: Partial<UCWorld>): Promise<unknown> {
    return (await api.put("/unit-cost/prices", { prices, world })).data;
  },
  async saveCompany(code: string, products: EditProduct[], imports: EditImport[]): Promise<unknown> {
    return (await api.put(`/unit-cost/companies/${code}`, { products, imports })).data;
  },
};
