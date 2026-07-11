import { useReducer } from "react";

export type StepStatus = "pending" | "running" | "done" | "error";

export const initialPipelineStatus: Record<string, StepStatus> = {
  preflight: "pending",
  discover: "pending",
  classification: "pending",
  parse: "pending",
  "local-ai": "pending",
  match: "pending",
  gemini: "pending",
  tv: "pending",
  "tv-plan": "pending",
  plan: "pending",
};

type PipelineAction =
  | { type: "replace"; status: Record<string, StepStatus> }
  | { type: "set"; key: string; status: StepStatus };

function pipelineReducer(
  state: Record<string, StepStatus>,
  action: PipelineAction,
): Record<string, StepStatus> {
  if (action.type === "replace") {
    return { ...action.status };
  }
  return { ...state, [action.key]: action.status };
}

export function useSessionPipeline() {
  const [stepStatus, dispatch] = useReducer(pipelineReducer, initialPipelineStatus);

  return {
    stepStatus,
    setStepStatus: (status: Record<string, StepStatus>) => dispatch({ type: "replace", status }),
    setStep: (key: string, status: StepStatus) => dispatch({ type: "set", key, status }),
  };
}
