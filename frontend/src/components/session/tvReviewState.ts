import type { TvShow } from "../../types";

export type TvReviewState = "included" | "needs_review" | "ignored" | "deferred" | "manual_override";

export function tvShowReviewState(show: TvShow): TvReviewState {
  if (show.review_decision === "ignored") return "ignored";
  if (show.review_decision === "deferred") return "deferred";
  if (show.review_decision === "manual_override") return "manual_override";
  if (show.needs_review || show.seasons.some((season) => season.episodes.some((episode) => episode.needs_review))) {
    return "needs_review";
  }
  return "included";
}
