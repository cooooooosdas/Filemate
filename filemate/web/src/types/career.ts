import type { GraphNode } from "./knowledgeGraph";
export interface CareerRequirement {
  label: string;
  category: "programming" | "knowledge" | "project" | "communication";
  evidence: string;
}
export interface CareerPosition {
  company: string;
  industry: string;
  region: string;
  title: string;
  employment: "校招" | "实习" | "社招参考" | "用户自定义";
  description: string;
  requirements: CareerRequirement[];
  source: string;
  source_url: string;
  source_kind: "official_snapshot" | "user_import";
  collected_at: string;
  published_at: string;
}
export interface CareerRecord {
  position_id: string;
  revision: number;
  active: number;
  created_at: string;
  updated_at: string;
  age_days: number | null;
  position: CareerPosition | null;
  data_error: boolean;
}
export interface CareerProblem {
  id: string;
  title: string;
  tags: string[];
  difficulty: string;
  version: number;
  reason: string;
}
export interface CareerComparison {
  position_id: string;
  position_revision: number;
  mapping_method: string;
  purpose: string;
  skills: (CareerRequirement & {
    status: string;
    recent_graph_samples: number;
    coding_count: number;
    coding_ac_count: number;
    written_count: number;
    written_correct_count: number;
    notes: string[];
    graph_nodes: {
      id: string;
      label: string;
      source_id: string;
      metrics: GraphNode["metrics"];
    }[];
    coding_evidence: {
      submission_id: string;
      problem_id: string;
      verdict: string;
      created_at: string;
    }[];
  })[];
  written: {
    training_id: string;
    correct: number;
    total: number;
    correct_rate: number;
    submitted_at: string;
  }[];
  interviews: {
    training_id: string;
    interview_id: string;
    answered: number;
    assessed: number;
    status: string;
  }[];
  recommended_problems: CareerProblem[];
}
export interface CareerTraining {
  training_id: string;
  position_id: string;
  kind: "written" | "interview" | "review";
  artifact_id: string;
  interview_id: string | null;
  created_at: string;
  data_error: boolean;
  payload: {
    version: string;
    position: CareerPosition;
    position_revision: number;
    comparison?: CareerComparison;
    problems?: CareerProblem[];
    questions?: {
      id: string;
      skill: string;
      question: string;
      options: string[];
      correct?: number;
      explanation?: string;
    }[];
    result?: {
      answers: Record<string, number>;
      correct: number;
      total: number;
      correct_rate: number;
      submitted_at: string;
    } | null;
  } | null;
}
export interface CareerEvent {
  event_id: number;
  position_id: string | null;
  training_id: string | null;
  action: string;
  detail: string;
  created_at: string;
}
