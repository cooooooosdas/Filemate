<template>
  <div class="knowledge-page">
    <header class="page-head"><div><h1>个人知识库</h1><p>从一份资料，到下一步学习。</p></div><router-link class="import-link" to="/ai-tools"><DocumentAdd :size="21" aria-hidden="true" />添加学习资料</router-link></header>

    <MotionSurface class="search-panel" aria-labelledby="search-heading">
      <h2 id="search-heading">想找什么知识？</h2>
      <div class="search-row">
        <label class="search-box"><Search :size="24" aria-hidden="true" /><span class="sr-only">检索知识库</span><input v-model.trim="query" name="knowledge_query" autocomplete="off" placeholder="概念、问题，或一段关键词" @keyup.enter="search" /></label>
        <button :disabled="searching || !query" @click="search">{{ searching ? '检索中…' : '开始检索' }}<ArrowRight :size="21" aria-hidden="true" /></button>
      </div>
      <div class="search-foot"><p class="privacy"><Lock :size="17" aria-hidden="true" />本机检索 · 原文可回看</p><span v-if="!selectedSource" class="scope-label">范围：全部资料</span><button v-else class="scope-chip" :disabled="searching" @click="selectedSource = ''" :aria-label="`清除检索范围：${scopeName}`">{{ scopeName }}<Close :size="17" aria-hidden="true" /></button></div>
    </MotionSurface>

    <nav class="evidence-entries" aria-label="继续学习与查看证据">
      <router-link v-if="graphEnabled" to="/knowledge-graph"><Share :size="27" aria-hidden="true" /><span><strong>连接知识</strong><span>核对概念与原文</span></span><ArrowUpRight :size="21" aria-hidden="true" /></router-link>
      <router-link to="/today"><Reading :size="27" aria-hidden="true" /><span><strong>继续复习</strong><span>查看今天的学习任务</span></span><ArrowUpRight :size="21" aria-hidden="true" /></router-link>
      <router-link to="/growth"><DataAnalysis :size="27" aria-hidden="true" /><span><strong>回看成长</strong><span>查看记录与评测依据</span></span><ArrowUpRight :size="21" aria-hidden="true" /></router-link>
    </nav>

    <section v-if="hasSearched" class="results" aria-live="polite">
      <div class="section-head"><h2>检索结果</h2><span>{{ results.length }} 条引用 · {{ searchedQuery }}</span></div>
      <div v-if="results.length" class="result-list">
        <article v-for="(result,index) in results" :key="result.chunk_id">
          <div class="citation"><b>[引用 {{ index + 1 }}]</b><span>{{ result.source_name }}</span><em>{{ result.page_number ? `第 ${result.page_number} 页` : `片段 ${result.chunk_index + 1}` }}</em></div>
          <p>{{ result.excerpt }}</p>
          <div class="result-foot"><router-link :to="{ path:'/ai-tools', query:{ source:result.source_id } }">回到资料<ArrowRight :size="18" aria-hidden="true" /></router-link><div class="relevance" role="group" :aria-label="`评价引用 ${index + 1} 是否相关`"><span>引用是否相关？</span><button type="button" :class="{ selected: feedbackState[result.chunk_id] === 1 }" :aria-pressed="feedbackState[result.chunk_id] === 1" @click="rateResult(result, index, 1)">相关</button><button type="button" :class="{ selected: feedbackState[result.chunk_id] === -1 }" :aria-pressed="feedbackState[result.chunk_id] === -1" @click="rateResult(result, index, -1)">不相关</button></div></div>
        </article>
      </div>
      <div v-else class="empty">没有找到相关片段，尝试换一个更具体的关键词。</div>
    </section>

    <section class="library">
      <div class="section-head library-heading"><div><h2>我的资料</h2><span>当前载入 {{ sources.length }} 份 · 选择资料继续学习</span></div><label v-if="sources.length" class="library-filter"><Search :size="18" aria-hidden="true" /><span class="sr-only">按资料名筛选</span><input v-model.trim="sourceFilter" placeholder="按资料名筛选" /></label></div>
      <div v-if="loading" class="empty" aria-live="polite">正在读取本地知识库…</div>
      <DataState v-else-if="error" :error="error" @retry="load" />
      <div v-else-if="sources.length" class="source-grid">
        <article v-for="source in visibleSources" :key="source.source_id" class="source-card" :class="{ expanded: expandedSource === source.source_id }">
          <div class="file-mark"><Document :size="28" :stroke-width="1.7" aria-hidden="true" /><span>{{ suffix(source.original_name) }}</span></div>
          <div class="source-copy"><h3>{{ source.original_name }}</h3><p>{{ source.text_length.toLocaleString('zh-CN') }} 字 · {{ formatDate(source.created_at) }}</p></div>
          <div class="source-actions">
            <router-link :to="{ path: '/ai-tools', query: { source: source.source_id } }" class="import-link">进入学习<ArrowRight :size="19" aria-hidden="true" /></router-link>
            <button type="button" :aria-expanded="expandedSource === source.source_id" @click="toggleArtifacts(source.source_id)">{{ expandedSource === source.source_id ? '收起学习链' : '学习链与产物' }}<ChevronDown :size="19" aria-hidden="true" /></button>
            <button type="button" class="scope-action" :aria-pressed="selectedSource === source.source_id" :disabled="searching" @click="scopeTo(source.source_id)"><Search :size="18" aria-hidden="true" />检索此资料</button>
            <button type="button" class="delete" :aria-label="`删除资料：${source.original_name}`" :disabled="deletingSource === source.source_id" @click="confirmDelete(source)"><Trash :size="19" aria-hidden="true" />{{ deletingSource === source.source_id ? '删除中…' : '删除' }}</button>
          </div>
          <div v-if="expandedSource === source.source_id" class="artifact-list">
            <p v-if="artifactLoading">正在加载…</p>
            <div v-else-if="artifactError" class="artifact-error" role="alert"><p>{{ artifactError }}</p><button type="button" @click="loadArtifacts(source.source_id)">重新读取</button></div>
            <template v-else>
              <div v-if="lineage" class="lineage-head"><div><strong>这份资料的学习链</strong><span>记录每一步，随时回到原始依据</span></div><b>{{ lineage.completed_stage_count }}/{{ lineage.total_stage_count }} 环已形成</b></div>
              <div v-if="lineage" class="lineage-rail">
                <article v-for="(stage,index) in lineage.stages" :key="stage.key" :class="stage.state"><span>{{ String(index + 1).padStart(2, '0') }}</span><strong>{{ stage.label }}</strong><p>{{ stage.primary }}</p><small>{{ stage.secondary }}</small></article>
              </div>
              <div v-if="artifacts.length" class="artifact-items"><button v-for="artifact in artifacts" :key="artifact.artifact_id" type="button" @click="openArtifact(artifact.artifact_id)"><span>{{ artifactLabel(artifact.artifact_type) }}</span><b>{{ artifact.title || '未命名产物' }}</b><em>打开</em></button></div>
              <p v-else>还没有学习产物，点击“进入学习”创建笔记或练习。</p>
            </template>
          </div>
        </article>
        <p v-if="!visibleSources.length" class="empty">没有匹配的资料，换个名称试试。</p>
      </div>
      <div v-else class="empty library-empty">
        <span class="empty-icon"><el-icon><FolderOpened /></el-icon></span>
        <strong>知识库还是空的</strong>
        <span>添加课件或笔记，随后阅读、提问、创建练习。</span>
        <router-link to="/ai-tools"><el-icon><DocumentAdd /></el-icon>添加第一份资料</router-link>
      </div>
    </section>

    <el-dialog v-model="dialogVisible" class="artifact-dialog" width="min(860px, calc(100vw - 24px))" :show-close="false" :before-close="beforeDialogClose" :title="selectedArtifact?.title || '学习产物'" append-to-body destroy-on-close>
      <template #header><header v-if="selectedArtifact"><div><p class="eyebrow">{{ artifactLabel(selectedArtifact.artifact_type) }}</p><h2 id="artifact-dialog-title">{{ selectedArtifact.title }}</h2></div><button type="button" aria-label="关闭学习产物" @click="closeArtifact"><Close :size="23" aria-hidden="true" /></button></header></template>
      <template v-if="selectedArtifact">
          <template v-if="editing">
            <label><span>标题</span><input v-model.trim="draftTitle" name="artifact_title" autocomplete="off" /></label>
            <label><span>内容 {{ structuredContent ? '（JSON）' : '' }}</span><textarea v-model="draftContent" name="artifact_content" rows="16"></textarea></label>
          </template>
          <div v-else-if="noteSections.length" class="artifact-reading"><section v-for="(section,index) in noteSections" :key="index"><h3>{{ section.title }}</h3><p>{{ section.content }}</p></section></div>
          <p v-else-if="typeof selectedArtifact.content === 'string'" class="artifact-reading plain-reading">{{ selectedArtifact.content }}</p>
          <div v-else class="artifact-handoff"><Reading :size="34" aria-hidden="true" /><h3>到学习工作区继续</h3><p>翻阅知识卡，或逐题练习并保存作答。</p><router-link class="import-link" :to="{path:'/ai-tools',query:{source:selectedArtifact.source_id,artifact:selectedArtifact.artifact_id}}">打开学习内容<ArrowRight :size="20" aria-hidden="true" /></router-link><details><summary>查看保存的内容</summary><pre>{{ formatArtifactContent(selectedArtifact.content) }}</pre></details></div>
          <footer><span>{{ selectedArtifact.metadata?.read_only_snapshot ? '历史题集只读；原有作答和错题仍可复练' : selectedArtifact.artifact_type === 'questions' ? '修改题目会保留已有作答的只读历史题集' : '修改会保存到本机知识库' }}</span><div><button type="button" @click="exportArtifact">导出</button><button v-if="!editing && !selectedArtifact.metadata?.read_only_snapshot" type="button" @click="editing = true">编辑</button><button v-if="editing" type="button" @click="cancelEdit">取消</button><button v-if="editing" class="primary" type="button" :disabled="saving" @click="saveArtifact">{{ saving ? '保存中…' : '保存修改' }}</button></div></footer>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowRight, ArrowUpRight, ChevronDown, Close, DataAnalysis, Document, DocumentAdd, FolderOpened, Lock, Reading, Search, Share, Trash } from '../icons'
import MotionSurface from '../components/MotionSurface.vue'
import { previewKnowledgeSourceDeletion, deleteKnowledgeSource, getKnowledgeArtifact, getKnowledgeArtifacts, getKnowledgeLineage, getKnowledgeSources, searchKnowledge, submitProductFeedback, updateKnowledgeArtifact, type KnowledgeArtifact, type KnowledgeLineage, type KnowledgeSearchResult, type KnowledgeSource } from '../services/api'
import DataState from '../components/DataState.vue'

const sources=ref<KnowledgeSource[]>([]); const results=ref<KnowledgeSearchResult[]>([]); const artifacts=ref<KnowledgeArtifact[]>([])
const query=ref(''); const selectedSource=ref(''); const loading=ref(true); const error=ref(''); const searching=ref(false); const hasSearched=ref(false); const expandedSource=ref(''); const artifactLoading=ref(false)
const feedbackState=ref<Record<string,1|-1>>({})
const selectedArtifact=ref<KnowledgeArtifact|null>(null); const editing=ref(false); const saving=ref(false); const draftTitle=ref(''); const draftContent=ref(''); const structuredContent=ref(false); const deletingSource=ref('')
const lineage=ref<KnowledgeLineage|null>(null)
const sourceFilter=ref(''); const searchedQuery=ref(''); const artifactError=ref('')
const graphEnabled=import.meta.env.VITE_ENABLE_KNOWLEDGE_GRAPH !== 'false'
const visibleSources=computed(()=>sources.value.filter(source=>source.original_name.toLocaleLowerCase().includes(sourceFilter.value.toLocaleLowerCase())))
const scopeName=computed(()=>sources.value.find(source=>source.source_id===selectedSource.value)?.original_name || '选中资料')
const dirty=computed(()=>editing.value && (draftTitle.value!==selectedArtifact.value?.title || draftContent.value!==formatArtifactContent(selectedArtifact.value?.content)))
const dialogVisible=computed({get:()=>Boolean(selectedArtifact.value),set:(value:boolean)=>{if(!value){selectedArtifact.value=null;editing.value=false}}})
const noteSections=computed(()=>selectedArtifact.value?.artifact_type==='notes' && Array.isArray(selectedArtifact.value.content?.sections)?selectedArtifact.value.content.sections:[])
let artifactEpoch=0
let disposed=false
const scopeTo=async(sourceId:string)=>{selectedSource.value=sourceId;await nextTick();document.querySelector<HTMLInputElement>('[name="knowledge_query"]')?.focus()}
const load=async()=>{loading.value=true;error.value='';try{sources.value=await getKnowledgeSources()}catch(e:any){error.value=e?.message||'知识库加载失败';ElMessage.error(error.value)}finally{loading.value=false}}
const search=async()=>{if(!query.value || searching.value)return;const term=query.value;const scope=selectedSource.value;searching.value=true;try{const found=await searchKnowledge(term,scope||undefined);if(disposed)return;results.value=found;searchedQuery.value=term;feedbackState.value={};hasSearched.value=true}catch(error:any){if(!disposed)ElMessage.error(error.message||'检索失败')}finally{searching.value=false}}
const rateResult=async(result:KnowledgeSearchResult,index:number,rating:1|-1)=>{const term=searchedQuery.value;try{await submitProductFeedback('retrieval',`${term}:${result.chunk_id}`,rating,{rank:index+1,score:result.score,query_length:term.length,query_token_count:term.trim().split(/\s+/).filter(Boolean).length,result_type:'chunk'});if(disposed || searchedQuery.value!==term)return;feedbackState.value[result.chunk_id]=rating;ElMessage.success('匿名相关性反馈已记录')}catch(error:any){ElMessage.error(error.message||'反馈保存失败')}}
const loadArtifacts=async(sourceId:string)=>{
  const epoch=++artifactEpoch
  expandedSource.value=sourceId;artifactLoading.value=true;artifactError.value='';artifacts.value=[];lineage.value=null
  try{const [items,chain]=await Promise.all([getKnowledgeArtifacts(sourceId),getKnowledgeLineage(sourceId)]);if(disposed || epoch!==artifactEpoch)return;artifacts.value=items;lineage.value=chain}
  catch(error:any){if(!disposed && epoch===artifactEpoch)artifactError.value=error.message||'学习链读取失败，请重试'}
  finally{if(epoch===artifactEpoch)artifactLoading.value=false}
}
const toggleArtifacts=(sourceId:string)=>{if(expandedSource.value===sourceId){artifactEpoch++;expandedSource.value='';lineage.value=null;artifacts.value=[];return}void loadArtifacts(sourceId)}
const suffix=(name:string)=>name.includes('.')?name.split('.').pop()!.slice(0,4).toUpperCase():'DOC'
const formatDate=(value:string)=>new Intl.DateTimeFormat('zh-CN',{month:'short',day:'numeric'}).format(new Date(value))
const artifactLabel=(type:string)=>({summary:'摘要',knowledge_cards:'知识卡',questions:'练习题',notes:'笔记',study_plan:'学习计划'}[type]||type)
const formatArtifactContent=(content:any)=>typeof content==='string'?content:JSON.stringify(content,null,2)
const syncDraft=(artifact:KnowledgeArtifact)=>{draftTitle.value=artifact.title;structuredContent.value=typeof artifact.content!=='string';draftContent.value=formatArtifactContent(artifact.content)}
const openArtifact=async(artifactId:string)=>{try{const artifact=await getKnowledgeArtifact(artifactId);selectedArtifact.value=artifact;syncDraft(artifact);editing.value=false}catch(error:any){ElMessage.error(error.message||'产物打开失败')}}
const allowLeaving=async()=>{if(saving.value){ElMessage.warning('正在保存，请稍后再离开');return false}if(!dirty.value)return true;try{await ElMessageBox.confirm('编辑内容尚未保存，离开会丢弃这些修改。','离开编辑？',{confirmButtonText:'丢弃并离开',cancelButtonText:'继续编辑',type:'warning'});return true}catch{return false}}
const closeArtifact=async()=>{if(await allowLeaving())dialogVisible.value=false}
const beforeDialogClose=async(done:()=>void)=>{if(await allowLeaving())done()}
const guardRefresh=(event:Event)=>{if(saving.value || dirty.value){event.preventDefault();ElMessage.info(saving.value?'正在保存，请稍后再刷新。':'编辑内容尚未保存，请先保存或取消编辑后再刷新。')}}
const guardUnload=(event:BeforeUnloadEvent)=>{if(saving.value || dirty.value){event.preventDefault();event.returnValue=''}}
onBeforeRouteLeave(allowLeaving)
const cancelEdit=()=>{if(selectedArtifact.value)syncDraft(selectedArtifact.value);editing.value=false}
const saveArtifact = async () => {
  if (!selectedArtifact.value || !draftTitle.value || saving.value || selectedArtifact.value.metadata?.read_only_snapshot) return
  const artifactId = selectedArtifact.value.artifact_id
  let content: any = draftContent.value
  if (structuredContent.value) {
    try { content = JSON.parse(draftContent.value) }
    catch { ElMessage.error('JSON 格式不正确，请检查逗号和引号'); return }
  }
  saving.value = true
  try {
    const updated = await updateKnowledgeArtifact(artifactId, draftTitle.value, content)
    if (selectedArtifact.value?.artifact_id === artifactId) {
      selectedArtifact.value = updated; syncDraft(updated); editing.value = false
    }
    const index = artifacts.value.findIndex(item => item.artifact_id === artifactId)
    if (index >= 0) artifacts.value[index] = updated
    ElMessage.success('学习产物已保存')
    if (updated.source_id && expandedSource.value === updated.source_id) {
      try {
        const [savedArtifacts, savedLineage] = await Promise.all([getKnowledgeArtifacts(updated.source_id), getKnowledgeLineage(updated.source_id)])
        if (expandedSource.value === updated.source_id) { artifacts.value = savedArtifacts; lineage.value = savedLineage }
      } catch { ElMessage.warning('保存已成功，历史列表暂未刷新，请重新打开资料') }
    }
  } catch (cause: any) { ElMessage.error(cause.message || '保存失败') }
  finally { saving.value = false }
}
const exportArtifact=()=>{if(!selectedArtifact.value)return;const structured=typeof selectedArtifact.value.content!=='string';const blob=new Blob([formatArtifactContent(selectedArtifact.value.content)],{type:structured?'application/json;charset=utf-8':'text/plain;charset=utf-8'});const url=URL.createObjectURL(blob);const link=document.createElement('a');link.href=url;link.download=`${selectedArtifact.value.title||'FileMate学习产物'}.${structured?'json':'txt'}`;link.click();URL.revokeObjectURL(url)}
const confirmDelete = async (source: KnowledgeSource) => {
  deletingSource.value = source.source_id
  try {
    const preview = await previewKnowledgeSourceDeletion(source.source_id)
    await ElMessageBox.confirm(`删除「${source.original_name}」及 ${preview.affected.artifacts} 个学习产物、${preview.affected.wrong_questions} 条错题？不可撤销，外部原文件保留。`, '确认删除范围', { confirmButtonText: '确认删除', cancelButtonText: '取消', type: 'warning' })
    const result = await deleteKnowledgeSource(source.source_id, preview.confirmation_token)
    sources.value = sources.value.filter(item => item.source_id !== source.source_id)
    if (expandedSource.value === source.source_id) { artifactEpoch++; expandedSource.value = ''; artifacts.value = []; lineage.value = null }
    if (selectedSource.value === source.source_id) selectedSource.value = ''
    results.value = results.value.filter(item => item.source_id !== source.source_id)
    ElMessage.success(`已删除资料及 ${result.affected.artifacts} 个产物、${result.affected.wrong_questions} 条错题`)
  } catch (error: any) { if (error !== 'cancel' && error !== 'close') ElMessage.error(error.message || '删除失败') }
  finally { deletingSource.value = '' }
}

onMounted(()=>{void load();window.addEventListener('filemate:before-refresh',guardRefresh);window.addEventListener('beforeunload',guardUnload)})
onUnmounted(()=>{disposed=true;artifactEpoch++;window.removeEventListener('filemate:before-refresh',guardRefresh);window.removeEventListener('beforeunload',guardUnload)})
</script>

<style scoped>
.knowledge-page { color:var(--text-primary); }
.page-head,.section-head { display:flex; justify-content:space-between; align-items:center; gap:20px; }
.page-head { margin-bottom:24px; }
.page-head p { margin:0; }
.import-link { display:inline-flex; align-items:center; justify-content:center; gap:9px; min-height:46px; padding:11px 17px; border-radius:11px; color:var(--hero-ink); background:var(--accent); text-decoration:none; font-size:16px; font-weight:600; flex-shrink:0; }
.import-link:hover { background:var(--accent-hover); }
.search-panel,.results,.library { border:1px solid var(--border-subtle); border-radius:22px; padding:26px; background:var(--bg-surface); }
.search-panel h2 { font-size:27px; margin:0 0 18px; letter-spacing:-.025em; }
.search-row { display:grid; grid-template-columns:1fr auto; gap:12px; }
.search-box { min-width:0; display:flex; align-items:center; gap:13px; min-height:62px; padding:0 18px; border:1px solid var(--border-strong); border-radius:14px; color:var(--accent); background:var(--bg-reading); }
.search-box:focus-within { outline:3px solid var(--accent-soft); border-color:var(--accent); }
.search-box input { min-width:0; width:100%; height:60px; border:0; outline:0; background:transparent; font-size:20px; color:var(--text-primary); }
.search-row>button { display:flex; align-items:center; justify-content:center; gap:16px; padding:0 23px; border:0; border-radius:14px; background:var(--accent); color:var(--hero-ink); font-size:18px; font-weight:600; }
button:disabled { opacity:.5; cursor:default; }
.search-foot { display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:12px; margin-top:15px; }
.privacy,.scope-label { font-size:15px; color:var(--text-secondary); margin:0; }
.privacy { display:flex; align-items:center; gap:7px; }
.scope-chip { max-width:100%; display:inline-flex; align-items:center; gap:9px; padding:8px 12px; border:1px solid var(--accent-border); border-radius:10px; background:var(--accent-soft); color:var(--accent); font-size:15px; overflow-wrap:anywhere; }
.scope-chip svg { flex-shrink:0; }
.evidence-entries { display:grid; grid-template-columns:repeat(3,1fr); gap:14px; margin:18px 0 28px; }
.evidence-entries a { min-width:0; display:flex; align-items:center; gap:14px; padding:20px; border:1px solid var(--border-subtle); border-radius:17px; background:var(--panel-tint); color:var(--accent); text-decoration:none; transition:transform var(--motion-fast),border-color var(--motion-fast); }
.evidence-entries a:hover { transform:translateY(-3px); border-color:var(--accent); }
.evidence-entries a>span { min-width:0; flex:1; display:grid; gap:7px; }
.evidence-entries a>svg { flex-shrink:0; }
.evidence-entries strong { font-size:20px; color:var(--text-primary); }
.evidence-entries span>span { font-size:15px; color:var(--text-secondary); }
.results { margin-bottom:24px; }
.section-head h2 { margin:0; font-size:26px; }
.section-head span { display:block; color:var(--text-secondary); font-size:15px; margin-top:8px; overflow-wrap:anywhere; }
.library-filter { display:flex; align-items:center; gap:8px; max-width:260px; padding:0 12px; min-height:44px; border:1px solid var(--border-subtle); border-radius:10px; color:var(--text-secondary); background:var(--bg-reading); }
.library-filter input { min-width:0; width:100%; border:0; outline:0; color:var(--text-primary); background:transparent; font-size:16px; }
.library-filter:focus-within { border-color:var(--accent); outline:2px solid var(--accent-soft); }
.source-grid { display:grid; gap:0; margin-top:15px; }
.source-card { display:grid; grid-template-columns:62px minmax(0,1fr); gap:14px 18px; padding:25px 0; border-bottom:1px solid var(--border-subtle); }
.source-card:last-child { border-bottom:0; padding-bottom:0; }
.file-mark { grid-row:span 2; width:62px; height:76px; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:5px; border-radius:13px; background:var(--accent-soft); color:var(--accent); }
.file-mark span { font:600 13px var(--font-mono); }
.source-copy { min-width:0; }
.source-copy h3 { margin:0; font-size:21px; font-weight:600; line-height:1.55; overflow-wrap:anywhere; }
.source-copy p { margin:7px 0 0; color:var(--text-secondary); font-size:15px; }
.source-actions { grid-column:2; display:flex; align-items:center; flex-wrap:wrap; gap:9px; }
.source-actions button { display:inline-flex; align-items:center; justify-content:center; gap:8px; min-height:44px; padding:9px 13px; border:1px solid var(--accent-border); border-radius:10px; background:transparent; color:var(--accent); font-size:16px; }
.source-actions button[aria-expanded=true] { background:var(--accent-soft); }
.source-actions button[aria-expanded=true] svg { transform:rotate(180deg); }
.source-actions button svg { transition:transform var(--motion-fast); }
.source-actions .delete { margin-left:auto; color:var(--text-secondary); border-color:transparent; }
.source-actions .delete:hover { color:var(--danger); border-color:var(--danger); }
.scope-action[aria-pressed=true] { background:var(--accent-soft); }
.artifact-list { grid-column:1/-1; padding-top:18px; }
.artifact-list>p,.artifact-error p { color:var(--text-secondary); font-size:16px; line-height:1.7; }
.artifact-error { padding:16px; border:1px solid var(--danger); border-radius:12px; }
.artifact-error button { min-height:44px; padding:8px 16px; border:1px solid var(--accent-border); border-radius:9px; color:var(--accent); background:transparent; }
.lineage-head { display:flex; align-items:center; justify-content:space-between; gap:16px; margin-bottom:17px; }
.lineage-head>div { display:grid; gap:6px; }
.lineage-head strong { font-size:21px; }
.lineage-head span,.lineage-head>b { font-size:15px; color:var(--text-secondary); }
.lineage-rail { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:10px; }
.lineage-rail article { padding:17px; border:1px solid var(--border-subtle); border-radius:12px; background:var(--bg-reading); }
.lineage-rail article.ready { border-color:var(--accent-border); background:var(--accent-soft); }
.lineage-rail article>span { color:var(--accent); font:600 14px var(--font-mono); }
.lineage-rail strong { display:block; margin:8px 0; font-size:18px; }
.lineage-rail p { margin:0 0 5px; font-size:16px; line-height:1.6; }
.lineage-rail small { display:block; font-size:14px; color:var(--text-secondary); line-height:1.65; overflow-wrap:anywhere; }
.artifact-items { display:grid; gap:8px; margin-top:16px; }
.artifact-items button { display:grid; grid-template-columns:80px minmax(0,1fr) auto; align-items:center; gap:12px; padding:14px; min-height:54px; text-align:left; border:1px solid var(--border-subtle); border-radius:11px; color:var(--text-primary); background:var(--bg-reading); font-size:17px; }
.artifact-items button:hover { background:var(--accent-soft); border-color:var(--accent-border); }
.artifact-items b { font-weight:500; overflow-wrap:anywhere; }
.artifact-items span,.artifact-items em { color:var(--accent); font-size:15px; font-style:normal; }
.empty { display:flex; flex-direction:column; align-items:center; gap:12px; padding:50px 24px; text-align:center; color:var(--text-secondary); font-size:17px; line-height:1.75; }
.empty-icon { display:grid; place-items:center; width:68px; height:68px; background:var(--accent-soft); color:var(--accent); border-radius:18px; font-size:30px; }
.library-empty strong { color:var(--text-primary); font-size:24px; }
.library-empty a { display:inline-flex; align-items:center; gap:9px; min-height:46px; padding:8px 16px; border-radius:10px; background:var(--accent); color:var(--hero-ink); text-decoration:none; margin-top:10px; }
.result-list { display:grid; gap:12px; margin-top:18px; }
.result-list article { border:1px solid var(--border-subtle); border-radius:14px; padding:20px; background:var(--bg-reading); }
.citation { display:flex; align-items:center; flex-wrap:wrap; gap:10px; font-size:15px; overflow-wrap:anywhere; }
.citation b { color:var(--accent); }
.citation em { font-style:normal; color:var(--text-secondary); }
.result-list p { font-size:18px; line-height:1.85; overflow-wrap:anywhere; }
.result-foot { display:flex; align-items:center; justify-content:space-between; gap:14px; flex-wrap:wrap; }
.result-foot a { display:inline-flex; align-items:center; gap:8px; min-height:44px; color:var(--accent); font-size:16px; }
.relevance { display:flex; flex-wrap:wrap; align-items:center; gap:8px; font-size:14px; color:var(--text-secondary); }
.relevance button { border:1px solid var(--border-subtle); border-radius:8px; padding:8px 12px; min-height:44px; background:transparent; color:var(--text-secondary); font-size:15px; }
.relevance button.selected { background:var(--accent-soft); border-color:var(--accent); color:var(--accent); }
.sr-only { position:absolute; width:1px; height:1px; padding:0; margin:-1px; overflow:hidden; clip:rect(0,0,0,0); white-space:nowrap; border:0; }
:global(.artifact-dialog) { max-height:88vh; display:flex; flex-direction:column; border-radius:22px; }
:global(.artifact-dialog .el-dialog__body) { overflow:auto; }
.artifact-dialog header,.artifact-dialog footer { display:flex; justify-content:space-between; align-items:center; gap:16px; }
.artifact-dialog h2 { font-size:26px; margin:8px 0 0; overflow-wrap:anywhere; color:var(--text-primary); }
.artifact-dialog .eyebrow { color:var(--accent); font-size:15px; margin:0; }
.artifact-dialog header button { display:grid; place-items:center; width:44px; height:44px; flex-shrink:0; border:1px solid var(--border-subtle); border-radius:12px; color:var(--text-primary); background:var(--bg-reading); }
.artifact-dialog pre { margin:12px 0 22px; padding:22px; border-radius:14px; background:var(--bg-reading); color:var(--text-primary); font:17px/1.85 var(--font-sans); white-space:pre-wrap; overflow-wrap:anywhere; }
.artifact-reading { padding:4px 8px 20px; color:var(--text-primary); }
.artifact-reading h3,.artifact-handoff h3 { font-size:23px; margin:22px 0 12px; }
.artifact-reading p,.plain-reading,.artifact-handoff p { font-size:18px; line-height:1.95; white-space:pre-wrap; overflow-wrap:anywhere; }
.artifact-handoff { padding:24px 8px; color:var(--text-primary); }.artifact-handoff>svg { color:var(--accent); }.artifact-handoff details { margin-top:26px; }.artifact-handoff summary { font-size:15px; min-height:44px; color:var(--text-secondary); cursor:pointer; }
.artifact-dialog label { display:grid; gap:10px; margin:16px 0; color:var(--text-secondary); font-size:16px; }
.artifact-dialog input,.artifact-dialog textarea { min-width:0; width:100%; border:1px solid var(--border-strong); border-radius:10px; padding:12px; background:var(--bg-reading); color:var(--text-primary); font:17px/1.75 var(--font-sans); }
.artifact-dialog textarea { resize:vertical; }
.artifact-dialog footer { padding-top:16px; border-top:1px solid var(--border-subtle); flex-wrap:wrap; }
.artifact-dialog footer>span { flex:1; min-width:200px; font-size:14px; line-height:1.65; color:var(--text-secondary); }
.artifact-dialog footer>div { display:flex; flex-wrap:wrap; gap:8px; }
.artifact-dialog footer button { display:flex; align-items:center; justify-content:center; min-height:44px; padding:8px 16px; border:1px solid var(--accent-border); border-radius:10px; color:var(--accent); background:transparent; font-size:16px; }
.artifact-dialog footer .primary { color:var(--hero-ink); background:var(--accent); }
@media(max-width:1100px) { .evidence-entries a { padding:18px 14px; gap:10px; }.evidence-entries span>span { font-size:14px; } }
@media(max-width:700px) { .page-head { align-items:flex-start; flex-direction:column; }.search-panel,.results,.library { padding:22px 18px; }.evidence-entries { grid-template-columns:1fr; gap:10px; }.evidence-entries a { padding:16px; }.evidence-entries a>span { display:flex; align-items:center; gap:12px; }.evidence-entries strong { font-size:18px; white-space:nowrap; }.library-heading { align-items:flex-start; flex-direction:column; }.library-filter { max-width:none; width:100%; }.lineage-head { align-items:flex-start; flex-direction:column; }.lineage-rail { grid-template-columns:repeat(2,minmax(0,1fr)); }.source-actions { grid-column:1/-1; }.file-mark { grid-row:auto; }.source-actions .delete { margin-left:0; } }
@media(max-width:480px) { .search-row { grid-template-columns:1fr; }.search-row>button { min-height:52px; }.search-box { padding:0 12px; }.search-box input { font-size:18px; }.search-panel h2 { font-size:25px; }.source-card { grid-template-columns:48px minmax(0,1fr); gap:13px; }.file-mark { width:48px; height:66px; }.source-copy h3 { font-size:20px; }.artifact-items button { grid-template-columns:62px minmax(0,1fr); }.artifact-items em { display:none; }.lineage-rail article { padding:13px; }.lineage-rail strong { font-size:17px; }.lineage-rail p { font-size:15px; }.evidence-entries a>span { gap:10px; }.evidence-entries span>span { font-size:14px; }.artifact-dialog pre { padding:16px; }.artifact-dialog footer>span { flex-basis:100%; } }
@media(prefers-reduced-motion:reduce) { .evidence-entries a,.source-actions button svg { transition:none; }.evidence-entries a:hover { transform:none; } }
</style>

