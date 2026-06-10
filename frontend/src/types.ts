export interface HealthResponse {
  status: string;
  app: string;
}

export interface ScanSession {
  id: number;
  source_path: string;
  target_path: string;
  status: string;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  finished_at: string | null;
  error_message: string | null;
}

export interface ScanSessionCreate {
  source_path: string;
  target_path: string;
}

export interface MediaFile {
  id: number;
  scan_session_id: number;
  media_item_id: number | null;
  path: string;
  file_name: string;
  extension: string;
  size_bytes: number | null;
  kind: string;
  is_video: boolean;
  is_subtitle: boolean;
  is_sidecar: boolean;
  scan_error: string | null;
  created_at: string;
}

export interface MediaItem {
  id: number;
  scan_session_id: number;
  media_type: string;
  status: string;
  original_title: string | null;
  parsed_title: string | null;
  year: number | null;
  season_number: number | null;
  episode_number: number | null;
  tmdb_id: number | null;
  tmdb_media_type: string | null;
  matched_title: string | null;
  matched_year: number | null;
  match_confidence: number | null;
  confidence: number | null;
  needs_review: boolean;
  created_at: string;
  updated_at: string;
}

export interface TmdbMatchCandidate {
  id: number;
  media_item_id: number;
  tmdb_id: number;
  media_type: string;
  title: string;
  original_title: string | null;
  overview: string | null;
  release_date: string | null;
  first_air_date: string | null;
  year: number | null;
  poster_path: string | null;
  backdrop_path: string | null;
  vote_average: number | null;
  popularity: number | null;
  score: number;
  is_selected: boolean;
  created_at: string;
}

export interface TmdbMatchResult {
  scan_session_id: number;
  matched_count: number;
  needs_review_count: number;
  unmatched_count: number;
  skipped_count: number;
}

export interface OperationPlan {
  id: number;
  scan_session_id: number;
  status: string;
  created_at: string;
  updated_at: string;
  applied_at: string | null;
  rolled_back_at: string | null;
}

export interface PlanOperation {
  id: number;
  plan_id: number;
  operation_type: string;
  status: string;
  source_path: string | null;
  target_path: string | null;
  payload_json: Record<string, unknown> | null;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}
