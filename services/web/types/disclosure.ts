export type Chamber = "House" | "Senate" | "Both" | "Combined";

export type ActionType = "Purchase" | "Sale" | "Exchange" | "Unknown";

export interface DisclosureRecord {
  id: string | number;
  filer_name: string;
  chamber: "House" | "Senate";
  filed_date: string;
  trade_date: string;
  ticker?: string | null;
  asset_name: string;
  action: string;
  value_range: string;
  ownership?: string | null;
  comment?: string | null;
  doc_id?: string | null;
  days_late?: number | null;
  is_late?: boolean;
}

export interface LateFilingAlert {
  filer_name: string;
  chamber: "House" | "Senate";
  trade_date: string;
  filed_date: string;
  days_to_disclose: number;
  ticker: string | null;
  asset_name: string;
  amount: string;
  late_status: "Critical" | "Warning" | "Moderate";
}

export interface CommitteeConflictItem {
  member_name: string;
  chamber: "House" | "Senate";
  committee: string;
  sector: string;
  ticker: string;
  asset_name: string;
  trade_count: number;
  total_volume_estimate: string;
  flag_type: "Direct Conflict" | "Potential Influence" | "Monitored";
}

export interface SearchFilterState {
  ticker?: string;
  filer_name?: string;
  action?: string;
  chamber?: Chamber;
  start_date?: string;
  end_date?: string;
  limit?: number;
  offset?: number;
}
