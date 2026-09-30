export type Incident = { id:string; title:string; affected_service:string; severity:string; status:string; keyterms:string[]; is_demo:boolean; started_at:string };
export type TimelineEvent = { id:string; event_type:string; summary:string; subject?:string; claim_value?:string; source_type:string; confidence:number; owner?:string; created_at:string };
export type Evidence = { id:string; source_name:string; source_url?:string; excerpt:string; retrieved_at:string; is_simulated:boolean };
export type Contradiction = { id:string; reason:string; confidence:number; status:string; resolution_note?:string|null; earlier_statement:string; later_statement:string };
export type Update = { id:string; content:string; status:string; approved_by?:string; created_at:string };
export type IncidentData = { incident:Incident; timeline:TimelineEvent[]; evidence:Evidence[]; contradictions:Contradiction[]; updates:Update[] };

