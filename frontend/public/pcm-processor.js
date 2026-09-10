class PCMProcessor extends AudioWorkletProcessor {
  process(inputs) { const input=inputs[0]?.[0]; if(input){const pcm=new Int16Array(input.length);for(let i=0;i<input.length;i++)pcm[i]=Math.max(-32768,Math.min(32767,Math.round(input[i]*32767)));this.port.postMessage(pcm.buffer,[pcm.buffer]);}return true; }
}
registerProcessor("pcm-processor",PCMProcessor);
