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
  ai_clean_title: string | null;
  ai_year: number | null;
  ai_media_type: string | null;
  ai_confidence: number | null;
  ai_junk_tokens: string[] | null;
  ai_explanation: string | null;
  gemini_clean_title: string | null;
  gemini_year: number | null;
  gemini_media_type: string | null;
  gemini_confidence: number | null;
  gemini_junk_tokens: string[] | null;
  gemini_explanation: string | null;
  tmdb_queries: string[] | null;
  local_ai_status: string | null;
  local_ai_duration_ms: number | null;
  local_ai_error: string | null;
  local_ai_response_valid_json: boolean | null;
  local_ai_model: string | null;
  gemini_status: string | null;
  gemini_duration_ms: number | null;
  gemini_error: string | null;
  gemini_response_valid_json: boolean | null;
  gemini_model: string | null;
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

export interface RecognitionNormalizeResult {
  scan_session_id: number;
  normalized_count: number;
  skipped_count: number;
  error_count: number;
}

export interface RecognitionCorrectionCreate {
  corrected_title: string;
  corrected_year?: number | null;
  corrected_media_type?: string | null;
  removed_tokens?: string[];
  confidence?: number | null;
}

export interface RecognitionCorrection {
  id: number;
  media_item_id: number;
  original_title: string | null;
  previous_title: string | null;
  corrected_title: string;
  corrected_year: number | null;
  corrected_media_type: string | null;
  removed_tokens: string[];
  confidence: number | null;
  created_at: string;
}

export interface RecognitionTokenRule {
  id: number;
  token: string;
  action: string;
  source: string;
  hit_count: number;
  created_at: string;
  updated_at: string;
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

export interface AppSettingsRead {
  tmdb_configured: boolean;
  ai_configured: boolean;
  ai_provider: string | null;
  ai_base_url: string | null;
  ai_model: string | null;
  cloud_ai_configured: boolean;
  cloud_ai_provider: string | null;
  cloud_ai_model: string | null;
  recognition_ai_enabled: boolean;
  default_source_path: string | null;
  default_target_path: string | null;
  setup_completed: boolean;
  updated_at: string;
}

export interface AppSettingsUpdate {
  tmdb_api_key?: string | null;
  ai_provider?: string | null;
  ai_api_key?: string | null;
  ai_base_url?: string | null;
  ai_model?: string | null;
  cloud_ai_provider?: string | null;
  cloud_ai_api_key?: string | null;
  cloud_ai_model?: string | null;
  recognition_ai_enabled?: boolean | null;
  default_source_path?: string | null;
  default_target_path?: string | null;
  setup_completed?: boolean | null;
}

export interface TestConnectionResult {
  success: boolean;
  message: string;
}

export interface LocalModelsResult {
  success: boolean;
  models: string[];
  message: string | null;
}

export interface DirectoryEntry {
  name: string;
  path: string;
}

export interface BrowseResult {
  current_path: string;
  parent_path: string | null;
  directories: DirectoryEntry[];
  readable: boolean;
  error: string | null;
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

export interface LlmPreflightCheck {
  ok: boolean;
  provider: string | null;
  model: string | null;
  endpoint: string | null;
  duration_ms: number;
  response_valid_json: boolean;
  response_had_markdown: boolean;
  response_preview: string | null;
  message: string | null;
  error: string | null;
  error_type: string | null;
}

export interface RecognitionPreflightResult {
  ok: boolean;
  local: LlmPreflightCheck;
  cloud: LlmPreflightCheck;
}
