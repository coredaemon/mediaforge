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
  imdb_id: string | null;
  tvdb_id: number | null;
  wikidata_id: string | null;
  localized_title: string | null;
  localized_overview: string | null;
  tmdb_original_title: string | null;
  poster_path: string | null;
  backdrop_path: string | null;
  poster_url: string | null;
  backdrop_url: string | null;
  metadata_language: string | null;
  reused_from_memory: boolean;
  memory_status: string | null;
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
  review_decision: string;
  reviewed_at: string | null;
  review_note: string | null;
  manual_title: string | null;
  manual_year: number | null;
  manual_tmdb_id: number | null;
  manual_imdb_id: string | null;
  manual_tvdb_id: number | null;
  manual_media_type: string | null;
  sidecar_title: string | null;
  sidecar_original_title: string | null;
  sidecar_year: number | null;
  sidecar_overview: string | null;
  sidecar_tmdb_id: number | null;
  sidecar_imdb_id: string | null;
  sidecar_tvdb_id: number | null;
  sidecar_source_path: string | null;
  sidecar_poster_path: string | null;
  sidecar_backdrop_path: string | null;
  sidecar_metadata_status: string | null;
  local_poster_path: string | null;
  local_backdrop_path: string | null;
  local_logo_path: string | null;
  match_source: string | null;
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
  poster_url: string | null;
  backdrop_url: string | null;
  imdb_id: string | null;
  tvdb_id: number | null;
  wikidata_id: string | null;
  metadata_language: string | null;
  overview_is_fallback: boolean;
  vote_average: number | null;
  popularity: number | null;
  score: number;
  is_selected: boolean;
  created_at: string;
}

export interface TmdbSearchResult {
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
  raw_json: Record<string, unknown> | null;
}

export interface TvEpisode {
  id: number;
  show_id: number;
  season_id: number | null;
  source_file_id: number | null;
  season_number: number;
  episode_number: number;
  absolute_number: number | null;
  title: string | null;
  overview: string | null;
  air_date: string | null;
  tmdb_episode_id: number | null;
  source_path: string | null;
  target_path: string | null;
  confidence: number | null;
  needs_review: boolean;
  issue: string | null;
  warning: string | null;
  match_source: string | null;
  created_at: string;
  updated_at: string;
}

export interface TvSeason {
  id: number;
  show_id: number;
  season_number: number;
  title: string | null;
  tmdb_season_id: number | null;
  episode_count: number | null;
  poster_path: string | null;
  poster_url: string | null;
  episodes: TvEpisode[];
  created_at: string;
  updated_at: string;
}

export interface TvShow {
  id: number;
  scan_session_id: number;
  local_group_id: string | null;
  title: string;
  original_title: string | null;
  year: number | null;
  first_air_date: string | null;
  tmdb_id: number | null;
  imdb_id: string | null;
  tvdb_id: number | null;
  wikidata_id: string | null;
  overview: string | null;
  poster_path: string | null;
  poster_url: string | null;
  backdrop_path: string | null;
  backdrop_url: string | null;
  language: string | null;
  match_source: string | null;
  confidence: number | null;
  review_decision: string;
  needs_review: boolean;
  ai_reasoning_summary: string | null;
  warnings: string[] | null;
  seasons: TvSeason[];
  created_at: string;
  updated_at: string;
}

export interface TvAnalyzeResult {
  scan_session_id: number;
  show_count: number;
  season_count: number;
  episode_count: number;
  warning_count: number;
}

export interface TvManualSearchRequest {
  query: string;
  year?: number | null;
}

export interface TvManualLookupRequest {
  tmdb_id?: number | null;
  imdb_id?: string | null;
  tvdb_id?: number | null;
  select?: boolean;
}

export interface TvReviewDecisionRequest {
  decision: string;
  note?: string | null;
  manual_title?: string | null;
  manual_year?: number | null;
  manual_tmdb_id?: number | null;
  manual_imdb_id?: string | null;
  manual_tvdb_id?: number | null;
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
  cloud_primary_configured: boolean;
  cloud_fallback_configured: boolean;
  cloud_ai_provider: string | null;
  cloud_ai_base_url: string | null;
  cloud_ai_model: string | null;
  cloud_ai_fallback_provider: string | null;
  cloud_ai_fallback_model: string | null;
  openrouter_configured: boolean;
  openrouter_base_url: string | null;
  openrouter_fast_chain: string[];
  openrouter_smart_chain: string[];
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
  cloud_ai_base_url?: string | null;
  cloud_ai_model?: string | null;
  cloud_ai_fallback_provider?: string | null;
  cloud_ai_fallback_api_key?: string | null;
  cloud_ai_fallback_model?: string | null;
  openrouter_api_key?: string | null;
  openrouter_base_url?: string | null;
  openrouter_fast_chain?: string[] | null;
  openrouter_smart_chain?: string[] | null;
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
  validation_status?: string;
  validation_error?: string | null;
  validated_at?: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface BulkApproveRequest {
  scope: "matched" | "selected";
  item_ids?: number[];
}

export interface BulkReviewDecisionRequest {
  item_ids: number[];
  decision: "approved" | "ignored" | "deferred";
  note?: string | null;
}

export interface BulkReviewResult {
  approved_count: number;
  skipped_count: number;
  ignored_count: number;
  deferred_count: number;
}

export interface PlanValidationResult {
  ok_count: number;
  warning_count: number;
  conflict_count: number;
  operations: PlanOperation[];
}

export interface PlanApplyRequest {
  confirm: boolean;
}

export interface PlanApplyResult {
  plan_id: number;
  apply_run_id: number;
  status: string;
  total_operations: number;
  done_operations: number;
  failed_operations: number;
  error_message: string | null;
}

export interface ApplyOperationLog {
  id: number;
  apply_run_id: number;
  plan_operation_id: number;
  operation_type: string;
  status: string;
  source_path: string | null;
  target_path: string | null;
  error_message: string | null;
  started_at: string | null;
  finished_at: string | null;
  rollback_data: Record<string, unknown> | null;
}

export interface ApplyRun {
  id: number;
  operation_plan_id: number;
  started_at: string;
  finished_at: string | null;
  status: string;
  total_operations: number;
  done_operations: number;
  failed_operations: number;
  error_message: string | null;
  logs: ApplyOperationLog[];
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
  human_message?: string | null;
  attempts?: number;
  attempted_models?: {
    model: string;
    ok: boolean;
    duration_ms: number;
    error?: string | null;
    human_message?: string | null;
    response_valid_json?: boolean;
  }[];
  retryable?: boolean;
}

export interface RecognitionPreflightResult {
  ok: boolean;
  local: LlmPreflightCheck;
  cloud: LlmPreflightCheck;
  cloud_fallback?: LlmPreflightCheck | null;
  warning?: string | null;
  message?: string | null;
}

export interface ReviewDecisionRequest {
  decision: string;
  note?: string | null;
  manual_title?: string | null;
  manual_year?: number | null;
  manual_tmdb_id?: number | null;
  manual_imdb_id?: string | null;
  manual_tvdb_id?: number | null;
  manual_media_type?: string | null;
}

export interface TmdbManualSearchRequest {
  query: string;
  year?: number | null;
  media_type?: string;
  language?: string;
}

export interface TmdbManualLookupRequest {
  tmdb_id?: number | null;
  imdb_id?: string | null;
  tvdb_id?: number | null;
  media_type?: string | null;
}

export interface CloudModel {
  id: string;
  label: string;
  display_name: string | null;
  description: string | null;
  context_length?: number | null;
  pricing?: Record<string, unknown> | null;
  provider?: string | null;
  is_free?: boolean | null;
  supported_generation_methods: string[];
}

export interface CloudModelsResult {
  success: boolean;
  models: CloudModel[];
  message: string | null;
}

export interface CloudModelsRequest {
  provider: string;
  api_key?: string | null;
  base_url?: string | null;
}

export interface CloudAiTestRequest {
  provider: string;
  model: string;
  models?: string[] | null;
  stage?: string | null;
  api_key?: string | null;
  base_url?: string | null;
}

export interface ExtensionCount {
  extension: string;
  count: number;
}

export interface MediaClassificationResult {
  scan_session_id: number;
  content_type: "movies" | "tv" | "mixed" | "unknown";
  confidence: number;
  reason: string;
  total_files: number;
  video_files: number;
  subtitle_files: number;
  sidecar_files: number;
  nested_folder_count: number;
  known_extensions: ExtensionCount[];
  ignored_extensions: ExtensionCount[];
  movie_like_files: number;
  tv_like_files: number;
  mixed: boolean;
  needs_user_decision: boolean;
  warnings: string[];
}
