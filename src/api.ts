export type Config={transcription_enabled:boolean;transcription_mode:string;rewrite_mode:string;processor:string|null;retention_notice:string;max_audio_seconds:number;max_audio_bytes:number;max_text_chars:number};
function requestId():string{const c=globalThis.crypto;if(c?.randomUUID)return c.randomUUID();return `${Date.now()}-${Math.random().toString(36).slice(2)}`;}
export const offlineConfig:Config={transcription_enabled:false,transcription_mode:'disabled',rewrite_mode:'unavailable',processor:null,retention_notice:'Speech service is not connected. You can still type, approve, and use your messages.',max_audio_seconds:90,max_audio_bytes:8*1024*1024,max_text_chars:4000};
export async function configuration(signal:AbortSignal):Promise<Config>{const r=await fetch('/v1/config',{signal,cache:'no-store'});if(!r.ok)throw new Error('unavailable');return {...offlineConfig,...await r.json()};}
const errorText:Record<number,string>={400:'The request could not be understood. Please try again.',401:'Your session expired. Please try again.',403:'This request is not permitted.',409:'This request is already processing or was changed. Please try again.',413:'This recording is too large. Please record a shorter message.',415:'This audio format is not supported.',422:'This recording or message could not be processed.',429:'The service is busy. Please wait before trying again.',503:'Speech service is unavailable. Your typed messages still work.',504:'The service took too long. Please try again or type instead.'};
export async function request<T>(path:string,body:FormData|{text:string;style:string},signal:AbortSignal):Promise<T>{
  const session=await fetch('/v1/session',{method:'POST',signal,cache:'no-store'});
  if(!session.ok)throw new Error(errorText[session.status]||'Unable to start a session. Try again later.');
  const {token}=await session.json();
  if(typeof token!=='string')throw new Error('Invalid service response. Please try again.');
  const isForm=body instanceof FormData;
  const response=await fetch('/v1/communication/'+path,{method:'POST',signal,cache:'no-store',headers:{Authorization:'Bearer '+token,'Idempotency-Key':requestId(),...(!isForm?{'Content-Type':'application/json'}:{})},body:isForm?body:JSON.stringify(body)});
  if(!response.ok)throw new Error(errorText[response.status]||'The service could not complete this. Your original message is unchanged.');
  return response.json();
}
