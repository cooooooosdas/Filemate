export interface GraphNodeDraft {
  id: string
  label: string
  source_id: string
  source_name?: string
  excerpt: string
  chunk_id: string | null
  page_number: number | null
}

export interface GraphNode extends GraphNodeDraft {
  metrics: {
    status: string
    sample_count: number
    correct_rate: number | null
    wrong_count: number
    last_reviewed_at: string | null
    confidence: '待评测' | '样本较少' | '有练习证据'
    study_time: null
    recent_sample_count: number
    days_since_review: number | null
    pending_wrong_count: number
    excluded_sample_count: number
  }
  questions: { artifact_id: string; question_index: number; question: string; read_only_snapshot?: boolean }[]
  wrong_ids: string[]
}

export interface GraphEdge { from: string; to: string; relation: string; excerpt: string }
export interface GraphBatch {
  batch_id: string
  source_id: string
  status: 'draft' | 'confirmed' | 'undone' | 'failed'
  mode: 'local' | 'llm'
  created_at: string
  updated_at: string
  error_code: string | null
  stale: boolean
  data_error: boolean
  payload: { nodes: GraphNodeDraft[]; edges: GraphEdge[] }
}
export interface KnowledgeGraphData {
  nodes: GraphNode[]
  edges: GraphEdge[]
  batches: GraphBatch[]
  plans: { plan_id: string; source_id: string; title: string; status: 'active' | 'completed' | 'archived'; updated_at: string }[]
  relations: Record<string, string>
  updated_at: string
  profile: {
    node_count: number
    observed_node_count: number
    unassessed_node_count: number
    attempt_count: number
    pending_wrong_count: number
    excluded_sample_count: number
    study_time: null
    status_counts: Record<string, number>
    weaknesses: {
      node_id: string; label: string; source_id: string; reasons: string[]
      prerequisites: { node_id: string; label: string; relation: string; excerpt: string }[]
    }[]
  }
  events: { event_id: number; source_id: string; target_id: string; action: string; created_at: string }[]
}
export interface GraphPlanPreview {
  node_id: string
  title: string
  source_id: string
  steps: { node_id: string; label: string; reason: string }[]
  evidence_revision: string
}
export interface GraphPlanResult { plan_id: string; artifact_id: string }
