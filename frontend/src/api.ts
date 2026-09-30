import type { IncidentData, Incident } from "./types";

export const API = import.meta.env.VITE_API_URL || "";

export async function request<T>(path:string, init?:RequestInit):Promise<T> {
  const headers = new Headers(init?.headers);
  if (!headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const response = await fetch(`${API}${path}`, { ...init, headers });
  if (!response.ok) { const body = await response.json().catch(()=>({detail:response.statusText})); throw new Error(body.detail?.recovery || body.detail?.code || body.detail || "Request failed"); }
  return response.json();
}
export const getIncident = (id:string) => request<IncidentData>(`/api/incidents/${id}`);
export const createIncident = (body:object) => request<Incident>("/api/incidents", {method:"POST",body:JSON.stringify(body)});
export const startDemo = () => request<Incident>("/api/demo/start", {method:"POST"});
export const getCapabilities = () => request<{voice_available:boolean}>("/api/capabilities");
export const callTool = <T>(path:string, body:object, grant:string) => request<T>(`/api/tools/${path}`, {method:"POST",headers:{Authorization:`Bearer ${grant}`},body:JSON.stringify(body)});

export function subscribeIncident(id:string, onRefresh:()=>void):()=>void {
  const controller = new AbortController();
  async function connect() {
    while (!controller.signal.aborted) {
      try {
        const response = await fetch(`${API}/api/incidents/${id}/stream`, {signal:controller.signal});
        if (!response.ok || !response.body) throw new Error("Incident stream unavailable");
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        while (!controller.signal.aborted) {
          const {done,value} = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, {stream:true});
          const frames = buffer.split(/\r?\n\r?\n/);
          buffer = frames.pop() || "";
          for (const frame of frames) if (frame.startsWith("event: refresh")) onRefresh();
        }
      } catch { /* Reconnect after a temporary network failure. */ }
      if (!controller.signal.aborted) await new Promise(resolve => setTimeout(resolve, 2000));
    }
  }
  void connect();
  return () => controller.abort();
}

