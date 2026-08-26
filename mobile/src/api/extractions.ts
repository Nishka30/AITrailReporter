import { apiRequest } from './client';

/** Mirrors the backend's extraction state machine EXACTLY (see
 * backend/app/db/models/extraction.py) — a THIRD state machine, independent of
 * both SyncStatus ("did the server receive this?") and TranscriptionStatus
 * ("did AI turn audio into text?"). This one answers "did LLM processing turn
 * the resolved source text into structured observations?" */
export type ExtractionStatus = 'pending' | 'processing' | 'completed' | 'failed';

export interface ObservationResult {
  id: string;
  knowledgeType: string;
  value: Record<string, unknown>;
  confidence: number | null;
  evidence: string | null;
}

export interface ExtractionResponse {
  id: string;
  submissionId: string;
  status: ExtractionStatus;
  errorMessage: string | null;
  observations: ObservationResult[];
}

interface ObservationResultWire {
  id: string;
  knowledge_type: string;
  value: Record<string, unknown>;
  confidence: number | null;
  evidence: string | null;
}

interface ExtractionResponseWire {
  id: string;
  submission_id: string;
  status: string;
  error_message: string | null;
  observations: ObservationResultWire[];
}

function fromWire(wire: ExtractionResponseWire): ExtractionResponse {
  return {
    id: wire.id,
    submissionId: wire.submission_id,
    status: wire.status as ExtractionStatus,
    errorMessage: wire.error_message,
    observations: wire.observations.map((o) => ({
      id: o.id,
      knowledgeType: o.knowledge_type,
      value: o.value,
      confidence: o.confidence,
      evidence: o.evidence,
    })),
  };
}

/**
 * POST /api/v1/submissions/{submissionId}/extract. Starts extraction if none is
 * running yet, or simply reports the current state (without a second LLM call)
 * if one is already 'processing' or already 'completed' — see
 * backend/README.md. Always resolves with the current true state; never
 * fabricates observations.
 */
export async function triggerExtraction(submissionId: string): Promise<ExtractionResponse> {
  const wire = await apiRequest<ExtractionResponseWire>(
    `/api/v1/submissions/${submissionId}/extract`,
    { method: 'POST' }
  );
  return fromWire(wire);
}
