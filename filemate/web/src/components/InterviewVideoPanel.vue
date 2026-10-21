<template>
  <section class="interview-video-panel" aria-label="设备与本地录像">
    <h3>你的面试画面</h3>
    <video ref="preview" v-show="camera.phase==='ready'" autoplay muted playsinline aria-label="摄像头本机预览" />
    <p v-if="camera.phase!=='ready'">{{ camera.phase==='requesting' ? '等待摄像头授权…' : '设备默认关闭，开启后只在本机预览。' }}</p>
    <div class="actions"><button type="button" :disabled="busy" @click="$emit('camera')">{{ camera.phase==='off' ? '开启摄像头' : camera.phase==='requesting' ? '取消开启' : '关闭摄像头' }}</button><button type="button" :disabled="phase==='stopping' || (phase!=='recording' && (busy || blocked || camera.phase!=='ready'))" @click="phase==='recording' ? $emit('stop') : $emit('record')"><VideoPlay :size="20" />{{ phase==='recording' ? '停止录像并回看' : phase==='stopping' ? '正在收尾…' : '录制本题' }}</button></div>
    <details><summary>选择设备与录音方式</summary>
      <label>摄像头<select :value="cameraId" :disabled="camera.phase!=='off' || busy" @change="$emit('update:cameraId', value($event))"><option value="">系统默认摄像头</option><option v-for="(device,index) in cameras" :key="device.deviceId || index" :value="device.deviceId">{{ device.label || `摄像头 ${index+1}（授权后显示名称）` }}</option></select></label>
      <p>先关闭预览再切换摄像头；选择不会自动开启设备。</p>
      <label class="consent"><input type="checkbox" :checked="withAudio" :disabled="busy" @change="$emit('update:withAudio', ($event.target as HTMLInputElement).checked)" />同时录制声音（单独请求麦克风权限）</label>
      <label v-if="withAudio">麦克风<select :value="microphoneId" :disabled="busy" @change="$emit('update:microphoneId', value($event))"><option value="">系统默认麦克风</option><option v-for="(device,index) in microphones" :key="device.deviceId || index" :value="device.deviceId">{{ device.label || `麦克风 ${index+1}（授权后显示名称）` }}</option></select></label>
      <button type="button" :disabled="busy" @click="$emit('refresh')"><Refresh :size="20" />刷新设备列表</button>
    </details>
    <p v-if="error || camera.error || previewError" role="alert">{{ error || videoIssue(camera.error) || previewError }}</p>
    <p role="status">{{ phase==='recording' ? '正在当前页面录制；停止后立即回看。' : '录像不上传，刷新或离开后清除。请及时导出。' }}</p>
    <p>每段最多30分钟／100MiB，每页最多20段／200MiB；新片段保留旧录像，容量满后需先导出并删除。</p>
    <slot />
  </section>
</template>
<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import type { CameraState } from '../interview/video-devices'
import { videoIssue } from '../interview/video-messages'
import { Refresh, VideoPlay } from '../icons'
const props=defineProps<{camera:CameraState;phase:string;busy:boolean;blocked:boolean;cameraId:string;microphoneId:string;withAudio:boolean;error:string}>()
const emit=defineEmits<{camera:[];record:[];stop:[];refresh:[];preview:[element:HTMLVideoElement|null];'update:cameraId':[value:string];'update:microphoneId':[value:string];'update:withAudio':[value:boolean]}>()
const preview=ref<HTMLVideoElement|null>(null)
const previewError=ref('')
const cameras=computed(()=>props.camera.devices.filter(d=>d.kind==='videoinput'))
const microphones=computed(()=>props.camera.devices.filter(d=>d.kind==='audioinput'))
const value=(event:Event)=>(event.target as HTMLSelectElement).value
watch(()=>props.camera.stream,async stream=>{previewError.value='';if(preview.value){preview.value.srcObject=stream;if(stream){try{await preview.value.play()}catch{previewError.value='浏览器无法播放预览，请关闭后重新开启；文字训练仍可继续。'}}}})
onMounted(()=>emit('preview',preview.value))
</script>
<style scoped>
.interview-video-panel { text-align: left; min-width: 0; margin-top: 24px; padding-top: 20px; border-top: 1px solid var(--border-color); } h3 { font-size: 23px; margin: 0 0 16px; }
video { width: 100%; background: #111827; aspect-ratio: 4/3; object-fit: contain; border-radius: 14px; } p { color: var(--text-secondary); font-size: 16px; line-height: 1.6; overflow-wrap: anywhere; margin: 12px 0; }
.actions { display:flex;flex-wrap:wrap;gap:10px;margin:14px 0; } button,select { min-height:44px;font:inherit;font-size:17px;color:var(--text-primary);background:var(--bg-card);border:1px solid var(--border-color);border-radius:10px;padding:8px 12px;max-width:100%; } button { display:inline-flex;gap:8px;align-items:center; } button:disabled { opacity:.65;cursor:not-allowed; }
details { margin-top:16px; } summary { min-height:44px;cursor:pointer;font-size:17px; } label { display:flex; flex-direction:column;gap:8px;font-size:17px;margin:12px 0; } label.consent { flex-direction:row;align-items:flex-start;line-height:1.6; } input { width:20px;height:20px;flex-shrink:0; }
</style>
