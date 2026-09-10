import type { IncidentData, Incident } from "./types";

export const API = import.meta.env.VITE_API_URL || "";

async function request<T>(path:string, init?:RequestInit):Promise<T> {
  const response = await fetch(`${API}${path}`, { headers:{"Content-Type":"application/json", ...(init?.headers||{})}, ...init });
  if (!response.ok) { const body = await response.json().catch(()=>({detail:response.statusText})); throw new Error(body.detail?.recovery || body.detail?.code || body.detail || "Request failed"); }
  return response.json();
}
export const getIncident = (id:string) => request<IncidentData>(`/api/incidents/${id}`);
export const createIncident = (body:object) => request<Incident>("/api/incidents", {method:"POST",body:JSON.stringify(body)});
export const startDemo = () => request<Incident>("/api/demo/start", {method:"POST"});
export const callTool = <T>(path:string, body:object, grant:string) => request<T>(`/api/tools/${path}`, {method:"POST",headers:{Authorization:`Bearer ${grant}`},body:JSON.stringify(body)});

