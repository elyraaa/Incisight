import { API, callTool } from "./api";
import type { Incident, Update } from "./types";

export type VoiceState = "idle"|"connecting"|"listening"|"speaking"|"error";
type Callbacks = { state:(s:VoiceState)=>void; transcript:(speaker:"user"|"agent", text:string)=>void; refresh:()=>void; error:(message:string)=>void };

const tools = [
  {type:"function",name:"record_incident_event",description:"Record a meaningful incident observation, hypothesis, decision, action item, or status update.",parameters:{type:"object",properties:{event_type:{type:"string",enum:["observation","hypothesis","decision","action_item","status_update"]},summary:{type:"string",minLength:2,maxLength:500},subject:{type:"string",maxLength:120},claim_value:{type:"string",maxLength:120},source_type:{type:"string",enum:["user","agent"]},confidence:{type:"number",minimum:0,maximum:1},owner:{type:"string",maxLength:80},idempotency_key:{type:"string",pattern:"^[A-Za-z0-9_-]{8,80}$"}},required:["event_type","summary","source_type","confidence"]}},
  {type:"function",name:"check_service_health",description:"Check the seeded status source. Use this instead of inventing service state.",parameters:{type:"object",properties:{service:{type:"string",minLength:2,maxLength:120}},required:["service"]}},
  {type:"function",name:"search_security_advisory",description:"Search the deterministic cached advisory source.",parameters:{type:"object",properties:{query:{type:"string",minLength:2,maxLength:160}},required:["query"]}},
  {type:"function",name:"find_contradictions",description:"Check a recorded factual claim against previous claims.",parameters:{type:"object",properties:{claim_event_id:{type:"string",pattern:"^[0-9a-fA-F-]{36}$"}},required:["claim_event_id"]}},
  {type:"function",name:"draft_stakeholder_update",description:"Draft an update from stored incident facts. It is not published.",parameters:{type:"object",properties:{},required:[]}},
  {type:"function",name:"approve_stakeholder_update",description:"Publish a draft only after the user explicitly says they approve that draft.",parameters:{type:"object",properties:{update_id:{type:"string",pattern:"^[0-9a-fA-F-]{36}$"},approver:{type:"string",minLength:2,maxLength:80},confirmed:{type:"boolean",const:true}},required:["update_id","approver","confirmed"]}},
];

function b64(buffer:ArrayBuffer) { let s=""; new Uint8Array(buffer).forEach(b=>s+=String.fromCharCode(b)); return btoa(s); }
function decodeAudio(value:string) { const raw=atob(value); const bytes=new Uint8Array(raw.length); for(let i=0;i<raw.length;i++) bytes[i]=raw.charCodeAt(i); return new Int16Array(bytes.buffer); }

export class BridgeVoice {
  private ws?:WebSocket; private ctx?:AudioContext; private stream?:MediaStream; private worklet?:AudioWorkletNode;
  private grant=""; private pending:{call_id:string; result:unknown}[]=[]; private replyDone=false; private nextAudio=0; private sources:AudioBufferSourceNode[]=[];
  constructor(private incident:Incident, private cb:Callbacks) {}
  private async dispatch(name:string,args:Record<string,unknown>) {
    const common={...args,incident_id:this.incident.id};
    if(name==="check_service_health") return fetch(`${API}/api/tools/check-service-health?incident_id=${this.incident.id}&service=${encodeURIComponent(String(args.service||this.incident.affected_service))}`,{headers:{Authorization:`Bearer ${this.grant}`}}).then(r=>r.json());
    if(name==="search_security_advisory") return fetch(`${API}/api/tools/search-security-advisory?incident_id=${this.incident.id}&query=${encodeURIComponent(String(args.query||"authentication"))}`,{headers:{Authorization:`Bearer ${this.grant}`}}).then(r=>r.json());
    if(name==="approve_stakeholder_update") {
      if(args.confirmed!==true) return {ok:false,error:"Explicit approval was not confirmed."};
      const nonce=await fetch(`${API}/api/updates/approval-nonce`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({update_id:args.update_id,approver:args.approver})}).then(r=>r.json());
      return callTool("approve-stakeholder-update",{...common,approval_nonce:nonce.approval_nonce},this.grant);
    }
    const paths:Record<string,string>={record_incident_event:"record-incident-event",find_contradictions:"find-contradictions",draft_stakeholder_update:"draft-stakeholder-update"};
    return callTool(paths[name],common,this.grant);
  }
  private flushAudio(){ this.sources.forEach(x=>{try{x.stop()}catch{}});this.sources=[];if(this.ctx)this.nextAudio=this.ctx.currentTime; }
  private flushTools(){if(!this.replyDone)return;for(const p of this.pending.splice(0))this.ws?.send(JSON.stringify({type:"tool.result",call_id:p.call_id,result:JSON.stringify(p.result)}));this.replyDone=false;}
  private play(pcm:string){ if(!this.ctx)return; const samples=decodeAudio(pcm), buffer=this.ctx.createBuffer(1,samples.length,24000), data=buffer.getChannelData(0); for(let i=0;i<samples.length;i++)data[i]=samples[i]/32768; const src=this.ctx.createBufferSource();src.buffer=buffer;src.connect(this.ctx.destination);this.nextAudio=Math.max(this.nextAudio,this.ctx.currentTime);src.start(this.nextAudio);this.nextAudio+=buffer.duration;this.sources.push(src);src.onended=()=>this.sources=this.sources.filter(x=>x!==src); }
  async connect(){
    try{
      this.cb.state("connecting");
      const auth=await fetch(`${API}/api/voice/token`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({incident_id:this.incident.id})});
      if(!auth.ok) throw new Error((await auth.json()).detail?.recovery||"Voice token failed");
      const token=await auth.json();this.grant=token.tool_grant;
      this.ctx=new AudioContext({sampleRate:24000}); await this.ctx.audioWorklet.addModule("/pcm-processor.js");
      this.stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,sampleRate:24000}});
      const source=this.ctx.createMediaStreamSource(this.stream); this.worklet=new AudioWorkletNode(this.ctx,"pcm-processor"); source.connect(this.worklet);
      this.ws=new WebSocket(`wss://agents.assemblyai.com/v1/ws?token=${encodeURIComponent(token.token)}`);
      this.worklet.port.onmessage=e=>{if(this.ws?.readyState===WebSocket.OPEN)this.ws.send(JSON.stringify({type:"input.audio",audio:b64(e.data)}));};
      this.ws.onopen=()=>this.ws?.send(JSON.stringify({type:"session.update",session:{system_prompt:`You are Incisight for incident ${this.incident.id}. Be direct and use at most two short sentences. Call tools for all system state. Clearly say reported, verified, or inferred. Ask before resolving contradictions. Never approve publishing without explicit confirmation.`,greeting:`Incisight is listening for ${this.incident.title}.`,tools,input:{format:{encoding:"audio/pcm"},keyterms:token.keyterms,turn_detection:{vad_threshold:.5,min_silence:650,max_silence:2200,interrupt_response:true}},output:{voice:"ivy",format:{encoding:"audio/pcm"}}}}));
      this.ws.onmessage=async e=>{const m=JSON.parse(e.data);if(m.type==="session.ready")this.cb.state("listening");if(m.type==="input.speech.started"){this.replyDone=false;this.flushAudio();this.cb.state("listening");}if(m.type==="reply.started")this.replyDone=false;if(m.type==="reply.audio"){this.cb.state("speaking");this.play(m.audio);}if(m.type==="transcript.user"||m.type==="transcript.agent"){const speaker=m.type.endsWith("user")?"user":"agent";this.cb.transcript(speaker,m.text);fetch(`${API}/api/transcripts`,{method:"POST",headers:{"Content-Type":"application/json",Authorization:`Bearer ${this.grant}`},body:JSON.stringify({incident_id:this.incident.id,speaker,text:m.text,final:true})});}if(m.type==="tool.call"){const result=await this.dispatch(m.name,m.arguments||{}).catch(err=>({ok:false,error:String(err)}));this.pending.push({call_id:m.call_id,result});this.cb.refresh();this.flushTools();}if(m.type==="reply.done"){if(m.status==="interrupted"){this.pending=[];this.replyDone=false;}else{this.replyDone=true;this.flushTools();}this.cb.state("listening");}if(m.type==="session.error")this.cb.error(m.message||m.code);};
      this.ws.onerror=()=>this.cb.error("Voice connection failed"); this.ws.onclose=()=>this.cb.state("idle");
    }catch(e){this.cb.error(e instanceof Error?e.message:String(e));this.disconnect();}
  }
  disconnect(){this.ws?.close();this.stream?.getTracks().forEach(t=>t.stop());this.worklet?.disconnect();this.ctx?.close();this.flushAudio();this.cb.state("idle");}
}
