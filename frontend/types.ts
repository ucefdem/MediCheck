export interface Entity {
  text: string;
  label: string;
  score: number;
  start: number;
  end: number;
}

export type EntityMap = Record<string, string[]>;

export interface ExtractionResult {
  entities: EntityMap;
  latency_ms: number;
  provider?: string | null;
}

export interface TavilyCard {
  drug: string;
  indication: string;
  contraindications: string;
  warning?: string | null;
  source?: string;
}

export interface TriageResponse {
  pioneer: ExtractionResult;
  openai: ExtractionResult;
  tavily_cards: TavilyCard[];
  transcript: string;
  winner?: string;
}
