import { useEffect, useRef, useState } from "react";
import {
  Activity, AlertTriangle, ArrowUpRight, Check, CircleDot, Clock3,
  Database, FileWarning, Mic, Radio, ShieldCheck, Square, Users,
} from "lucide-react";
import {
  createIncident, getCapabilities, getIncident, request, startDemo, subscribeIncident,
} from "./api";
import type { Incident, IncidentData } from "./types";
import { BridgeVoice, type VoiceProposal, type VoiceState } from "./voice";

type RecentIncident = Pick<Incident, "id" | "title" | "affected_service" | "severity">;
const recentKey = "incisight:recent-incidents";

function loadRecent(): RecentIncident[] {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(recentKey) || "[]");
    if (!Array.isArray(value)) return [];
    return value.filter((item): item is RecentIncident =>
      typeof item?.id === "string" && typeof item?.title === "string" &&
      typeof item?.affected_service === "string" && typeof item?.severity === "string"
    ).slice(0, 5);
  } catch {
    return [];
  }
}

function rememberIncident(incident: Incident): RecentIncident[] {
  const recent = [
    { id: incident.id, title: incident.title, affected_service: incident.affected_service, severity: incident.severity },
    ...loadRecent().filter(item => item.id !== incident.id),
  ].slice(0, 5);
  try { localStorage.setItem(recentKey, JSON.stringify(recent)); } catch { /* Private browsing may block storage. */ }
  return recent;
}

const fmt = (date: string) => new Date(date).toLocaleTimeString([], {
  hour: "2-digit", minute: "2-digit", second: "2-digit",
});
const elapsed = (start: string) => {
  const duration = Math.max(0, Date.now() - new Date(start).getTime());
  const hours = Math.floor(duration / 36e5);
  const minutes = Math.floor(duration % 36e5 / 6e4);
  const seconds = Math.floor(duration % 6e4 / 1e3);
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
};
const message = (error: unknown) => error instanceof Error ? error.message : String(error);

function Create({
  onCreated, onResume, recent, initialError,
}: {
  onCreated: (incident: Incident) => void;
  onResume: (id: string) => Promise<void>;
  recent: RecentIncident[];
  initialError: string;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const fields = new FormData(event.currentTarget);
    try {
      const incident = await createIncident({
        title: fields.get("title"),
        affected_service: fields.get("service"),
        severity: fields.get("severity"),
        keyterms: String(fields.get("keyterms") || "").split(",").map(term => term.trim()).filter(Boolean),
      });
      onCreated(incident);
    } catch (reason) {
      setError(message(reason));
      setBusy(false);
    }
  }

  async function demo() {
    setBusy(true);
    setError("");
    try { onCreated(await startDemo()); }
    catch (reason) { setError(message(reason)); setBusy(false); }
  }

  async function resume(id: string) {
    setBusy(true);
    setError("");
    try { await onResume(id); }
    catch (reason) { setError(message(reason)); setBusy(false); }
  }

  return (
    <main className="landing">
      <section className="hero">
        <div className="brand"><span className="brandmark"><Activity /></span>INCISIGHT <small>INCIDENT INTELLIGENCE</small></div>
        <p className="eyebrow">VOICE-NATIVE INCIDENT COMMAND</p>
        <h1>Keep the incident moving.<br /><em>Keep the record honest.</em></h1>
        <p className="lede">A real-time command surface that turns conversation into an evidence-backed incident timeline—without letting automation outrun human judgment.</p>
        <div className="trust"><span><Radio /> Live voice</span><span><Database /> Evidence-backed</span><span><ShieldCheck /> Human approval</span></div>
      </section>
      <section className="create-card">
        <div className="card-head">
          <span>NEW INCIDENT</span><CircleDot />
          <h2>Open a command room</h2>
          <p>Set the context. Incisight will handle the running record.</p>
        </div>
        <form onSubmit={submit}>
          <label>INCIDENT TITLE<input name="title" placeholder="e.g. Customer login failures" required minLength={3} maxLength={160} /></label>
          <label>AFFECTED SERVICE<input name="service" placeholder="e.g. Authentication Service" required minLength={2} maxLength={120} /></label>
          <div className="form-row">
            <label>SEVERITY<select name="severity" defaultValue="SEV-2"><option>SEV-1</option><option>SEV-2</option><option>SEV-3</option></select></label>
            <label>KNOWN TERMS<input name="keyterms" placeholder="Optional, separated by commas" /></label>
          </div>
          {(error || initialError) && <p className="error" role="alert">{error || initialError}</p>}
          <button className="primary" disabled={busy}>{busy ? "OPENING…" : "OPEN INCIDENT"}<ArrowUpRight /></button>
          <button type="button" className="demo" onClick={demo} disabled={busy}>TRY GUIDED DEMO</button>
        </form>
        {recent.length > 0 && (
          <section className="recent" aria-labelledby="recent-title">
            <h3 id="recent-title">Recent incidents on this device</h3>
            <div className="recent-list">
              {recent.map(item => (
                <button type="button" key={item.id} onClick={() => resume(item.id)} disabled={busy}>
                  <span><strong>{item.title}</strong><small>{item.affected_service}</small></span>
                  <b>{item.severity}</b><ArrowUpRight aria-hidden="true" />
                </button>
              ))}
            </div>
          </section>
        )}
      </section>
    </main>
  );
}

function App() {
  const [incident, setIncident] = useState<Incident | null>(null);
  const [data, setData] = useState<IncidentData | null>(null);
  const [loadingIncident, setLoadingIncident] = useState(
    Boolean(new URLSearchParams(window.location.search).get("incident")),
  );
  const [recent, setRecent] = useState(loadRecent);
  const [voiceAvailable, setVoiceAvailable] = useState<boolean | null>(null);
  const [voiceState, setVoiceState] = useState<VoiceState>("idle");
  const [transcript, setTranscript] = useState<{ speaker: string; text: string }[]>([]);
  const [voiceProposal, setVoiceProposal] = useState<VoiceProposal | null>(null);
  const [error, setError] = useState("");
  const [pending, setPending] = useState("");
  const [confirmingUpdate, setConfirmingUpdate] = useState(false);
  const [reviewingConflict, setReviewingConflict] = useState<string | null>(null);
  const [resolutionNote, setResolutionNote] = useState("");
  const [, setTick] = useState(0);
  const voice = useRef<BridgeVoice | null>(null);

  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get("incident");
    if (!id) { setLoadingIncident(false); return; }
    let active = true;
    getIncident(id)
      .then(snapshot => {
        if (!active) return;
        setIncident(snapshot.incident);
        setData(snapshot);
        setRecent(rememberIncident(snapshot.incident));
      })
      .catch(reason => {
        if (!active) return;
        setError(`Could not reopen that incident: ${message(reason)}`);
        window.history.replaceState({}, "", "/");
      })
      .finally(() => { if (active) setLoadingIncident(false); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!incident) return;
    let active = true;
    const refreshCurrent = () => getIncident(incident.id)
      .then(snapshot => { if (active) setData(snapshot); })
      .catch(reason => { if (active) setError(message(reason)); });
    const stopStream = subscribeIncident(incident.id, () => { void refreshCurrent(); });
    const timer = setInterval(() => setTick(value => value + 1), 1000);
    getCapabilities()
      .then(result => { if (active) setVoiceAvailable(result.voice_available); })
      .catch(() => { if (active) setVoiceAvailable(false); });
    return () => {
      active = false;
      stopStream();
      clearInterval(timer);
      voice.current?.disconnect();
    };
  }, [incident?.id]);

  function openIncident(next: Incident) {
    setRecent(rememberIncident(next));
    window.location.assign(`/?incident=${encodeURIComponent(next.id)}`);
  }

  async function resumeIncident(id: string) {
    const snapshot = await getIncident(id);
    openIncident(snapshot.incident);
  }

  async function refresh() {
    if (!incident) return;
    setData(await getIncident(incident.id));
  }

  async function runAction(name: string, action: () => Promise<void>) {
    if (pending) return;
    setPending(name);
    setError("");
    try {
      await action();
      await refresh();
    } catch (reason) {
      setError(message(reason));
    } finally {
      setPending("");
    }
  }

  async function toggleVoice() {
    if (!incident || !voiceAvailable) return;
    if (voiceState !== "idle" && voiceState !== "error" && voiceState !== "disconnected") {
      voice.current?.disconnect();
      return;
    }
    const session = new BridgeVoice(incident, {
      state: setVoiceState,
      transcript: (speaker, text) => setTranscript(items => [...items.slice(-39), { speaker, text }]),
      proposal: setVoiceProposal,
      error: text => { setError(text); setVoiceState("error"); },
    });
    voice.current = session;
    await session.connect();
  }

  if (loadingIncident) return <div className="loading">Opening incident…</div>;
  if (!incident) return <Create onCreated={openIncident} onResume={resumeIncident} recent={recent} initialError={error} />;
  if (!data) return <div className="loading">Opening command room…</div>;

  const actions = data.timeline.filter(event => event.event_type === "action_item");
  const latest = data.updates[0];
  const voiceActive = !["idle","error","disconnected"].includes(voiceState);
  const voiceTitle = voiceAvailable === false ? "Voice is unavailable in this workspace"
    : voiceAvailable === null ? "Checking voice availability…"
    : voiceState === "speaking" ? "Incisight is responding"
    : voiceState === "error" ? "Voice connection failed"
    : voiceState === "disconnected" ? "Voice disconnected"
    : voiceState === "processing" ? "Incisight is processing"
    : voiceState === "connecting" ? "Connecting to voice service"
    : voiceState === "idle" ? "Incisight is standing by" : "Incisight is listening";
  const voiceDescription = voiceAvailable === false
    ? "You can still review the incident and use the demo controls."
    : voiceAvailable === null ? "Checking the voice service."
    : voiceState === "idle" || voiceState === "error" || voiceState === "disconnected"
      ? "Start a live voice session."
      : "Speak naturally. Interrupt at any time.";

  return (
    <div className="app">
      <header>
        <a className="brand brand-home" href="/" aria-label="Go to home page"><span className="brandmark"><Activity /></span>INCISIGHT</a>
        <div className="incident-id">INCIDENT <b>{incident.id.slice(0, 8).toUpperCase()}</b></div>
      </header>
      <section className="incident-bar">
        <div><span className="severity">{incident.severity}</span><span className="live-dot">● {incident.status.toUpperCase()}</span>{incident.is_demo && <span className="demo-badge">SIMULATED DEMO</span>}<h1>{incident.title}</h1><p>{incident.affected_service}</p></div>
        <div className="timer"><Clock3 /><span>INCIDENT DURATION<strong>{elapsed(incident.started_at)}</strong></span></div>
      </section>
      {error && <button className="error-banner" role="alert" onClick={() => setError("")}>{error}<span aria-hidden="true">×</span></button>}
      <main className="workspace">
        <section className="maincol">
          <div className="panel voice-panel">
            <div className="panel-title"><span><Mic /> VOICE COMMAND</span><b className={`connection ${voiceState}`}>{voiceAvailable === false ? "UNAVAILABLE" : voiceState.toUpperCase()}</b></div>
            <div className="voice-body">
              <button className={`voice-button ${voiceState}`} onClick={toggleVoice} disabled={voiceAvailable !== true}
                aria-label={voiceActive ? "Stop voice session" : "Start voice session"} title={voiceActive ? "Stop voice session" : "Start voice session"}>
                {voiceActive ? <Square /> : <Mic />}
              </button>
              <div><h2>{voiceTitle}</h2><p>{voiceDescription}</p></div>
            </div>
            <div className="transcript" aria-live="polite">
              {transcript.length === 0 ? <p className="empty">Live transcript will appear here.</p>
                : transcript.slice(-4).map((item, index) => <p key={index}><b>{item.speaker === "user" ? "YOU" : "INCISIGHT"}</b>{item.text}</p>)}
            </div>
            {voiceProposal && <section className="voice-proposal" aria-label="Voice proposal for review">
              <strong>{voiceProposal.kind === "event" ? "REVIEW TIMELINE ENTRY" : "REVIEW UPDATE DRAFT"}</strong>
              <p>{voiceProposal.kind === "event" ? voiceProposal.summary : voiceProposal.content}</p>
              {voiceProposal.kind === "event" && <p className="proposal-meta">{voiceProposal.event_type.replace("_", " ")} · {voiceProposal.source_type} · {Math.round(voiceProposal.confidence * 100)}% confidence{voiceProposal.owner ? ` · Owner: ${voiceProposal.owner}` : ""}</p>}
              {data.contradictions.some(item => item.status === "open") && <p className="proposal-warning">Open conflicts need review before relying on this proposal.</p>}
              <div className="proposal-actions"><button type="button" onClick={() => setVoiceProposal(null)}>DISCARD</button>
                <button type="button" disabled={Boolean(pending)} onClick={() => runAction("voice-proposal", async () => {
                  if (voiceProposal.kind === "event") await request("/api/events", {method:"POST",body:JSON.stringify({incident_id:incident.id,...voiceProposal,idempotency_key:crypto.randomUUID()})});
                  else await request("/api/updates/draft-from-proposal", {method:"POST",body:JSON.stringify({incident_id:incident.id,content:voiceProposal.content})});
                  setVoiceProposal(null);
                })}>{pending === "voice-proposal" ? "SAVING…" : voiceProposal.kind === "event" ? "CONFIRM AND SAVE" : "SAVE AS DRAFT"}</button></div>
            </section>}
          </div>
          <div className="panel">
            <div className="panel-title"><span><Activity /> INCIDENT TIMELINE</span><span>{data.timeline.length} EVENTS</span></div>
            <div className="timeline">
              {data.timeline.length === 0 && <p className="empty">No events recorded yet.</p>}
              {data.timeline.map(event => (
                <article key={event.id}>
                  <div className={`node ${event.source_type}`}>{event.source_type === "tool" ? <Check /> : event.event_type === "action_item" ? <Users /> : <CircleDot />}</div>
                  <div className="time">{fmt(event.created_at)}</div>
                  <div className="event"><div><span className={`tag ${event.event_type}`}>{event.event_type.replace("_", " ")}</span><span className="source">{event.source_type.toUpperCase()} · {Math.round(event.confidence * 100)}%</span></div><p>{event.summary}</p>{event.owner && <small>OWNER / {event.owner}</small>}</div>
                </article>
              ))}
            </div>
          </div>
        </section>
        <aside>
          <div className="panel contradiction">
            <div className="panel-title"><span><AlertTriangle /> POTENTIAL CONFLICTS</span><b>{data.contradictions.filter(item => item.status === "open").length}</b></div>
            {data.contradictions.length === 0 ? (
              <div className="empty-card"><ShieldCheck /><p>No conflicts detected.</p>
                <button onClick={() => runAction("health", () => request("/api/demo/advance", {
                  method: "POST", body: JSON.stringify({ incident_id: incident.id, action: "health_check" }),
                }).then(() => {}))} disabled={Boolean(pending)}>{pending === "health" ? "CHECKING…" : "RUN SEEDED HEALTH CHECK"}</button>
              </div>
            ) : data.contradictions.map(conflict => (
              <article key={conflict.id}>
                <span className="tag observation">{conflict.status}</span>
                <h3>{Math.round(conflict.confidence * 100)}% confidence</h3>
                <p>“{conflict.earlier_statement}”</p><p>“{conflict.later_statement}”</p>
                <small>{conflict.reason}</small>
                {conflict.status === "open" ? (
                  reviewingConflict === conflict.id ? (
                    <div className="resolution-form">
                      <label htmlFor={`resolution-${conflict.id}`}>REVIEW NOTE</label>
                      <textarea id={`resolution-${conflict.id}`} value={resolutionNote} onChange={event => setResolutionNote(event.target.value)}
                        placeholder="Explain why this conflict is resolved or dismissed." maxLength={500} />
                      <div className="resolution-actions">
                        <button type="button" onClick={() => { setReviewingConflict(null); setResolutionNote(""); }}>CANCEL</button>
                        {(["resolved", "dismissed"] as const).map(status => (
                          <button type="button" key={status} disabled={resolutionNote.trim().length < 3 || Boolean(pending)}
                            onClick={() => runAction("resolve", async () => {
                              await request(`/api/contradictions/${conflict.id}`, {
                                method: "PATCH", body: JSON.stringify({ status, resolution_note: resolutionNote.trim() }),
                              });
                              setReviewingConflict(null);
                              setResolutionNote("");
                            })}>{pending === "resolve" ? "SAVING…" : status.toUpperCase()}</button>
                        ))}
                      </div>
                    </div>
                  ) : <button className="text-action" onClick={() => { setReviewingConflict(conflict.id); setResolutionNote(""); }}>REVIEW CONFLICT</button>
                ) : conflict.resolution_note && <p className="resolution-note">{conflict.resolution_note}</p>}
              </article>
            ))}
          </div>
          <div className="panel">
            <div className="panel-title"><span><Users /> OPEN ACTIONS</span><b>{actions.length}</b></div>
            {actions.length === 0 ? <p className="empty">No owner assignments yet.</p> : actions.map(action => (
              <article className="action" key={action.id}><span>{action.owner?.slice(0, 2).toUpperCase() || "?"}</span><div><b>{action.owner || "Unassigned"}</b><p>{action.summary}</p></div></article>
            ))}
          </div>
          <div className="panel">
            <div className="panel-title"><span><FileWarning /> EVIDENCE</span><b>{data.evidence.length}</b></div>
            {data.evidence.length === 0 ? <p className="empty">No evidence retrieved yet.</p> : data.evidence.map(evidence => (
              <article className="evidence" key={evidence.id}><div><Database /><b>{evidence.source_name}</b>{evidence.is_simulated && <span>SIMULATED</span>}</div><p>{evidence.excerpt}</p><small>Retrieved {fmt(evidence.retrieved_at)}</small></article>
            ))}
          </div>
          <div className="panel update">
            <div className="panel-title"><span><Radio /> STAKEHOLDER UPDATE</span>{latest && <b>{latest.status}</b>}</div>
            {!latest ? <button className="outline" onClick={() => runAction("draft", () => request("/api/updates/draft", {
              method: "POST", body: JSON.stringify({ incident_id: incident.id }),
            }).then(() => {}))} disabled={Boolean(pending)}>{pending === "draft" ? "DRAFTING…" : "DRAFT FROM INCIDENT RECORD"}</button>
              : <><p>{latest.content}</p>
                {latest.status === "draft" ? confirmingUpdate ? (
                  <div className="approval-confirm">
                    <strong>Publish this draft in Incisight?</strong>
                    <p>This records an approved update in the simulated channel.</p>
                    <div>
                      <button type="button" onClick={() => setConfirmingUpdate(false)}>CANCEL</button>
                      <button type="button" className="approve" disabled={Boolean(pending)} onClick={() => runAction("publish", async () => {
                        const approver = "Incident Commander";
                        const nonce = await request<{ approval_nonce: string }>("/api/updates/approval-nonce", {
                          method: "POST", body: JSON.stringify({ update_id: latest.id, approver }),
                        });
                        await request("/api/updates/publish", {
                          method: "POST", body: JSON.stringify({
                            incident_id: incident.id, update_id: latest.id, approver,
                            approval_nonce: nonce.approval_nonce, confirmed: true,
                          }),
                        });
                        setConfirmingUpdate(false);
                      })}>{pending === "publish" ? "PUBLISHING…" : "CONFIRM PUBLISH"}</button>
                    </div>
                  </div>
                ) : <button className="approve" onClick={() => setConfirmingUpdate(true)}><Check /> REVIEW AND PUBLISH</button>
                  : <div className="published"><ShieldCheck /> Published in simulated channel by {latest.approved_by}</div>}
              </>}
          </div>
        </aside>
      </main>
    </div>
  );
}

export default App;
