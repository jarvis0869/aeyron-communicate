export type Capture={stop:()=>void;cancel:()=>void};
export async function startCapture(signal:AbortSignal,onDone:(blob:Blob)=>void,onError:(message:string)=>void,onLevel:(level:number)=>void,maxBytes=8*1024*1024):Promise<Capture>{
  if(!navigator.mediaDevices?.getUserMedia||typeof MediaRecorder==='undefined')throw new Error('Recording is unavailable in this browser. Please use Type.');
  const stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:false,autoGainControl:true}});
  if(signal.aborted){stream.getTracks().forEach(t=>t.stop());throw new DOMException('Cancelled','AbortError');}
  const types=['audio/webm;codecs=opus','audio/mp4','audio/ogg;codecs=opus'];
  const mimeType=types.find(t=>MediaRecorder.isTypeSupported(t));
  let recorder:MediaRecorder;
  try{recorder=new MediaRecorder(stream,mimeType?{mimeType}:undefined);}catch(e){stream.getTracks().forEach(t=>t.stop());throw e;}
  let cancelled=false,bytes=0,frames=0,chunks:Blob[]=[];
  let audio:AudioContext|undefined;
  try{audio=new AudioContext();const source=audio.createMediaStreamSource(stream),analyser=audio.createAnalyser();analyser.fftSize=256;source.connect(analyser);const samples=new Uint8Array(analyser.fftSize);const meter=()=>{analyser.getByteTimeDomainData(samples);onLevel(Math.min(1,Math.sqrt(samples.reduce((sum,v)=>sum+((v-128)/128)**2,0)/samples.length)*4));frames=requestAnimationFrame(meter);};meter();}catch{/* Meter is optional; recording remains available. */}
  const cleanup=()=>{clearTimeout(limit);cancelAnimationFrame(frames);stream.getTracks().forEach(t=>{t.onended=null;t.stop();});void audio?.close().catch(()=>{});signal.removeEventListener('abort',cancel);};
  const stop=()=>{if(recorder.state!=='inactive')recorder.stop();};
  const cancel=()=>{cancelled=true;chunks=[];stop();cleanup();};
  const limit=setTimeout(stop,90000);
  signal.addEventListener('abort',cancel,{once:true});
  stream.getAudioTracks().forEach(t=>{t.onended=()=>{cancel();onError('Your microphone was disconnected. Please record again.');};});
  recorder.ondataavailable=e=>{if(cancelled)return;if(e.data.size){bytes+=e.data.size;if(bytes>maxBytes){cancel();onError('The recording reached its size limit. Please try a shorter message.');}else chunks.push(e.data);}};
  recorder.onerror=()=>{cancel();onError('Recording was interrupted. Please try again or type.');};
  recorder.onstop=()=>{cleanup();if(!cancelled){const blob=new Blob(chunks,{type:recorder.mimeType});chunks=[];if(!blob.size)onError('No audio was captured. Please try again.');else onDone(blob);}};
  try{recorder.start(500);}catch(e){cancel();throw e;}
  return {stop,cancel};
}
