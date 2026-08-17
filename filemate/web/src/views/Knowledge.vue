<template>
  <div class="knowledge-page">
    <header class="page-head"><div><p class="eyebrow">LOCAL KNOWLEDGE BASE</p><h1>个人知识库</h1><p>统一管理已解析资料，跨文档检索并核验引用位置。</p></div><router-link class="import-link" to="/ai-tools">添加学习资料</router-link></header>

    <section class="search-panel">
      <div class="search-row">
        <label class="search-box"><span class="sr-only">检索知识库</span><input v-model.trim="query" name="knowledge_query" autocomplete="off" placeholder="输入概念、问题或关键词…" @keyup.enter="search" /></label>
        <select v-model="selectedSource" name="knowledge_scope" aria-label="检索范围"><option value="">全部资料</option><option v-for="source in sources" :key="source.source_id" :value="source.source_id">{{ source.original_name }}</option></select>
        <button :disabled="searching || !query" @click="search">{{ searching ? '检索中…' : '开始检索' }}</button>
      </div>
      <p class="privacy">检索在本机完成；结果展示资料名、页码和原文片段。</p>
    </section>

    <section v-if="hasSearched" class="results" aria-live="polite">
      <div class="section-head"><h2>检索结果</h2><span>{{ results.length }} 条引用</span></div>
      <div v-if="results.length" class="result-list">
        <article v-for="(result,index) in results" :key="result.chunk_id">
          <div class="citation"><b>[引用 {{ index + 1 }}]</b><span>{{ result.source_name }}</span><em>{{ result.page_number ? `第 ${result.page_number} 页` : `片段 ${result.chunk_index + 1}` }}</em></div>
          <p>{{ result.excerpt }}</p>
          <div class="result-foot"><small>相关度 {{ Math.round(result.score * 100) / 100 }}</small><div class="relevance" role="group" :aria-label="`评价引用 ${index + 1} 是否相关`"><span>这条引用有帮助吗？</span><button type="button" :class="{ selected: feedbackState[result.chunk_id] === 1 }" :aria-pressed="feedbackState[result.chunk_id] === 1" @click="rateResult(result, index, 1)">相关</button><button type="button" :class="{ selected: feedbackState[result.chunk_id] === -1 }" :aria-pressed="feedbackState[result.chunk_id] === -1" @click="rateResult(result, index, -1)">不相关</button></div></div>
        </article>
      </div>
      <div v-else class="empty">没有找到相关片段，尝试换一个更具体的关键词。</div>
    </section>

    <section class="library">
      <div class="section-head"><h2>已入库资料</h2><span>{{ sources.length }} 份</span></div>
      <div v-if="loading" class="empty" aria-live="polite">正在读取本地知识库…</div>
      <div v-else-if="sources.length" class="source-grid">
        <article v-for="source in sources" :key="source.source_id" class="source-card">
          <div class="file-mark">{{ suffix(source.original_name) }}</div>
          <div class="source-copy"><h3>{{ source.original_name }}</h3><p>{{ source.text_length.toLocaleString('zh-CN') }} 字 · {{ formatDate(source.created_at) }}</p></div>
          <button :aria-expanded="expandedSource === source.source_id" @click="toggleArtifacts(source.source_id)">{{ expandedSource === source.source_id ? '收起产物' : '查看产物' }}</button>
          <div v-if="expandedSource === source.source_id" class="artifact-list">
            <p v-if="artifactLoading">正在加载…</p>
            <template v-else-if="artifacts.length"><button v-for="artifact in artifacts" :key="artifact.artifact_id" type="button" @click="openArtifact(artifact.artifact_id)"><span>{{ artifactLabel(artifact.artifact_type) }}</span><b>{{ artifact.title || '未命名产物' }}</b><em>打开</em></button></template>
            <p v-else>该资料暂无学习产物</p>
          </div>
        </article>
      </div>
      <div v-else class="empty"><strong>知识库还是空的</strong><span>在“资料理解”中生成摘要、知识卡或练习题后，资料会自动入库。</span><router-link to="/ai-tools">去添加第一份资料</router-link></div>
    </section>

    <Teleport to="body">
      <div v-if="selectedArtifact" class="artifact-overlay" role="presentation" @click.self="closeArtifact">
        <section class="artifact-dialog" role="dialog" aria-modal="true" aria-labelledby="artifact-dialog-title">
          <header><div><p class="eyebrow">{{ artifactLabel(selectedArtifact.artifact_type) }}</p><h2 id="artifact-dialog-title">{{ selectedArtifact.title }}</h2></div><button type="button" aria-label="关闭学习产物" @click="closeArtifact">×</button></header>
          <template v-if="editing">
            <label><span>标题</span><input v-model.trim="draftTitle" name="artifact_title" autocomplete="off" /></label>
            <label><span>内容 {{ structuredContent ? '（JSON）' : '' }}</span><textarea v-model="draftContent" name="artifact_content" rows="16"></textarea></label>
          </template>
          <pre v-else>{{ formatArtifactContent(selectedArtifact.content) }}</pre>
          <footer><span>修改会保存到本机知识库</span><div><button type="button" @click="exportArtifact">导出</button><button v-if="!editing" type="button" @click="editing = true">编辑</button><button v-else type="button" @click="cancelEdit">取消</button><button v-if="editing" class="primary" type="button" :disabled="saving" @click="saveArtifact">{{ saving ? '保存中…' : '保存修改' }}</button></div></footer>
        </section>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getKnowledgeArtifact, getKnowledgeArtifacts, getKnowledgeSources, searchKnowledge, submitProductFeedback, updateKnowledgeArtifact, type KnowledgeArtifact, type KnowledgeSearchResult, type KnowledgeSource } from '../services/api'

const sources=ref<KnowledgeSource[]>([]); const results=ref<KnowledgeSearchResult[]>([]); const artifacts=ref<KnowledgeArtifact[]>([])
const query=ref(''); const selectedSource=ref(''); const loading=ref(true); const searching=ref(false); const hasSearched=ref(false); const expandedSource=ref(''); const artifactLoading=ref(false)
const feedbackState=ref<Record<string,1|-1>>({})
const selectedArtifact=ref<KnowledgeArtifact|null>(null); const editing=ref(false); const saving=ref(false); const draftTitle=ref(''); const draftContent=ref(''); const structuredContent=ref(false)
const load=async()=>{loading.value=true;try{sources.value=await getKnowledgeSources()}catch(error:any){ElMessage.error(error.message||'知识库加载失败')}finally{loading.value=false}}
const search=async()=>{if(!query.value)return;searching.value=true;try{results.value=await searchKnowledge(query.value,selectedSource.value||undefined);hasSearched.value=true}catch(error:any){ElMessage.error(error.message||'检索失败')}finally{searching.value=false}}
const rateResult=async(result:KnowledgeSearchResult,index:number,rating:1|-1)=>{try{await submitProductFeedback('retrieval',`${query.value}:${result.chunk_id}`,rating,{rank:index+1,score:result.score,query_length:query.value.length,query_token_count:query.value.trim().split(/\s+/).filter(Boolean).length,result_type:'chunk'});feedbackState.value[result.chunk_id]=rating;ElMessage.success('匿名相关性反馈已记录')}catch(error:any){ElMessage.error(error.message||'反馈保存失败')}}
const toggleArtifacts=async(sourceId:string)=>{if(expandedSource.value===sourceId){expandedSource.value='';return}expandedSource.value=sourceId;artifactLoading.value=true;try{artifacts.value=await getKnowledgeArtifacts(sourceId)}catch(error:any){ElMessage.error(error.message||'产物加载失败')}finally{artifactLoading.value=false}}
const suffix=(name:string)=>name.includes('.')?name.split('.').pop()!.slice(0,4).toUpperCase():'DOC'
const formatDate=(value:string)=>new Intl.DateTimeFormat('zh-CN',{month:'short',day:'numeric'}).format(new Date(value))
const artifactLabel=(type:string)=>({summary:'摘要',knowledge_cards:'知识卡',questions:'练习题',notes:'笔记',study_plan:'学习计划'}[type]||type)
const formatArtifactContent=(content:any)=>typeof content==='string'?content:JSON.stringify(content,null,2)
const syncDraft=(artifact:KnowledgeArtifact)=>{draftTitle.value=artifact.title;structuredContent.value=typeof artifact.content!=='string';draftContent.value=formatArtifactContent(artifact.content)}
const openArtifact=async(artifactId:string)=>{try{const artifact=await getKnowledgeArtifact(artifactId);selectedArtifact.value=artifact;syncDraft(artifact);editing.value=false}catch(error:any){ElMessage.error(error.message||'产物打开失败')}}
const closeArtifact=()=>{selectedArtifact.value=null;editing.value=false}
const cancelEdit=()=>{if(selectedArtifact.value)syncDraft(selectedArtifact.value);editing.value=false}
const saveArtifact=async()=>{if(!selectedArtifact.value||!draftTitle.value)return;let content:any=draftContent.value;if(structuredContent.value){try{content=JSON.parse(draftContent.value)}catch{ElMessage.error('JSON 格式不正确，请检查逗号和引号');return}}saving.value=true;try{const updated=await updateKnowledgeArtifact(selectedArtifact.value.artifact_id,draftTitle.value,content);selectedArtifact.value=updated;syncDraft(updated);editing.value=false;const index=artifacts.value.findIndex(item=>item.artifact_id===updated.artifact_id);if(index>=0)artifacts.value[index]=updated;ElMessage.success('学习产物已保存')}catch(error:any){ElMessage.error(error.message||'保存失败')}finally{saving.value=false}}
const exportArtifact=()=>{if(!selectedArtifact.value)return;const structured=typeof selectedArtifact.value.content!=='string';const blob=new Blob([formatArtifactContent(selectedArtifact.value.content)],{type:structured?'application/json;charset=utf-8':'text/plain;charset=utf-8'});const url=URL.createObjectURL(blob);const link=document.createElement('a');link.href=url;link.download=`${selectedArtifact.value.title||'FileMate学习产物'}.${structured?'json':'txt'}`;link.click();URL.revokeObjectURL(url)}
onMounted(load)
</script>

<style scoped>
.knowledge-page{max-width:1120px;margin:0 auto;padding:28px;color:var(--text-primary)}.page-head,.section-head{display:flex;align-items:end;justify-content:space-between;gap:20px}.page-head{margin-bottom:24px}.page-head h1{font-size:32px;margin:6px 0}.page-head p{margin:0;color:var(--text-secondary)}.eyebrow{color:var(--accent)!important;font-size:11px;font-weight:800;letter-spacing:.14em}.import-link{padding:10px 15px;border-radius:9px;color:white;background:var(--accent);text-decoration:none}.search-panel,.results,.library{background:var(--bg-surface);border:1px solid var(--border-subtle);border-radius:16px;padding:22px}.search-row{display:grid;grid-template-columns:1fr 190px auto;gap:10px}.search-row input,.search-row select{width:100%;height:44px;border:1px solid var(--border-default);border-radius:9px;padding:0 12px;background:var(--bg-elevated);color:var(--text-primary)}.search-row button{border:0;border-radius:9px;padding:0 18px;background:var(--accent);color:white;font-weight:700}.search-row button:disabled{opacity:.45}.privacy{margin:10px 0 0;color:var(--text-muted);font-size:12px}.results,.library{margin-top:16px}.section-head h2{font-size:19px;margin:0}.section-head span{font-size:12px;color:var(--text-muted)}.result-list{display:grid;gap:10px;margin-top:16px}.result-list article{padding:16px;border:1px solid var(--border-subtle);border-radius:12px;background:var(--bg-base)}.citation{display:flex;gap:9px;align-items:center;flex-wrap:wrap;font-size:12px}.citation b{color:var(--accent)}.citation span{font-weight:700}.citation em{font-style:normal;color:var(--text-muted)}.result-list p{line-height:1.75;overflow-wrap:anywhere}.result-list small{color:var(--text-muted)}.source-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:16px}.source-card{display:grid;grid-template-columns:48px 1fr auto;gap:12px;align-items:center;padding:16px;border:1px solid var(--border-subtle);border-radius:13px}.file-mark{width:48px;height:52px;display:grid;place-items:center;border-radius:8px;background:var(--accent-soft);color:var(--accent);font-size:11px;font-weight:800}.source-copy{min-width:0}.source-copy h3{font-size:14px;margin:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.source-copy p{font-size:12px;color:var(--text-muted);margin:7px 0 0}.source-card>button{border:1px solid var(--accent-border);border-radius:8px;background:transparent;color:var(--accent);padding:7px 9px}.artifact-list{grid-column:1/-1;border-top:1px solid var(--border-subtle);padding-top:10px}.artifact-list div{display:flex;gap:9px;padding:6px 0;font-size:12px}.artifact-list span{color:var(--accent)}.artifact-list p{color:var(--text-muted);font-size:12px}.empty{display:flex;flex-direction:column;align-items:center;gap:8px;padding:54px;text-align:center;color:var(--text-muted)}.empty a{color:var(--accent)}.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}@media(max-width:760px){.search-row{grid-template-columns:1fr}.search-row button{height:44px}.source-grid{grid-template-columns:1fr}.page-head{align-items:start;flex-direction:column}}@media(max-width:480px){.knowledge-page{padding:16px}.source-card{grid-template-columns:42px 1fr}.source-card>button{grid-column:1/-1}.file-mark{width:42px}}
.artifact-list>button{width:100%;display:grid;grid-template-columns:72px 1fr auto;gap:9px;padding:9px 6px;border:0;border-radius:7px;background:transparent;color:var(--text-primary);text-align:left;font-size:12px;cursor:pointer}.artifact-list>button:hover{background:var(--accent-soft)}.artifact-list>button span{color:var(--accent)}.artifact-list>button em{font-style:normal;color:var(--text-muted)}
.artifact-overlay{position:fixed;inset:0;z-index:1000;display:grid;place-items:center;padding:20px;background:rgba(25,48,39,.28);backdrop-filter:blur(4px)}.artifact-dialog{width:min(780px,100%);max-height:min(760px,90vh);overflow:auto;padding:24px;border:1px solid var(--border-subtle);border-radius:18px;background:var(--bg-surface);box-shadow:0 24px 80px rgba(22,48,38,.18)}.artifact-dialog header,.artifact-dialog footer{display:flex;align-items:center;justify-content:space-between;gap:16px}.artifact-dialog header h2{margin:4px 0 0;font-size:22px}.artifact-dialog header>button{width:36px;height:36px;border:1px solid var(--border-subtle);border-radius:50%;background:transparent;color:var(--text-primary);font-size:22px;cursor:pointer}.artifact-dialog pre{min-height:280px;max-height:52vh;overflow:auto;margin:20px 0;padding:18px;border-radius:12px;background:var(--bg-base);color:var(--text-primary);font:13px/1.75 ui-monospace,SFMono-Regular,Consolas,monospace;white-space:pre-wrap;overflow-wrap:anywhere}.artifact-dialog label{display:grid;gap:7px;margin-top:16px;color:var(--text-secondary);font-size:12px}.artifact-dialog input,.artifact-dialog textarea{width:100%;box-sizing:border-box;padding:11px 12px;border:1px solid var(--border-default);border-radius:9px;background:var(--bg-base);color:var(--text-primary);font:inherit}.artifact-dialog textarea{resize:vertical;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;line-height:1.6}.artifact-dialog footer{padding-top:16px;border-top:1px solid var(--border-subtle)}.artifact-dialog footer>span{color:var(--text-muted);font-size:12px}.artifact-dialog footer div{display:flex;gap:8px}.artifact-dialog footer button{padding:8px 12px;border:1px solid var(--accent-border);border-radius:8px;background:transparent;color:var(--accent);cursor:pointer}.artifact-dialog footer .primary{background:var(--accent);color:white}.artifact-dialog button:disabled{opacity:.5}@media(max-width:760px){.artifact-dialog footer{align-items:flex-start;flex-direction:column}.artifact-dialog footer div{width:100%;flex-wrap:wrap}}@media(max-width:480px){.artifact-overlay{padding:8px}.artifact-dialog{padding:16px;border-radius:14px}}
.result-foot{display:flex;align-items:center;justify-content:space-between;gap:16px}.relevance{display:flex;align-items:center;gap:6px}.relevance>span{color:var(--text-muted);font-size:11px}.relevance button{padding:5px 8px;border:1px solid var(--border-subtle);border-radius:7px;background:transparent;color:var(--text-secondary);font-size:11px;cursor:pointer}.relevance button.selected{border-color:var(--accent);background:var(--accent-soft);color:var(--accent)}@media(max-width:560px){.result-foot{align-items:flex-start;flex-direction:column}.relevance{flex-wrap:wrap}}
</style>
