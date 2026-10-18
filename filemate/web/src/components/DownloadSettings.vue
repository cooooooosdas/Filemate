<template>
  <section class="download-settings" aria-labelledby="download-settings-title">
    <h3 id="download-settings-title">导出文件，存到你指定的位置</h3>
    <p>用于备份、报告、简历、学习计划和本地录像的下载。学习资料仍保存在原学习空间。</p>
    <div class="folder-location"><el-icon><FolderOpened /></el-icon><div><strong>{{ folderName || '跟随浏览器下载设置' }}</strong><p>{{ folderName ? '导出时从这个文件夹开始，仍可确认或更改文件名。' : '文件下载到浏览器指定的目录。' }}</p></div></div>
    <div class="download-actions"><el-button v-if="supported" type="primary" :loading="busy" @click="choose">{{ folderName ? '更换文件夹' : '选择本机文件夹' }}</el-button><el-button v-if="folderName || error" :disabled="busy" @click="reset">恢复浏览器默认</el-button><el-button :disabled="busy" @click="testSave">试存一个文件</el-button></div>
    <p v-if="!supported">当前浏览器不能直接选择文件夹。可在浏览器的“设置 → 下载”中修改位置，或开启“每次下载前询问保存位置”。</p>
    <p v-if="error" role="alert">{{ error }}</p><p v-if="message" role="status">{{ message }}</p>
    <p class="folder-privacy">只在当前浏览器记住目录授权，不上传目录路径或其中的文件。清除网站数据后需要重新选择。</p>
  </section>
</template>
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { FolderOpened } from '../icons'
import { chooseDownloadFolder, downloadLocation, folderPickerAvailable, resetDownloadFolder, saveDownload } from '../services/downloads'
const folderName=ref(''), error=ref(''), message=ref(''), busy=ref(false), supported=folderPickerAvailable()
async function load(){const state=await downloadLocation();folderName.value=state.name;error.value=state.error}
async function choose(){busy.value=true;message.value='';try{if(await chooseDownloadFolder()){await load();if(!error.value)message.value='已选择保存目录。'}}catch(e){error.value=e instanceof Error?e.message:'无法选择目录，请重试。'}finally{busy.value=false}}
async function reset(){busy.value=true;message.value='';try{await resetDownloadFolder();await load();if(!error.value)message.value='已恢复浏览器默认下载。'}catch(e){error.value=e instanceof Error?e.message:'设置未修改，请重试。'}finally{busy.value=false}}
async function testSave(){busy.value=true;message.value='';try{if(await saveDownload(new Blob(['FileMate 保存位置测试\n这是测试文件，不包含个人资料或密钥。\n'],{type:'text/plain;charset=utf-8'}),'FileMate-保存测试.txt'))message.value=folderName.value?'测试文件已保存。':'测试下载已发起，请查看浏览器下载列表。'}finally{busy.value=false}}
onMounted(load)
</script>
<style scoped>
.download-settings h3{font-size:25px;line-height:1.5;margin:0 0 12px}.download-settings p{font-size:17px;line-height:1.8;color:var(--text-secondary)}.folder-location{display:flex;gap:18px;align-items:center;padding:22px;margin:24px 0;background:var(--bg-elevated);border:1px solid var(--border-subtle);border-radius:12px;overflow-wrap:anywhere}.folder-location>.el-icon{font-size:32px;color:var(--accent)}.folder-location strong{font-size:21px;color:var(--text-primary)}.folder-location p{margin:7px 0 0}.download-actions{display:flex;flex-wrap:wrap;gap:12px}.download-actions .el-button{margin:0}.folder-privacy{padding-top:20px;border-top:1px solid var(--border-subtle)}[role=alert]{color:var(--danger)}
</style>
