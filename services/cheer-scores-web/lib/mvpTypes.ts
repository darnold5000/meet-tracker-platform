export type MvpTeamHit = {
  id: number;
  name: string;
  gym_name: string | null;
  level: string | null;
  division: string | null;
};

export type MvpMeetHit = {
  meet_key: string;
  name: string;
  location: string | null;
  start_date: string | null;
  end_date: string | null;
  starts_at?: string | null;
  ends_at?: string | null;
};

export type MvpSearchResponse = {
  q: string;
  teams: MvpTeamHit[];
  meets: MvpMeetHit[];
  /** Distinct gyms that appear in scored performances (empty search only). */
  gym_names?: string[];
};

export type MvpUpcomingMeetsResponse = {
  limit: number;
  meets: MvpMeetHit[];
};

export type MvpMeetSummary = {
  id: number;
  meet_key: string;
  name: string;
  location: string | null;
  start_date: string | null;
  end_date: string | null;
  starts_at?: string | null;
  ends_at?: string | null;
  source: string | null;
};

export type MvpSessionRow = {
  id: number;
  name: string;
  display_order: number;
  start_time: string | null;
};

export type MvpTimelineItem = {
  performance_id: number;
  display_order: number;
  scheduled_time: string | null;
  actual_time: string | null;
  status: string;
  is_break: boolean;
  break_label: string | null;
  round: string | null;
  final_score: number | null;
  raw_score: number | null;
  performance_score: number | null;
  rank: number | null;
  deductions: number | null;
  team_id: number | null;
  team_name: string | null;
  team_gym_name: string | null;
  team_level: string | null;
  team_division: string | null;
  session_id: number;
  session_name: string;
  session_display_order: number;
};

export type MvpTimelineResponse = {
  meet_key: string;
  meet: MvpMeetSummary;
  sessions: MvpSessionRow[];
  items: MvpTimelineItem[];
};

export type MvpResultRow = {
  rank: number | null;
  final_score: number;
  raw_score: number | null;
  performance_score: number | null;
  deductions: number | null;
  scheduled_time: string | null;
  actual_time: string | null;
  team_name: string;
  team_gym_name: string | null;
  team_level: string | null;
  team_division: string | null;
  session_name: string;
  session_id: number;
  round: string | null;
};

export type MvpResultsResponse = {
  meet_key: string;
  meet: MvpMeetSummary;
  session_id: number | null;
  results: MvpResultRow[];
};

export type MvpRecentItem =
  | { kind: "meet"; meetKey: string; label: string }
  | { kind: "team"; teamId: number; label: string };
