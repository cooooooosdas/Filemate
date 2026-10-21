<template>
  <div class="interview-page coach-surface">
    <header class="page-head">
      <div>
        <h1>口头讲解与模拟面试</h1>
        <p>用资料练表达，逐题回答并回看依据。</p>
      </div>
      <span class="status-pill" aria-live="polite"><i></i>{{ session?.status === 'completed' ? '本轮已完成' : session ? '面试进行中' : '准备就绪' }}</span>
    </header>

    <DataState v-if="resumeError && !session" :error="resumeError" @retry="restoreInterview(requestedInterviewId)" />
    <details v-if="!session" class="resume-panel">
      <summary class="resume-summary"><Document :size="24" aria-hidden="true" /><strong>接着上次练</strong><span>{{ historyLoading ? '正在读取…' : `${recentInterviews.length} 场已保存` }}</span></summary>
      <div class="resume-heading"><p>已提交回答保留。实战文字草稿可在同一浏览器标签页刷新恢复；本地录像不恢复。</p><button class="ghost" :disabled="historyLoading || loading" @click="loadRecent">刷新记录</button></div>
      <p v-if="historyLoading" role="status">正在读取练习记录…</p>
      <DataState v-else-if="historyError" :error="historyError" @retry="loadRecent" />
      <div v-else-if="recentInterviews.length" class="resume-list">
        <button v-for="item in recentInterviews" :key="item.interview_id" class="resume-item" :disabled="loading" @click="restoreInterview(item.interview_id)">
          <span><b>{{ item.target_role }}</b><small>{{ item.scenario }} · 已答 {{ item.current_index }} 题</small></span>
          <span class="resume-action">{{ item.status === 'completed' ? '回看回答' : '继续练习' }} →</span>
        </button>
      </div>
      <p v-else class="resume-empty">还没有练习记录，从下方创建第一场面试。</p>
      <p v-if="loading" role="status">正在准备面试…</p>
    </details>

    <section v-if="!session" class="setup-card">
      <p v-if="needsConfigurationChoice" class="focus-note" role="alert">这场历史记录的训练模式未被识别。原题与回答仍可回看；请重新选择训练方向后再开始。</p>
      <InterviewCreator v-if="!configurationState.ready || configurationState.enabled" :model-value="configuration" :draft="configurationState" :runtime-enabled="runtimeEnabled" :busy="loading || memoryBusy" @update:model-value="updateConfiguration" @save="savePreparation" @restore="restorePreparation" @reload="draftController.load()" />
      <div v-else class="setup-copy">
        <h2>选择你要训练的真实场景</h2>
        <p>选场景、定主题，然后开始回答。可以说出来，也可以全程打字。</p>
      </div>
      <fieldset v-if="configurationState.ready && !configurationState.enabled" class="mode-picker">
        <legend>训练场景</legend>
        <button v-for="mode in interviewModes" :key="mode" type="button" :aria-pressed="form.scenario === mode" :disabled="loading" @click="form.scenario = mode; needsConfigurationChoice = false"><component :is="modeIcons[mode]" :size="24" aria-hidden="true" /><span>{{ mode === 'HR面' ? 'HR 面' : mode }}</span></button>
      </fieldset>
      <div class="form-grid">
        <label>02 / 这次想练什么？<input v-model="form.targetRole" name="target_role" maxlength="120" autocomplete="off" placeholder="例如：数据库索引 / Java 后端开发" :disabled="loading" /></label>
        <fieldset v-if="configurationState.ready && !configurationState.enabled" class="difficulty-picker"><legend>选择难度</legend><button v-for="level in ['入门', '标准', '压力面']" :key="level" type="button" :aria-pressed="form.difficulty === level" :disabled="loading" @click="form.difficulty = level">{{ level }}</button></fieldset>
        <label v-if="configuration.execution_mode!=='timed'" class="source-field">结合哪份资料？（可选）<select v-model="form.sourceId" name="interview_source" :disabled="loading" @change="focusWrongId = ''; originGoalId = ''"><option value="">按题库训练</option><option v-for="source in knowledgeSources" :key="source.source_id" :value="source.source_id">{{ source.original_name }}</option></select><small>主动选择后才会使用；授权未确认时只用资料名组织问题。</small></label>
      </div>
      <p v-if="form.scenario === '压力面'" class="focus-note">通过质疑依据、反例和取舍练习临场回应；不会使用羞辱性提问。</p>
      <p v-if="form.scenario === '英语面'" class="focus-note">问题播报与语音识别切换到英语；也可以直接输入英文回答。</p>
      <fieldset v-if="form.scenario === '项目面' || configuration.execution_mode==='timed'" class="project-input">
        <legend>{{ configuration.category==='creator'?'讲解主题／商品的已知事实':'真实经历与资料事实' }}</legend>
        <label>项目名称<input v-model="projectName" maxlength="120" placeholder="例如：课程项目或比赛作品" :disabled="loading" /></label>
        <label>本场事实依据（未知信息请注明）<textarea v-model="projectDetails" maxlength="6000" rows="4" :disabled="loading" placeholder="说明目标、你的职责、设计选择和实际结果。未做或未验证的部分请明确写出。" /></label>
        <p>这段事实会随本场练习保存，只用于提问；不会自动修改简历或能力画像。</p>
      </fieldset>
      <label v-if="configuration.execution_mode!=='timed'" class="practice-consent"><input v-model="rememberForFuture" type="checkbox" :disabled="loading" />允许本场回答用于以后面试的连续追问（可随时遗忘）</label>
      <details v-if="configuration.execution_mode!=='timed'" class="practice-memory">
        <summary>选择一场已授权练习继续追问{{ selectedMemoryId ? ' · 已选择' : '' }}</summary>
        <p>仅列出你主动允许复用的练习。外发分析仍需另行授权；遗忘保留原回答与报告。</p>
        <button type="button" class="ghost" :disabled="memoryBusy || loading" @click="loadMemories">{{ memoryBusy ? '正在读取…' : '刷新可用练习' }}</button>
        <DataState v-if="memoryError" :error="memoryError" @retry="loadMemories" />
        <p v-else-if="!memoryBusy && !practiceMemories.length">还没有允许复用的已答练习，可以先完成本场训练。</p>
        <div v-for="item in practiceMemories" :key="item.memory_id" class="memory-row">
          <button type="button" :aria-pressed="selectedMemoryId === item.memory_id" :disabled="memoryBusy || loading" @click="selectedMemoryId = selectedMemoryId === item.memory_id ? null : item.memory_id">
            <strong>{{ item.target_role }}</strong><span>{{ item.scenario }} · 已答 {{ item.answer_count }} 题{{ selectedMemoryId === item.memory_id ? ' · 将继续追问' : '' }}</span>
          </button>
          <button type="button" class="ghost" :disabled="memoryBusy || loading" @click="forgetPractice(item.memory_id)">遗忘</button>
        </div>
        <button v-if="selectedMemoryId" type="button" class="ghost" :disabled="loading" @click="selectedMemoryId = null">本场不复用历史</button>
      </details>
      <p v-if="focusWrongId && form.sourceId" class="focus-note">本轮首题会依据该资料中的一条待纠错练习组织；参考答案不会放进题目。</p>
      <p v-if="form.scenario === '知识讲解'" class="focus-note">讲解会保存为练习记录；当前内容准确性待评估，语音节奏仅作参考。</p>
      <p v-if="reviewEnabled" class="focus-note">本轮先按规则选题，回答保存到学习空间。提交后可在复盘区主动授权内容分析；录像和视觉观察不会发给模型。</p>
      <label v-else class="legacy-consent"><input v-model="legacyExternalConsent" type="checkbox" />授权已配置模型对问题和回答提供四维参考评分；不发送本地录像。</label>
      <button class="primary start-practice" :disabled="loading || memoryBusy || needsConfigurationChoice || configurationState.busy || !configurationState.ready || (configurationState.enabled && (!!unavailableReason(configuration) || (configuration.execution_mode==='timed'&&!runtimeEnabled))) || !form.targetRole.trim() || (form.scenario === '项目面' && (!projectName.trim() || !projectDetails.trim()))" @click="begin"><VideoPlay :size="22" aria-hidden="true" />{{ loading ? '正在创建…' : configuration.execution_mode==='timed'?'准备实战':'开始逐题训练' }}<ArrowRight :size="22" aria-hidden="true" /></button>
      <DataState v-if="error" :error="error" @retry="begin" />
    </section>

    <template v-else>
      <p v-if="session.configuration && !session.runtime" class="focus-note" role="status">{{ session.configuration.origin === 'unavailable' ? session.configuration.error : session.configuration.duration_minutes ? `目标 ${session.configuration.duration_minutes} 分钟 · 当前为逐题训练，尚未启用计时` : '旧版训练 · 未记录目标时长' }}</p>
      <p v-if="requestedMedia.length" class="focus-note">本场准备使用：{{ requestedMedia.join('、') }}。请在训练伙伴区点击相应按钮开启；AI 分析需单独授权。也可以全程打字完成。</p>
      <section v-if="session.practice_context && (session.practice_context.mode === 'continuous' || session.practice_context.remember_for_future)" class="practice-session" aria-live="polite">
        <strong>{{ session.scenario }}{{ session.practice_context.mode === 'continuous' ? ' · 连续追问' : '' }}</strong>
        <span v-if="session.practice_context.project">项目：{{ session.practice_context.project.name }}</span>
        <span v-if="session.practice_context.memory_ref">{{ session.practice_context.memory_available ? '本轮已引用一场你授权的练习' : '历史复用已停止；已生成问题保留' }}</span>
        <span>{{ session.practice_context.remember_for_future ? '本场允许后续复用' : '本场不会用于后续追问' }}</span>
        <button v-if="session.practice_context.remember_for_future" type="button" class="ghost" :disabled="loading || memoryBusy || recording || videoRecording || videoStopping" @click="forgetCurrentPractice">停止复用本场</button>
        <DataState v-if="memoryError" :error="memoryError" />
      </section>
      <InterviewRuntimePanel v-if="session.runtime" :runtime="session.runtime" :busy="['save','advance','consent'].includes(coach.pending.value)" @command="runtimeAction" />
      <section v-if="session.runtime && coach.draftConflict.value" class="focus-note" role="alert"><strong>这段草稿属于原任务或原回答版本</strong><p>请先复制保留；清空旧草稿后再回答当前任务，避免串题。</p><blockquote>{{ answer }}</blockquote><button class="ghost" @click="discardRuntimeDraft">清空旧草稿，回答当前任务</button></section>
      <p v-if="session.runtime && answer.trim()" class="focus-note">{{ coach.draftRecoveryAvailable.value ? '草稿仅临时保存在当前浏览器标签页；关闭标签页或清除站点数据可能丢失。' : '浏览器存储不可用，刷新前请复制这段草稿。' }}</p>
      <p v-if="session.runtime && runtimeLocked && answer.trim()" class="focus-note">本场已停止接收回答。这段未提交文字仍在页面中，请复制保存：{{ answer }}</p>
      <section class="studio">
        <InterviewCoachPanel v-if="coachEnabled && coach.view.value" :pending-save="coach.replaySave.value" :answer-locked="runtimeLocked" :history-locked="!!session.runtime && !['finished','expired'].includes(session.runtime.status)" :answered-questions="session.turns.map(t=>({index:t.question_index,question:t.question}))" :completed="session.status==='completed'" :coach="coach.view.value" :draft="answer" :busy="coachBusy || recording || videoRecording || videoStopping || videoStarting || interviewAudio.busy.value || interviewVideo.busy.value" :total="session.questions.length" :editing="coachEditing" :composing="coach.composing.value" :external-consent="coach.snapshot.value?.external_consent || false" :current-answer="coach.snapshot.value?.current_attempt?.answer || ''" :error="coach.error.value?.message" :attempts="coachAttempts" :selected-attempt="selectedAttempt" :more-history="historyBefore != null" :history-error="coachHistoryError" :comparison="coachComparison" @update:draft="answer = $event" @composition="coach.setDraft(answer, $event)" @submit="submitCoach" @retry-analysis="coach.analyze()" @advance="advanceCoach" @reanswer="reanswerCoach" @select-question="focusCoach" @consent-change="coach.consent($event)" @load-history="loadCoachHistory" @select-attempt="selectedAttempt = $event" @reload="coach.refresh()">
          <template v-if="!audioEnabled" #answer-tools><button type="button" :disabled="coachBusy" @click="toggleRecording">{{ recording ? '停止录音' : '语音回答' }}</button><p class="speech-privacy">语音识别可能使用浏览器厂商的服务。摄像头和本地录像可在伙伴区按需开启。</p></template>
          <template #answer-media><InterviewAudioPanel v-if="audioEnabled" :takes="audioTakes" :phase="interviewAudio.captureState.value.phase" :capture-error="interviewAudio.captureState.value.error" :transcription="interviewAudio.transcription.value" :allowed="interviewAudio.allowed.value" :busy="interviewAudio.busy.value" :playback-blocked="interviewVideo.busy.value || recording || videoRecording || videoStarting || videoStopping" :blocked="coachBusy || recording || videoRecording || videoStopping || videoStarting || interviewVideo.busy.value" :locked="runtimeLocked || coach.replaySave.value || (coach.view.value?.phase==='feedback' && !coachEditing)" :error="interviewAudio.error.value" @record="recordAudio" @stop="interviewAudio.stop()" @consent="interviewAudio.consent($event)" @transcribe="transcribeAudio" @download="interviewAudio.download($event)" @remove="removeAudio" @play="coachSpeech.stop();interviewVideo.pausePlayback()" /><InterviewVideoLibrary v-if="videoEnabled" :takes="videoTakes" title="本题录像 · 停止后立即回看" :busy="interviewVideo.busy.value || interviewAudio.busy.value" @download="interviewVideo.download($event)" @remove="removeVideo" @play="coachSpeech.stop()" /></template>
          <template #history-media><InterviewAudioPanel v-if="audioEnabled" :takes="interviewAudio.items.value.filter(t=>t.attemptId===selectedAttempt?.attempt_id)" :phase="interviewAudio.captureState.value.phase" :capture-error="interviewAudio.captureState.value.error" :transcription="interviewAudio.transcription.value" :allowed="interviewAudio.allowed.value" :busy="interviewAudio.busy.value" :playback-blocked="interviewVideo.busy.value || recording || videoRecording || videoStarting || videoStopping" :blocked="coachBusy || recording || videoRecording || videoStopping || videoStarting || interviewVideo.busy.value" :locked="runtimeLocked || coach.replaySave.value || (coach.view.value?.phase==='feedback' && !coachEditing)" :error="interviewAudio.error.value" summary @record="recordAudio" @stop="interviewAudio.stop()" @consent="interviewAudio.consent($event)" @transcribe="transcribeAudio" @download="interviewAudio.download($event)" @remove="removeAudio" @play="coachSpeech.stop();interviewVideo.pausePlayback()" /><InterviewVideoLibrary v-if="videoEnabled" :takes="interviewVideo.items.value.filter(t=>t.attemptId===selectedAttempt?.attempt_id)" title="这版回答的录像" :busy="interviewVideo.busy.value || interviewAudio.busy.value" @download="interviewVideo.download($event)" @remove="removeVideo" @play="coachSpeech.stop()" /><video v-if="!videoEnabled && selectedAttempt && coachRecordings[selectedAttempt.attempt_id]" :src="coachRecordings[selectedAttempt.attempt_id].url" controls playsinline /><p v-else-if="!videoEnabled">这版没有当前页面录像；已保存文字仍可回看。</p></template>
          <template #summary><InterviewAudioPanel v-if="audioEnabled" :takes="interviewAudio.items.value" :phase="interviewAudio.captureState.value.phase" :capture-error="interviewAudio.captureState.value.error" :transcription="interviewAudio.transcription.value" :allowed="interviewAudio.allowed.value" :busy="interviewAudio.busy.value" :playback-blocked="interviewVideo.busy.value || recording || videoRecording || videoStarting || videoStopping" :blocked="coachBusy || recording || videoRecording || videoStopping || videoStarting || interviewVideo.busy.value" :locked="runtimeLocked || coach.replaySave.value || (coach.view.value?.phase==='feedback' && !coachEditing)" :error="interviewAudio.error.value" summary @record="recordAudio" @stop="interviewAudio.stop()" @consent="interviewAudio.consent($event)" @transcribe="transcribeAudio" @download="interviewAudio.download($event)" @remove="removeAudio" @play="coachSpeech.stop();interviewVideo.pausePlayback()" /><InterviewVideoLibrary v-if="videoEnabled" :takes="interviewVideo.items.value" title="整场录像汇总" :busy="interviewVideo.busy.value || interviewAudio.busy.value" @download="interviewVideo.download($event)" @remove="removeVideo" @play="coachSpeech.stop()" /><button type="button" class="ghost" @click="reset">再练一次</button></template>
        </InterviewCoachPanel>
        <DataState v-else-if="coachEnabled" :error="coach.error.value?.message || ''" :loading="!coach.error.value" @retry="coach.open(session.interview_id)" />
        <div v-else class="conversation-panel">
          <div class="progress-row"><span>第 {{ Math.min(session.current_index + 1, session.questions.length) }} / {{ session.questions.length }} 题</span><strong>{{ displayScore(session.overall_score) }}</strong></div>
          <div class="progress"><i :style="{ width: `${session.current_index / session.questions.length * 100}%` }"></i></div>

          <div v-if="session.status === 'active'" class="question-block">
            <p>训练问题</p>
            <span v-if="session.source_context?.source_name" class="source-evidence">依据：{{ session.source_context.source_name }} · {{ session.source_context.focus_wrong_id ? '待纠错练习首题' : session.source_context.mode === 'authorized_excerpt' ? '已授权片段' : '仅资料名' }}</span>
            <span v-if="sourceEvidenceLabel" class="source-evidence source-location-evidence" :class="{ unavailable: session.source_context?.source_evidence?.status === 'unavailable' }">{{ sourceEvidenceLabel }}</span>
            <h2>{{ session.current_question }}</h2>
            <textarea v-model="answer" name="interview_answer" autocomplete="off" aria-label="当前训练回答" rows="7" maxlength="12000" :disabled="loading" :placeholder="session.scenario === '知识讲解' ? '先解释概念，再说明推理过程和一个例子…' : '建议用“情境—任务—行动—结果”结构回答…'"></textarea>
            <div class="answer-actions">
              <button class="voice" :class="{ recording }" :disabled="loading" @click="toggleRecording">{{ recording ? '停止录音' : '语音回答' }}</button>
              <span>{{ answer.length }} 字</span>
              <button class="primary" :disabled="loading || videoRecording || videoStopping || recording || answer.trim().length < 4" @click="submit">{{ loading ? '保存中…' : videoRecording || videoStopping ? '先停止本地录像' : recording ? '先停止语音回答' : '提交并进入下一题' }}</button>
            </div>
            <small class="speech-privacy">语音识别由浏览器提供，可能使用浏览器厂商的在线服务；也可直接输入文字。</small>
            <div v-if="recording || fluencyMetrics" class="fluency-strip" aria-live="polite">
              <span><b>{{ recordingDuration }}</b> 秒回答时长</span>
              <span><b>{{ session.scenario === '英语面' ? liveWordsPerMinute : liveCharsPerMinute }}</b> {{ session.scenario === '英语面' ? '词/分钟' : '字/分钟' }}</span>
              <span><b>{{ fillerCount }}</b> 个口头语</span>
              <span><b>{{ longPauseCount }}</b> 次较长停顿</span>
              <small>{{ session.scenario === '英语面' ? '英语只记录识别节奏；节奏评分尚未校准，不计入内容分。' : '仅语音回答生成流畅度参考；有内容评估时计入总分的 15%' }}</small>
            </div>
            <div v-if="fluencyMarkers.length" class="live-timeline" aria-label="当前回答表达时间轴">
              <div class="timeline-track"><i v-for="marker in fluencyMarkers" :key="`${marker.kind}-${marker.second}`" :class="marker.kind" :style="{ left: markerPosition(marker.second, recordingDuration) }" /></div>
              <p><span>表达时间轴</span><b>{{ fluencyMarkers.length }} 个可复盘位置</b></p>
            </div>
          </div>

          <div v-else class="completion">
            <span class="score-ring" :class="{ unassessed: session.overall_score == null }">{{ session.overall_score == null ? '已记录' : session.overall_score.toFixed(0) }}</span>
            <div><p>本轮训练完成</p><h2>{{ scoreLabel }}</h2><button class="primary" @click="reset">再练一次</button><button v-if="session.source_context?.goal_id" class="ghost" @click="router.push({ path: '/goals', query: { goal: session.source_context.goal_id } })">返回目标复盘</button></div>
          </div>
        </div>

        <div class="interviewer-panel">
          <div class="avatar-stage" :class="{ speaking }">
            <div class="pulse pulse-one" aria-hidden="true"></div><div class="pulse pulse-two" aria-hidden="true"></div>
            <div class="avatar-face"><img :src="mascotUrl" alt="FileMate 形象伙伴" /></div>
            <div class="voice-bars" aria-hidden="true"><i v-for="n in 7" :key="n"></i></div>
          </div>
          <div><p class="role">FileMate 面试伙伴</p><p class="online"><i></i>在线 · {{ session.scenario === '英语面' ? '英语训练' : '中文普通话' }}</p></div>
          <template v-if="coachEnabled"><label class="coach-voice-consent"><input v-model="coachSpeech.voiceConsent.value" type="checkbox" /><span>允许将点击朗读的文字发给 Microsoft 自然语音服务</span></label><label class="coach-voice-select">朗读声线<select v-model="voiceId"><option v-for="voice in NATURAL_VOICES" :key="voice.voiceURI" :value="voice.voiceURI">{{ voice.name }}</option></select></label><div class="coach-voice-actions"><button type="button" class="ghost" :disabled="!coach.view.value?.question" @click="speakQuestion">朗读当前问题</button><button type="button" class="ghost" :disabled="!coach.view.value?.analysis" @click="readCoachFeedback">朗读可见反馈</button><button v-if="coachSpeech.speaking.value" type="button" class="ghost" @click="coachSpeech.stop">停止朗读</button></div><p v-if="coachSpeech.error.value" role="alert">{{ coachSpeech.error.value }}</p><p v-if="feedbackTooLong">反馈过长，朗读仅包含总评；各项建议请直接阅读。</p></template><button v-else class="ghost" :disabled="!session.current_question" @click="speakQuestion">重新播报问题</button>
          <InterviewVideoPanel v-if="videoEnabled" :camera="interviewVideo.camera.value" :phase="interviewVideo.captureState.value.phase" :busy="interviewVideo.busy.value" :blocked="coachBusy || runtimeLocked || coach.replaySave.value || interviewAudio.busy.value || recording || (coach.view.value?.phase==='feedback' && !coachEditing)" v-model:camera-id="interviewVideo.cameraId.value" v-model:microphone-id="interviewVideo.microphoneId.value" v-model:with-audio="interviewVideo.withAudio.value" :error="interviewVideo.error.value || videoIssue(interviewVideo.captureState.value.error)" @camera="interviewVideo.toggleCamera()" @record="recordVideo" @stop="interviewVideo.stop()" @refresh="interviewVideo.refresh()" @preview="cameraVideo=$event">
            <div v-if="reviewEnabled" class="vision-controls">
              <button :disabled="interviewVideo.camera.value.phase!=='ready' || interviewVideo.busy.value || vision.state.value === 'loading'" @click="toggleVision">{{ vision.state.value === 'loading' ? '加载视觉模型…' : ['ready', 'observing'].includes(vision.state.value) ? '关闭本地视觉观察' : '开启本地视觉观察' }}</button>
              <small role="status">{{ vision.hint.value }}</small>
              <small>每秒约2次采样；观察头部、眼部与嘴角动作，不判断情绪或注意力。</small>
              <section v-if="vision.state.value === 'observing'" class="live-face" aria-label="实时面部动作">
                <h3>实时面部动作</h3><p>{{ vision.live.value?.status || '等待有效画面…' }}</p>
                <template v-if="vision.live.value">
                  <div v-for="item in [{key: 'smile', label: '微笑动作'}, {key: 'brow', label: '皱眉动作'}, {key: 'jaw', label: '张口动作'}] as const" :key="item.key" class="face-reading">
                    <span>{{ item.label }}</span><strong>{{ vision.live.value[item.key] ?? '待测' }}{{ vision.live.value[item.key] == null ? '' : ' / 100' }}</strong>
                    <meter v-if="vision.live.value[item.key] != null" :value="vision.live.value[item.key]!" min="0" max="100" :aria-label="item.label" />
                  </div>
                  <p>头部偏转 {{ vision.live.value.yaw == null ? '待测' : `${vision.live.value.yaw}°` }} · 俯仰 {{ vision.live.value.pitch == null ? '待测' : `${vision.live.value.pitch}°` }}</p>
                </template>
                <small>0–100 为模型动作系数换算，不是开心、紧张或疑惑的概率；光线不足或无人脸时停止读数。实时系数不保存、不上传，不用于面试评分。</small>
              </section>
            </div>
          </InterviewVideoPanel>
          <div v-else class="camera-dock" :class="{ active: cameraActive }">
            <div class="camera-preview">
              <video ref="cameraVideo" v-show="cameraActive" autoplay muted playsinline />
              <div v-if="!cameraActive" class="camera-placeholder">
                <span>你的面试画面</span>
                <small>开启后仅在本机浏览器预览</small>
              </div>
            </div>
            <button type="button" class="camera-toggle" @click="toggleCamera">
              {{ cameraActive ? '关闭摄像头' : '开启摄像头' }}
            </button>
            <button
              type="button"
              class="record-toggle"
              :class="{ recording: videoRecording }"
              :disabled="!cameraActive || !recordingSupported || videoStopping || videoStarting || loading || vision.state.value === 'loading'"
              @click="toggleVideoRecording"
            >
              {{ videoRecording ? `停止本地录像 · ${videoRecordingDuration}s` : videoStopping ? '正在保存本地录像…' : '开始本地录像（含声音）' }}
            </button>
            <small v-if="cameraError" class="camera-error">{{ cameraError }}</small>
            <small v-else-if="videoRecording">正在浏览器内存录制{{ recordingHasAudio ? '画面与声音' : '静音画面' }}，不会上传</small>
            <small v-else>预览默认不录像；本地录像需单独授权麦克风，刷新后清除</small>
            <div v-if="reviewEnabled" class="vision-controls">
              <button :disabled="!cameraActive || videoRecording || vision.state.value === 'loading'" @click="toggleVision">{{ vision.state.value === 'loading' ? '加载视觉模型…' : ['ready', 'observing'].includes(vision.state.value) ? '关闭本地视觉观察' : '开启本地视觉观察' }}</button>
              <small role="status">{{ vision.hint.value }}</small>
              <small>每秒约2次采样；观察头部、眼部与嘴角动作，不判断情绪或注意力。</small>
              <section v-if="vision.state.value === 'observing'" class="live-face" aria-label="实时面部动作">
                <h3>实时面部动作</h3><p>{{ vision.live.value?.status || '等待有效画面…' }}</p>
                <template v-if="vision.live.value">
                  <div v-for="item in [{key: 'smile', label: '微笑动作'}, {key: 'brow', label: '皱眉动作'}, {key: 'jaw', label: '张口动作'}] as const" :key="item.key" class="face-reading">
                    <span>{{ item.label }}</span><strong>{{ vision.live.value[item.key] ?? '待测' }}{{ vision.live.value[item.key] == null ? '' : ' / 100' }}</strong>
                    <meter v-if="vision.live.value[item.key] != null" :value="vision.live.value[item.key]!" min="0" max="100" :aria-label="item.label" />
                  </div>
                  <p>头部偏转 {{ vision.live.value.yaw == null ? '待测' : `${vision.live.value.yaw}°` }} · 俯仰 {{ vision.live.value.pitch == null ? '待测' : `${vision.live.value.pitch}°` }}</p>
                </template>
                <small>0–100 为模型动作系数换算，不是开心、紧张或疑惑的概率；光线不足或无人脸时停止读数。实时系数不保存、不上传，不用于面试评分。</small>
              </section>
            </div>
          </div>
        </div>
      </section>

      <CompanionCard
        v-if="session.status === 'completed'"
        class="completion-companion"
        :mood="completionCompanion.mood"
        :title="completionCompanion.title"
        :message="completionCompanion.message"
        :evidence="completionCompanion.evidence"
        route="/growth"
        action-label="查看成长证据"
      />

      <section v-if="!coachEnabled && session.latest_evaluation" class="evaluation">
        <div class="evaluation-head"><div><p class="eyebrow">{{ session.latest_evaluation.scoring_mode === 'llm' ? '模型评估 · 仅供训练参考' : '规则练习 · 内容待评估' }}</p><h2>{{ session.latest_evaluation.feedback }}</h2></div><strong>{{ displayScore(session.latest_evaluation.score) }}</strong></div>
        <div class="dimension-grid"><div v-for="(score, name) in session.latest_evaluation.dimensions" :key="name"><span>{{ name }}</span><b>{{ score.toFixed(0) }}</b><i><em :style="{ width: `${score}%` }"></em></i></div></div>
      </section>

      <section v-if="session.turns.length && (!coachEnabled || coach.view.value?.phase === 'summary')" class="review-list">
        <h2>回答记录</h2>
        <details v-for="(turn, index) in session.turns" :key="turn.turn_id" :open="index === session.turns.length - 1">
          <summary><span>Q{{ index + 1 }} · {{ turn.question }}</span><b>{{ displayScore(turn.score) }}</b></summary>
          <small>{{ turn.scoring_mode === 'llm' ? '模型评估 · 仅供训练参考' : turn.scoring_mode === 'local_fallback' ? '规则练习 · 不计入能力均分' : '历史评分来源未确认 · 不计入能力均分' }}</small>
          <p>{{ turn.answer }}</p><small>{{ turn.feedback }}</small>
          <div v-if="localRecordings[index]" class="local-replay">
            <div class="replay-head"><strong>本地录像回放</strong><span>仅保留在当前页面，未上传</span></div>
            <video :id="`interview-replay-${index}`" :src="localRecordings[index].url" controls playsinline />
            <div class="recording-actions"><button class="ghost" @click="downloadRecording(index)">下载本地录像</button><button class="ghost" @click="removeRecording(index)">删除这段本地录像</button></div>
            <div v-if="turn.visual_metrics?.events?.length" class="marker-list"><button v-for="(event, eventIndex) in turn.visual_metrics.events" :key="eventIndex" :disabled="turn.visual_metrics.timeline_origin !== 'recording'" @click="seekRecording(index, event.start)">{{ event.start.toFixed(1) }}s · {{ visualLabels[event.kind] }}</button></div>
            <div v-if="turn.fluency_metrics?.markers?.length && turn.fluency_metrics.recording_offset_seconds != null && turn.visual_metrics?.timeline_origin === 'recording'" class="replay-timeline">
              <div class="timeline-track">
                <button v-for="marker in turn.fluency_metrics.markers" :key="`${marker.kind}-${marker.second}`" type="button" :class="marker.kind" :style="{ left: markerPosition(marker.second + turn.fluency_metrics.recording_offset_seconds, localRecordings[index].duration) }" :aria-label="`${marker.label}，${marker.second.toFixed(1)} 秒`" @click="seekRecording(index, marker.second + turn.fluency_metrics.recording_offset_seconds)" />
              </div>
              <div class="marker-list"><button v-for="marker in turn.fluency_metrics.markers" :key="`label-${marker.kind}-${marker.second}`" type="button" @click="seekRecording(index, marker.second + turn.fluency_metrics.recording_offset_seconds)"><i :class="marker.kind" />{{ marker.second.toFixed(1) }}s · {{ marker.label }}</button></div>
            </div>
          </div>
          <div v-else-if="turn.fluency_metrics?.markers?.length" class="evidence-only-timeline">
            <strong>表达时间轴</strong><span>本轮未保存录像，时间点仍作为评分证据保留</span>
            <div class="marker-list"><span v-for="marker in turn.fluency_metrics.markers" :key="`${marker.kind}-${marker.second}`"><i :class="marker.kind" />{{ marker.second.toFixed(1) }}s · {{ marker.label }}</span></div>
          </div>
        </details>
      </section>
      <InterviewReviewPanel v-if="reviewEnabled || session.turns.length" :read-only="!reviewEnabled" :session="session" :analysis-busy="coachEnabled && coach.pending.value==='analysis'" :coach-mode="coachEnabled" :recording-indexes="Object.keys(localRecordings).map(Number)" :media-busy="videoRecording || videoStopping || recording || loading || interviewAudio.busy.value || interviewVideo.busy.value" @updated="reviewUpdated" @deleted="deletedInterview" @cleared="vision.reset()" @seek="seekRecording" />
    </template>
  </div>
</template>

<script setup lang="ts">
import { saveDownload } from '../services/downloads'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  answerInterview,
  getKnowledgeSources,
  getInterview,
  getLearningAnalytics,
  getInterviewReviewStatus,
  getInterviewPracticeMemories,
  previewInterviewMemoryForget,
  forgetInterviewMemory,
  startInterview,
  type InterviewFluencyMarker,
  type InterviewFluencyMetrics,
  type InterviewSession,
  type InterviewPracticeMemory,
  type KnowledgeSource,
  type LearningAnalytics
} from '../services/api'
import InterviewAudioPanel from '../components/InterviewAudioPanel.vue'
import { useInterviewAudio } from '../interview/useInterviewAudio'
import { bindingKey } from '../interview/audio-collection'
import InterviewCoachPanel from '../components/InterviewCoachPanel.vue'
import { useInterviewCoach } from '../interview/useInterviewCoach'
import { useInterviewCoachSpeech } from '../interview/useInterviewCoachSpeech'
import { NATURAL_VOICES } from '../digital-human/natural-speech'
import { getInterviewAttempts } from '../services/api'
import type { AttemptView } from '../types/interviewCoach'
import CompanionCard from '../components/CompanionCard.vue'
import DataState from '../components/DataState.vue'
import InterviewReviewPanel from '../components/InterviewReviewPanel.vue'
import InterviewCreator from '../components/InterviewCreator.vue'
import InterviewRuntimePanel from '../components/InterviewRuntimePanel.vue'
import type { RuntimeKind } from '../types/interviewRuntime'
import { prepareInterviewRuntime } from '../services/api'
import { configurationForScenario, configurationForSession, createDraftController, legacyScenario, unavailableReason } from '../interview/configuration'
import { getInterviewConfiguration, saveInterviewDraft } from '../services/api'
import type { InterviewConfiguration } from '../types/interviewConfiguration'
import { useInterviewVision } from '../interview/useInterviewVision'
import { visualLabels } from '../interview/observations'
import { useInterviewVideo } from '../interview/useInterviewVideo'
import { videoIssue } from '../interview/video-messages'
import { watchMediaEnvironment } from '../interview/media-lifecycle'
import InterviewVideoPanel from '../components/InterviewVideoPanel.vue'
import InterviewVideoLibrary from '../components/InterviewVideoLibrary.vue'
import { publishCompanionEvent, type CompanionMood } from '../composables/useCompanion'
import mascotUrl from '../assets/filemate-mascot.png'
import '../styles/interview-practice.css'
import { hasInterviewDraft } from '../navigation/route-state'
import { ArrowRight, Briefcase, Code, Collection, Conversation, Document, Language, Reading, School, ShieldCheck, Trophy, VideoPlay } from '../icons'

const form = ref({ targetRole: '', scenario: '知识讲解', difficulty: '标准', sourceId: '' })
const specialistModes = ['技术面', '项目面', '算法面', 'HR面', '压力面', '英语面']
const interviewModes = ['知识讲解', ...specialistModes, '求职面试', '竞赛答辩', '保研复试']
const modeIcons: Record<string, typeof Reading> = { '知识讲解': Reading, '技术面': Code, '项目面': Collection, '算法面': Code, 'HR面': Conversation, '压力面': ShieldCheck, '英语面': Language, '求职面试': Briefcase, '竞赛答辩': Trophy, '保研复试': School }
const configuration = ref<InterviewConfiguration>(configurationForScenario('知识讲解', '标准')!)
const needsConfigurationChoice = ref(false)
const draftController = createDraftController({ read: getInterviewConfiguration, save: saveInterviewDraft }, undefined, state => { configurationState.value = state })
const configurationState = ref(draftController.state)
function updateConfiguration(value: InterviewConfiguration): void {
  needsConfigurationChoice.value = false
  configuration.value = value
  form.value.scenario = legacyScenario(value) || form.value.scenario
  form.value.difficulty = value.difficulty
}
async function savePreparation(): Promise<void> {
  const before = preparationSnapshot()
  await draftController.save({ configuration: configuration.value, target_role: form.value.targetRole, source_id: form.value.sourceId, project_name: projectName.value, project_details: projectDetails.value })
  if (!configurationState.value.error && preparationSnapshot() === before) initialPreparation.value = before
}
function restorePreparation(): void {
  const saved = configurationState.value.remote.content
  if (!saved) return
  updateConfiguration({ ...saved.configuration })
  form.value.targetRole = saved.target_role
  form.value.sourceId = saved.source_id
  projectName.value = saved.project_name; projectDetails.value = saved.project_details
  focusWrongId.value = ''; originGoalId.value = ''
  rememberForFuture.value = false; selectedMemoryId.value = null; legacyExternalConsent.value = false
  initialPreparation.value = preparationSnapshot()
}
const projectName = ref('')
const projectDetails = ref('')
const rememberForFuture = ref(false)
const selectedMemoryId = ref<string | null>(null)
const practiceMemories = ref<InterviewPracticeMemory[]>([])
const memoryBusy = ref(false)
const memoryError = ref('')
const route = useRoute()
const router = useRouter()
const focusWrongId = ref(typeof route.query.focus === 'string' ? route.query.focus : '')
const originGoalId = ref(typeof route.query.goal === 'string' ? route.query.goal : '')
const recentInterviews = ref<LearningAnalytics['recent_interviews']>([])
const historyLoading = ref(false)
const historyError = ref('')
const resumeError = ref('')
const requestedInterviewId = ref('')
let disposed = false
let disposeMediaEnvironment: (()=>void) | undefined
let syncingSessionTarget: string | null = null
const knowledgeSources = ref<KnowledgeSource[]>([])
const session = ref<InterviewSession | null>(null)
const requestedMedia = computed(() => {
  const preferences = session.value?.configuration?.media_preferences
  const names = { camera:'摄像头', microphone:'麦克风', transcription:'语音转写', local_recording:'本地录像', post_analysis:'AI 分析' }
  return preferences ? (Object.keys(names) as (keyof typeof names)[]).filter(key => preferences[key]).map(key => names[key]) : []
})
const coachEnabled = import.meta.env.VITE_ENABLE_INTERVIEW_COACH === 'true'
const audioEnabled = coachEnabled && import.meta.env.VITE_ENABLE_INTERVIEW_AUDIO === 'true'
const videoEnabled = coachEnabled && import.meta.env.VITE_ENABLE_INTERVIEW_VIDEO === 'true'
const coach = useInterviewCoach()
const runtimeEnabled = computed(()=>coachEnabled && configurationState.value.runtimeEnabled===true)
const runtimeLocked = computed(()=>!!session.value?.runtime && session.value.runtime.status!=='running')
let preparationKey='', preparationFingerprint=''
async function runtimeAction(kind:RuntimeKind){
 if(kind==='finish'){try{await ElMessageBox.confirm(answer.value.trim()?'未提交文字不会写入报告，请先复制保存。确定提前结束本场？':'已保存回答保留，可随时生成复盘报告。确定提前结束？','结束实战',{confirmButtonText:'结束本场',cancelButtonText:'继续训练'})}catch{return}}
 if(kind==='finish'||kind==='skip'){await interviewVideo.stop();await interviewAudio.stop();stopSpeechRecording();stopVideoRecording(true);coachSpeech.stop()}
 const updated=await coach.runtimeAction(kind)
 if(updated && kind==='skip'){answer.value='';coach.setDraft('');coachEditing.value=false}
}
const coachSpeech = useInterviewCoachSpeech()
const voiceId = ref<string>('zh-CN-XiaoxiaoNeural')
const coachEditing = ref(false)
const coachBusy = computed(() => coach.pending.value !== 'idle')
const currentQuestionIndex = computed(() => coachEnabled ? (coach.snapshot.value?.displayed_index ?? 0) : (session.value?.current_index ?? 0))
const coachAttempts = ref<AttemptView[]>([])
const selectedAttempt = ref<AttemptView|null>(null)
const historyBefore = ref<number|null>(null)
const coachHistoryError = ref('')
const coachRecordings = ref<Record<string,LocalRecording>>({})
let mediaEpoch = 0
let draftMediaId = crypto.randomUUID()
const audioDraftEpoch=ref(0)
const coachComparison = computed(() => {
 const turn = coach.snapshot.value?.session.turns.find(t => t.question_index === currentQuestionIndex.value) as unknown as {attempt_comparison?:{first:AttemptView;last:AttemptView;scores_comparable:boolean}} | undefined
 return turn?.attempt_comparison ?? null
})
const interviewAudio=useInterviewAudio(text=>{answer.value=text},()=>{coachSpeech.stop();interviewVideo.pausePlayback()},()=>coach.replaySave.value)
const interviewVideo=useInterviewVideo({
 blocked:()=>coachBusy.value || runtimeLocked.value || recording.value || interviewAudio.busy.value || (coach.view.value?.phase==='feedback' && !coachEditing.value),
 pendingSave:()=>coach.replaySave.value,
 stopOthers:async()=>{coachSpeech.stop();window.speechSynthesis?.cancel();stopSpeechRecording();await interviewAudio.stop();interviewAudio.pausePlayback()},
 finishVision:()=>{vision.finish()}
})
const videoTakes=computed(()=>interviewVideo.items.value.filter(t=>t.binding.questionIndex===currentQuestionIndex.value))
async function recordVideo(){
 await interviewVideo.record()
 if(interviewVideo.captureState.value.phase==='recording' && reviewEnabled.value && cameraVideo.value)vision.observe(cameraVideo.value,interviewVideo.captureState.value.started)
}
async function removeVideo(id:string){
 try{await ElMessageBox.confirm('删除这段本页录像，已保存回答与观察摘要保留。需要保留录像请先导出。','删除录像',{confirmButtonText:'删除片段',cancelButtonText:'保留录像'})}catch{return}
 interviewVideo.remove(id)
}
const mediaBinding=computed(()=>{
 const s=coach.snapshot.value
 return coachEnabled&&s&&s.phase!=='summary'?{sessionId:s.session.interview_id,questionIndex:s.displayed_index,attemptId:s.current_attempt?.attempt_id??null,token:`${s.session.runtime?.version_token??'practice'}:${audioDraftEpoch.value}`}:null
})
const audioTakes=computed(()=>interviewAudio.items.value.filter(t=>t.binding.questionIndex===currentQuestionIndex.value))
const audioBinding=computed(()=>audioEnabled?mediaBinding.value:null)
function syncAudioContext(){if(audioEnabled)interviewAudio.context(audioBinding.value)}
watch(runtimeLocked,locked=>{if(locked&&audioEnabled)void interviewAudio.stop();if(locked&&videoEnabled)void interviewVideo.stop()})
watch(mediaBinding,value=>{if(videoEnabled && coach.snapshot.value?.phase!=='summary')interviewVideo.context(value)},{deep:true})
watch(audioBinding,()=>{if(coach.snapshot.value?.phase!=='summary')syncAudioContext()},{deep:true})
async function recordAudio(){
 if(!audioEnabled || runtimeLocked.value || coachBusy.value || coach.replaySave.value || interviewVideo.busy.value)return
 const old=audioTakes.value.filter(t=>!t.attemptId && bindingKey(t.binding)===bindingKey(audioBinding.value))
 if(old.length){try{await ElMessageBox.confirm('重新录音会删除本题未提交的旧录音；需要保留请先导出。','重新录音',{confirmButtonText:'删除旧录音并重录',cancelButtonText:'保留旧录音'})}catch{return};for(const t of old)interviewAudio.remove(t.id)}
 syncAudioContext();await interviewAudio.record()
}
async function removeAudio(id:string){try{await ElMessageBox.confirm('此操作只删除页面中的这段录音；已保存回答摘要及下载文件保留。','删除本机录音',{confirmButtonText:'删除这段',cancelButtonText:'保留'})}catch{return};interviewAudio.remove(id)}
function transcribeAudio(){
 if(interviewVideo.busy.value || !audioEnabled || runtimeLocked.value || coachBusy.value)return
 syncAudioContext();interviewAudio.transcribe(session.value?.scenario==='英语面'?'en-US':'zh-CN',answer.value)
}
const feedbackText = computed(() => [coach.view.value?.feedback, ...Object.values(coach.view.value?.analysis?.areas || {}).flatMap(a => [a.evidence, a.suggestion])].filter(Boolean).join('。'))
const feedbackTooLong = computed(() => Array.from(feedbackText.value).length > 5000)
function readCoachFeedback(){if(interviewAudio.busy.value || interviewVideo.busy.value)return;interviewVideo.pausePlayback();interviewAudio.pausePlayback();coachSpeech.read(feedbackTooLong.value ? (coach.view.value?.feedback || '') : feedbackText.value,voiceId.value)}
async function loadCoachHistory(more=false){
 const state=coach.snapshot.value, a=state?.current_attempt
 if(!state || !a) return
 const id=state.session.interview_id, aid=a.attempt_id
 try {const page=await getInterviewAttempts(id,a.turn_id,{limit:10,...(more && historyBefore.value ? {before_version:historyBefore.value}:{})});if(disposed || coach.snapshot.value?.session.interview_id!==id || coach.snapshot.value.current_attempt?.attempt_id!==aid)return;coachAttempts.value=more?[...coachAttempts.value,...page.items]:page.items;historyBefore.value=page.next_before_version;coachHistoryError.value=''}
 catch {coachHistoryError.value='历史读取失败，可重新展开重试。'}
}
function clearCoachQuestion(){
 audioDraftEpoch.value++;interviewAudio.invalidate();interviewVideo.invalidate();
 mediaEpoch++;draftMediaId=crypto.randomUUID();coachSpeech.stop();stopSpeechRecording();vision.reset();fluencyMetrics.value=undefined;fluencyMarkers.value=[];recordingDuration.value=0;coachAttempts.value=[];selectedAttempt.value=null;historyBefore.value=null
}
async function submitCoach(){
 if(recording.value || videoRecording.value || videoStopping.value || videoStarting.value || interviewAudio.busy.value || interviewVideo.busy.value)return
 coachSpeech.stop();coach.setDraft(answer.value)
 const index=currentQuestionIndex.value, mediaId=draftMediaId
 const metrics=fluencyMetrics.value ? {duration_seconds:fluencyMetrics.value.duration_seconds,filler_count:fluencyMetrics.value.filler_count,long_pause_count:fluencyMetrics.value.long_pause_count,source:fluencyMetrics.value.source,markers:fluencyMetrics.value.markers,recording_offset_seconds:fluencyMetrics.value.recording_offset_seconds} : undefined
 const frozen=audioEnabled?interviewAudio.freeze(answer.value):null
 const visual=reviewEnabled.value?vision.finish():undefined
 const frozenVideo=videoEnabled?interviewVideo.freeze(answer.value,visual):null
 const saved=await coach.submit({fluency_metrics:audioEnabled?frozen?.metrics:metrics,visual_metrics:videoEnabled?frozenVideo?.metrics:visual})
 if(!saved || disposed)return
 const record=localRecordings.value[index]
 const savedId=saved.receipt.attempt_id
 if(frozen && typeof savedId==='string')interviewAudio.receipt(frozen,savedId,saved.snapshot.session.interview_id)
 if(frozenVideo && typeof savedId==='string')interviewVideo.receipt(frozenVideo,savedId,saved.snapshot.session.interview_id)
 if(record?.ownerId===mediaId && typeof savedId==='string'){record.ownerId=savedId;coachRecordings.value={...coachRecordings.value,[savedId]:record}}
 if(saved.snapshot.current_attempt?.attempt_id!==savedId){const next={...localRecordings.value};delete next[index];localRecordings.value=next;return}
 coachEditing.value=false;vision.reset()
}
function reanswerCoach(){
 if(coachBusy.value)return
 clearCoachQuestion();answer.value=coach.snapshot.value?.current_attempt?.answer || '';coachEditing.value=true
 const index=currentQuestionIndex.value;const next={...localRecordings.value};delete next[index];localRecordings.value=next
 void nextTick(()=>document.getElementById('coach-answer')?.focus())
}
async function discardRuntimeDraft(){
 try{await ElMessageBox.confirm('请先复制需要保留的文字。清空后可重新回答当前任务。','清空旧草稿',{confirmButtonText:'清空旧草稿',cancelButtonText:'继续保留'})}catch{return}
 interviewAudio.invalidate();interviewVideo.invalidate();vision.reset();audioDraftEpoch.value++;answer.value='';coach.setDraft('');coachEditing.value=true
}
async function advanceCoach(){
 if(answer.value.trim()){try{await ElMessageBox.confirm('重答草稿还未提交。继续下一题会放弃这段草稿，已保存回答保留。','保留或放弃草稿',{confirmButtonText:'放弃草稿并继续',cancelButtonText:'继续修改'})}catch{return}}
 const result=await coach.advance();if(!result)return
 answer.value='';clearCoachQuestion();coachEditing.value=false
 await nextTick();document.getElementById('coach-question')?.focus()
}
async function focusCoach(index:number|null){
 if(coachBusy.value || recording.value || videoRecording.value || videoStopping.value || interviewVideo.busy.value)return
 if(answer.value.trim()){try{await ElMessageBox.confirm('切换会放弃未提交草稿，已保存版本保留。','切换题目',{confirmButtonText:'放弃草稿并切换',cancelButtonText:'继续修改'})}catch{return}}
 const result=await coach.focus(index);if(!result)return
 answer.value='';clearCoachQuestion();coachEditing.value=false
 await nextTick();document.getElementById('coach-question')?.focus()
}
function reviewUpdated(updated:InterviewSession){session.value=updated;if(coachEnabled)void coach.refresh()}
watch(coach.snapshot,value=>{if(value)session.value=value.session})
watch(coach.draft,value=>{if(coachEnabled && answer.value!==value)answer.value=value;if(value.trim() && session.value?.runtime)coachEditing.value=true})
const sourceEvidenceLabel = computed(() => {
  const evidence = session.value?.source_context?.source_evidence
  if (!evidence) return ''
  if (evidence.status === 'unavailable') return evidence.reason
  const location = [
    evidence.page_number != null ? `第 ${evidence.page_number} 页` : '',
    evidence.chunk_index != null ? `片段 ${evidence.chunk_index + 1}` : ''
  ].filter(Boolean).join(' · ') || '已匹配资料片段'
  return `定位：${location}；本地词法匹配，需核对原资料。`
})
const answer = ref('')
const loading = ref(false)
const error = ref('')
const speaking = computed(() => coachEnabled ? coachSpeech.speaking.value : legacySpeaking.value)
const legacySpeaking = ref(false)
const recording = ref(false)
const recordingDuration = ref(0)
const fillerCount = ref(0)
const longPauseCount = ref(0)
const fluencyMetrics = ref<InterviewFluencyMetrics | undefined>()
const cameraVideo = ref<HTMLVideoElement | null>(null)
const cameraActive = ref(false)
const cameraError = ref('')
const reviewEnabled = ref(import.meta.env.VITE_ENABLE_INTERVIEW_REVIEW !== 'false')
const legacyExternalConsent = ref(false)
const vision = useInterviewVision()
let submitKey = ''
let submitFingerprint = ''
let cameraRequestEpoch = 0
let speechOffset: number | undefined
let videoPerformanceStart = 0
let recordingByteCount = 0
let recognition: any = null
let recognitionGeneration = 0
let recordingStartedAt = 0
let lastSpeechAt = 0
let recordingTimer: number | undefined
let cameraStream: MediaStream | null = null
let localRecordingStream: MediaStream | null = null
let mediaRecorder: MediaRecorder | null = null
let localVideoChunks: Blob[] = []
let videoRecordingStartedAt = 0
let videoRecordingTimer: number | undefined
let recordingQuestionIndex = -1
let discardPendingRecording = false

interface LocalRecording {
  ownerId?: string
  url: string
  duration: number
  mimeType: string
  hasAudio: boolean
}

const recordingSupported = typeof MediaRecorder !== 'undefined'
const videoRecording = ref(false)
const videoStopping = ref(false)
const videoStarting = ref(false)
const videoRecordingDuration = ref(0)
const recordingHasAudio = ref(false)
const fluencyMarkers = ref<InterviewFluencyMarker[]>([])
const localRecordings = ref<Record<number, LocalRecording>>({})

const liveCharsPerMinute = computed(() => {
  if (!recordingDuration.value) return 0
  return Math.round(answer.value.replace(/\s+/g, '').length * 60 / recordingDuration.value)
})
const liveWordsPerMinute = computed(() => recordingDuration.value
  ? Math.round((answer.value.match(/[A-Za-z]+(?:['’-][A-Za-z]+)*/g)?.length || 0) * 60 / recordingDuration.value) : 0)

const markerPosition = (second: number, duration: number) => {
  if (!duration) return '0%'
  return `${Math.max(0, Math.min(100, second / duration * 100))}%`
}

const displayScore = (value: number | null | undefined) => value == null ? '待评估' : `${value.toFixed(0)} 分`

const scoreLabel = computed(() => {
  const score = session.value?.overall_score
  if (score == null) return '回答已保存，先回看一题，再继续练习'
  return score >= 85 ? '表现出色，可以进入实战' : score >= 70 ? '基础扎实，继续优化表达' : '已发现提升空间，建议再练一轮'
})

const completionCompanion = computed((): {
  mood: CompanionMood
  title: string
  message: string
  evidence: string
} => {
  const score = session.value?.overall_score
  if (score == null) return {
    mood: 'happy',
    title: '又完成了一次练习',
    message: '内容质量尚未评估，可以对照资料回看自己的回答。',
    evidence: `依据：已记录 ${session.value?.turns.length || 0} 次回答`
  }
  if (score >= 85) return {
    mood: 'wink',
    title: '这轮表达已经具备实战说服力',
    message: '保持内容证据，再尝试压力面或更短的限时回答。',
    evidence: `依据：本轮面试均分 ${Math.round(score)} 分`
  }
  if (score >= 60) return {
    mood: 'focused',
    title: '基础已经站稳，下一轮重点打磨表达',
    message: '从回答记录中选择最低分问题，补上具体行动和量化结果。',
    evidence: `依据：本轮面试均分 ${Math.round(score)} 分`
  }
  return {
    mood: 'encouraging',
    title: '我已经帮你找到最值得重练的位置',
    message: '先复盘一题即可，不需要一次把所有问题都改完。',
    evidence: `依据：本轮面试均分 ${Math.round(score)} 分`
  }
})

const speakQuestion = () => {
  if(coachEnabled){if(interviewAudio.busy.value || interviewVideo.busy.value)return;interviewVideo.pausePlayback();interviewAudio.pausePlayback();coachSpeech.read(coach.view.value?.question || '',voiceId.value);return}
  const text = session.value?.current_question
  if (!text || !('speechSynthesis' in window)) return
  window.speechSynthesis.cancel()
  const utterance = new SpeechSynthesisUtterance(text)
  utterance.lang = session.value?.scenario === '英语面' ? 'en-US' : 'zh-CN'; utterance.rate = .95
  utterance.onstart = () => { legacySpeaking.value = true }
  utterance.onend = () => { legacySpeaking.value = false }
  utterance.onerror = () => { legacySpeaking.value = false }
  window.speechSynthesis.speak(utterance)
}

const begin = async () => {
  if (loading.value || memoryBusy.value || needsConfigurationChoice.value || configurationState.value.busy || !configurationState.value.ready) return
  loading.value = true
  error.value = ''
  memoryError.value = ''
  try {
    if(configuration.value.execution_mode==='timed'){
      if(!runtimeEnabled.value)throw Error('实战写入未开启，请选择逐题训练')
      const content={configuration:configuration.value,target_role:form.value.targetRole,source_id:'',project_name:projectName.value,project_details:projectDetails.value}
      const fingerprint=JSON.stringify(content)
      if(preparationFingerprint!==fingerprint){preparationFingerprint=fingerprint;preparationKey=crypto.randomUUID()}
      const prepared=await prepareInterviewRuntime(content,preparationKey)
      if(disposed)return
      preparationKey='';preparationFingerprint=''
      session.value=prepared.session
      await syncSessionQuery(prepared.session.interview_id)
      await coach.open(prepared.session.interview_id)
      return
    }
    const created = await startInterview(form.value.targetRole, form.value.scenario, form.value.difficulty, form.value.sourceId || undefined, focusWrongId.value || undefined, originGoalId.value || undefined, reviewEnabled.value ? false : legacyExternalConsent.value, {
      projectName: form.value.scenario === '项目面' ? projectName.value : '',
      projectDetails: form.value.scenario === '项目面' ? projectDetails.value : '',
      rememberForFuture: rememberForFuture.value,
      memoryId: selectedMemoryId.value
    }, configurationState.value.enabled ? configuration.value : undefined)
    if (disposed) return
    session.value = created
    resumeError.value = ''
    await syncSessionQuery(created.interview_id)
    if(coachEnabled)await coach.open(created.interview_id)
    else speakQuestion()
  }
  catch (e: any) { error.value = e?.message || '创建失败'; ElMessage.error(error.value) }
  finally { loading.value = false }
}

const submit = async () => {
  if (!session.value) return
  const captured = session.value
  const visual = reviewEnabled.value ? vision.finish() : undefined
  const fingerprint = JSON.stringify([captured.interview_id, captured.current_index, answer.value, fluencyMetrics.value, visual])
  if (fingerprint !== submitFingerprint) { submitFingerprint = fingerprint; submitKey = crypto.randomUUID() }
  loading.value = true
  try {
    const updated = await answerInterview(
      captured.interview_id,
      answer.value,
      fluencyMetrics.value,
      { questionIndex: captured.current_index, requestKey: submitKey, visualMetrics: visual }
    )
    if (disposed || session.value?.interview_id !== captured.interview_id) return
    session.value = updated
    submitKey = ''; submitFingerprint = ''
    vision.reset()
    const latestScore = session.value.latest_evaluation?.score
    publishCompanionEvent({
      mood: latestScore == null ? 'happy' : latestScore >= 85 ? 'wink' : latestScore >= 60 ? 'focused' : 'encouraging',
      title: latestScore == null ? '这一题的回答已保存' : latestScore >= 85 ? '这一题回答得很有力量' : latestScore >= 60 ? '思路已经清楚，再补一层证据' : '这一题值得慢下来重新组织',
      message: session.value.latest_evaluation?.feedback || '继续完成下一题，我会保留每轮证据。',
      evidence: latestScore == null ? '练习记录 · 内容质量待评估' : `依据：本题模型评分 ${Math.round(latestScore)} 分`,
      route: session.value.status === 'completed' ? '/growth' : '/interview',
      actionLabel: session.value.status === 'completed' ? '查看成长证据' : '继续面试'
    })
    answer.value = ''
    fluencyMetrics.value = undefined
    fluencyMarkers.value = []
    recordingDuration.value = 0
    fillerCount.value = 0
    longPauseCount.value = 0
    if (session.value.status === 'active') setTimeout(speakQuestion, 180)
  }
  catch (error: any) { ElMessage.error(error.message || '回答保存失败，文字与本地录像仍保留') }
  finally { loading.value = false }
}

const loadRecent = async () => {
  historyLoading.value = true
  historyError.value = ''
  try { recentInterviews.value = (await getLearningAnalytics()).recent_interviews }
  catch { historyError.value = '练习记录暂时未能加载，可以重试；仍可新建面试。' }
  finally { historyLoading.value = false }
}

const loadMemories = async () => {
  if (memoryBusy.value || disposed) return
  memoryBusy.value = true
  memoryError.value = ''
  try {
    const items = await getInterviewPracticeMemories()
    if (disposed) return
    practiceMemories.value = items
    if (selectedMemoryId.value && !items.some(item => item.memory_id === selectedMemoryId.value)) selectedMemoryId.value = null
  } catch (e: any) {
    if (!disposed) memoryError.value = e?.message || '练习记忆暂时无法读取，可以不复用历史继续训练。'
  } finally { memoryBusy.value = false }
}

const forgetPractice = async (memoryId: string) => {
  if (memoryBusy.value || loading.value) return
  memoryBusy.value = true
  memoryError.value = ''
  let confirmed = false
  try {
    const preview = await previewInterviewMemoryForget(memoryId)
    if (disposed) return
    try {
      await ElMessageBox.confirm(`“${preview.target_role}”：${preview.scope}`, '遗忘练习记忆', { confirmButtonText: '确认停止复用', cancelButtonText: '保留复用' })
    } catch { return }
    if (disposed) return
    await forgetInterviewMemory(memoryId, preview.confirmation_token)
    if (disposed) return
    confirmed = true
    if (selectedMemoryId.value === memoryId) selectedMemoryId.value = null
    const context = session.value?.practice_context
    if (context?.memory_id === memoryId) { context.remember_for_future = false; context.memory_id = null }
    if (context?.memory_ref?.memory_id === memoryId) context.memory_available = false
    ElMessage.success('已停止复用，原回答与报告保留')
  } catch (e: any) {
    if (!disposed) { memoryError.value = e?.message || '遗忘未完成，请重试'; ElMessage.error(memoryError.value) }
  } finally {
    memoryBusy.value = false
    if (confirmed && !disposed) void loadMemories()
  }
}

const forgetCurrentPractice = () => {
  const memoryId = session.value?.practice_context?.memory_id
  if (memoryId) void forgetPractice(memoryId)
}

const restoreInterview = async (interviewId: string, fromRoute = false) => {
  if (!interviewId || loading.value) return
  if (!fromRoute && !(await confirmLeave())) return
  stopSpeechRecording(); stopVideoRecording(true); stopCamera(); clearLocalRecordings(); interviewAudio.clear(); interviewVideo.clear()
  window.speechSynthesis?.cancel()
  session.value = null
  answer.value = ''
  requestedInterviewId.value = interviewId
  loading.value = true
  resumeError.value = ''
  try {
    const restored = await getInterview(interviewId)
    if (disposed) return
    session.value = restored
    form.value = { targetRole: restored.target_role, scenario: restored.scenario, difficulty: restored.difficulty, sourceId: restored.source_context?.source_id || '' }
    const restoredConfiguration = configurationForSession(restored)
    needsConfigurationChoice.value = !restoredConfiguration
    configuration.value = restoredConfiguration || configurationForScenario('知识讲解', '标准')!
    projectName.value = restored.practice_context?.project?.name || ''
    projectDetails.value = restored.practice_context?.project?.details || ''
    rememberForFuture.value = false
    selectedMemoryId.value = null
    focusWrongId.value = restored.source_context?.focus_wrong_id || ''
    originGoalId.value = restored.source_context?.goal_id || ''
    answer.value = ''
    if(coachEnabled)await coach.open(restored.interview_id)
    await syncSessionQuery(restored.interview_id)
  } catch { resumeError.value = '这场面试暂时无法恢复。请确认后端已启动，或从下方新建面试。' }
  finally { loading.value = false }
}

const finalizeFluency = () => {
  if (!recordingStartedAt) return
  recordingDuration.value = Math.max(1, Math.round((Date.now() - recordingStartedAt) / 1000))
  fluencyMetrics.value = {
    duration_seconds: recordingDuration.value,
    chars_per_minute: liveCharsPerMinute.value,
    filler_count: fillerCount.value,
    long_pause_count: longPauseCount.value,
    source: 'speech_recognition',
    markers: fluencyMarkers.value,
    ...(speechOffset !== undefined ? { recording_offset_seconds: speechOffset } : {})
  }
  recordingStartedAt = 0
  if (recordingTimer !== undefined) window.clearInterval(recordingTimer)
  recordingTimer = undefined
}

const toggleRecording = () => {
  if(interviewVideo.busy.value)return
  coachSpeech.stop();interviewVideo.pausePlayback();interviewAudio.pausePlayback()
  if (recording.value) { recognition?.stop(); return }
  if (recognition) return
  const Recognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
  if (!Recognition) { ElMessage.info('当前浏览器不支持语音识别，请使用文字回答'); return }
  recognition = new Recognition(); recognition.lang = session.value?.scenario === '英语面' ? 'en-US' : 'zh-CN'; recognition.continuous = true; recognition.interimResults = true
  const generation = ++recognitionGeneration
  const isCurrent = () => !disposed && generation === recognitionGeneration
  recognition.onstart = () => {
    if (!isCurrent()) return
    recording.value = true
    recordingStartedAt = Date.now()
    speechOffset = videoRecording.value ? Math.max(0, (performance.now() - videoPerformanceStart) / 1000) : undefined
    lastSpeechAt = 0
    recordingDuration.value = 0
    fillerCount.value = 0
    longPauseCount.value = 0
    fluencyMarkers.value = []
    fluencyMetrics.value = undefined
    recordingTimer = window.setInterval(() => {
      recordingDuration.value = Math.max(1, Math.round((Date.now() - recordingStartedAt) / 1000))
    }, 500)
  }
  recognition.onend = () => { if (!isCurrent()) return; recording.value = false; recognition = null; finalizeFluency() }
  recognition.onerror = () => { if (!isCurrent()) return; recording.value = false; recognition = null; finalizeFluency(); ElMessage.warning('语音识别中断，请重试') }
  recognition.onresult = (event: any) => {
    if (!isCurrent() || !recordingStartedAt) return
    const now = Date.now()
    const elapsed = Math.max(0, (now - recordingStartedAt) / 1000)
    if (lastSpeechAt && now - lastSpeechAt > 2500) {
      longPauseCount.value += 1
      if (fluencyMarkers.value.length < 100) fluencyMarkers.value.push({ second: elapsed, kind: 'long_pause', label: '较长停顿' })
    }
    lastSpeechAt = now
    const english = session.value?.scenario === '英语面'
    answer.value = Array.from(event.results).map((result: any) => result[0].transcript).join(english ? ' ' : '')
    const detectedFillers = answer.value.match(english ? /\b(?:um|uh|erm|you know)\b/gi : /嗯|呃|那个|就是说|然后呢|就是/g)?.length || 0
    if (detectedFillers > fillerCount.value) {
      for (let index = fillerCount.value; index < detectedFillers; index += 1) {
        if (fluencyMarkers.value.length < 100) fluencyMarkers.value.push({ second: elapsed, kind: 'filler', label: '出现口头语' })
      }
    }
    fillerCount.value = Math.min(100, detectedFillers)
  }
  try { recognition.start() }
  catch { recognitionGeneration++; recognition = null; ElMessage.warning('语音识别未能启动，请重试或使用文字回答') }
}

const stopSpeechRecording = () => {
  recognitionGeneration++
  const previous = recognition
  recognition = null
  previous?.stop()
  recording.value = false
  finalizeFluency()
}

const startCamera = async () => {
  cameraError.value = ''
  if (!navigator.mediaDevices?.getUserMedia) {
    cameraError.value = '当前环境不支持摄像头预览'
    return
  }
  const current = ++cameraRequestEpoch
  try {
    const acquired = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: 'user', width: { ideal: 640 }, height: { ideal: 480 } },
      audio: false
    })
    if (disposed || current !== cameraRequestEpoch || !session.value) { acquired.getTracks().forEach(track => track.stop()); return }
    cameraStream = acquired
    cameraActive.value = true
    await nextTick()
    if (cameraVideo.value) {
      cameraVideo.value.srcObject = cameraStream
      cameraVideo.value.muted = true
      try { await cameraVideo.value.play() }
      catch { if (!disposed && current === cameraRequestEpoch) cameraError.value = '浏览器未能播放摄像头预览，请关闭后重新开启；文字训练仍可使用。' }
    }
  } catch {
    if (disposed || current !== cameraRequestEpoch) return
    cameraError.value = '当前无法访问摄像头，将跳过视频分析；可继续文字或语音回答。'
    cameraActive.value = false
  }
}

const stopCamera = () => {
  cameraRequestEpoch++
  vision.finish()
  vision.stop()
  if (videoRecording.value && !videoStopping.value) stopVideoRecording()
  cameraStream?.getTracks().forEach(track => track.stop())
  cameraStream = null
  cameraActive.value = false
  if (cameraVideo.value) cameraVideo.value.srcObject = null
}

const toggleCamera = () => { cameraActive.value ? stopCamera() : startCamera() }
const toggleVision = async () => {
  if (['ready', 'observing'].includes(vision.state.value)) { vision.finish(); vision.stop(); return }
  if (await vision.enable()) {
    await nextTick()
    if ((videoEnabled ? interviewVideo.camera.value.phase==='ready' : cameraActive.value) && cameraVideo.value) vision.observe(cameraVideo.value)
  }
}

const stopLocalRecordingTracks = () => {
  localRecordingStream?.getTracks().forEach(track => track.stop())
  localRecordingStream = null
  if (videoRecordingTimer !== undefined) window.clearInterval(videoRecordingTimer)
  videoRecordingTimer = undefined
}

const startVideoRecording = async () => {
  coachSpeech.stop()
  if (!cameraStream || !session.value || !recordingSupported || videoStarting.value || videoStopping.value) return
  videoStarting.value = true
  const capturedId = session.value.interview_id
  const capturedIndex = currentQuestionIndex.value
  const capturedEpoch = mediaEpoch
  const capturedMediaId = draftMediaId
  const capturedCamera = cameraStream
  cameraError.value = ''
  if (localRecordings.value[capturedIndex]) {
    try {
      await ElMessageBox.confirm('本题已有一段当前页面录像。新录像完成后将替换它；可先下载保留原录像。确认重新录制？', '替换本题本地录像', { confirmButtonText: '确认重新录制', cancelButtonText: '保留原录像' })
    } catch { videoStarting.value = false; return }
    if (disposed || capturedCamera !== cameraStream || session.value?.interview_id !== capturedId || currentQuestionIndex.value !== capturedIndex || mediaEpoch !== capturedEpoch) { videoStarting.value = false; return }
  }
  let microphoneStream: MediaStream | null = null
  try {
    microphoneStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false })
  } catch {
    ElMessage.warning('未获得麦克风权限，将只录制本地画面')
  }
  if (disposed || !cameraActive.value || capturedCamera !== cameraStream || session.value?.interview_id !== capturedId || currentQuestionIndex.value !== capturedIndex || mediaEpoch !== capturedEpoch) {
    microphoneStream?.getTracks().forEach(track => track.stop()); videoStarting.value = false; return
  }
  const videoTracks = cameraStream.getVideoTracks().map(track => track.clone())
  const audioTracks = microphoneStream?.getAudioTracks() || []
  localRecordingStream = new MediaStream([...videoTracks, ...audioTracks])
  recordingHasAudio.value = audioTracks.length > 0
  localVideoChunks = []
  recordingByteCount = 0
  recordingQuestionIndex = currentQuestionIndex.value
  discardPendingRecording = false
  const mimeType = ['video/webm;codecs=vp9,opus', 'video/webm;codecs=vp8,opus', 'video/webm']
    .find(type => MediaRecorder.isTypeSupported(type))
  try {
    mediaRecorder = mimeType
      ? new MediaRecorder(localRecordingStream, { mimeType })
      : new MediaRecorder(localRecordingStream)
  } catch { stopLocalRecordingTracks(); videoStarting.value = false; cameraError.value = '当前浏览器无法创建本地录像，可继续文字或语音回答。'; return }
  mediaRecorder.ondataavailable = event => {
    if (event.data.size > 0) { localVideoChunks.push(event.data); recordingByteCount += event.data.size }
    if (recordingByteCount > 100 * 1024 * 1024 && mediaRecorder?.state === 'recording') { stopVideoRecording(); ElMessage.info('本段录像达到100MB上限，已自动停止。') }
  }
  mediaRecorder.onerror = () => {
    videoRecording.value = false
    videoStopping.value = false
    videoStarting.value = false
    vision.finish()
    stopLocalRecordingTracks()
    ElMessage.error('本地录像中断，请重新开启')
  }
  mediaRecorder.onstop = () => {
    const duration = Math.max(1, Math.round((Date.now() - videoRecordingStartedAt) / 1000))
    if (!disposed && !discardPendingRecording && session.value?.interview_id === capturedId && currentQuestionIndex.value === capturedIndex && mediaEpoch === capturedEpoch && localVideoChunks.length && recordingQuestionIndex >= 0) {
      const previous = localRecordings.value[recordingQuestionIndex]
      if (previous) URL.revokeObjectURL(previous.url)
      const blob = new Blob(localVideoChunks, { type: mediaRecorder?.mimeType || 'video/webm' })
      localRecordings.value = {
        ...localRecordings.value,
        [recordingQuestionIndex]: {
          ownerId: coachEnabled ? capturedMediaId : undefined,
          url: URL.createObjectURL(blob),
          duration,
          mimeType: blob.type,
          hasAudio: recordingHasAudio.value
        }
      }
      ElMessage.success('本轮录像已保存在当前页面，可在回答记录中回放')
    }
    videoRecording.value = false
    videoStopping.value = false
    videoStarting.value = false
    stopLocalRecordingTracks()
    mediaRecorder = null
    localVideoChunks = []
  }
  videoRecordingStartedAt = Date.now()
  videoPerformanceStart = performance.now()
  if (recording.value) speechOffset = undefined
  videoRecordingDuration.value = 0
  videoRecording.value = true
  try { mediaRecorder.start(500) }
  catch { stopLocalRecordingTracks(); videoRecording.value = false; videoStarting.value = false; cameraError.value = '本地录像未能启动，可重试。'; return }
  videoStarting.value = false
  if (reviewEnabled.value && cameraVideo.value) vision.observe(cameraVideo.value, videoPerformanceStart)
  videoRecordingTimer = window.setInterval(() => {
    videoRecordingDuration.value = Math.max(1, Math.round((Date.now() - videoRecordingStartedAt) / 1000))
    if (videoRecordingDuration.value >= 1800) { stopVideoRecording(); ElMessage.info('本段录像达到30分钟上限，已自动停止。') }
  }, 500)
}

const stopVideoRecording = (discard = false) => {
  vision.finish()
  discardPendingRecording = discard
  if (mediaRecorder && mediaRecorder.state !== 'inactive') { videoStopping.value = true; mediaRecorder.stop() }
  else {
    videoRecording.value = false
    stopLocalRecordingTracks()
  }
}

const toggleVideoRecording = () => {
  if (videoRecording.value) stopVideoRecording()
  else void startVideoRecording()
}

const seekRecording = (index: number, second: number) => {
  const video = document.getElementById(`interview-replay-${index}`) as HTMLVideoElement | null
  if (!video) return
  video.currentTime = Math.max(0, Math.min(second, Number.isFinite(video.duration) ? video.duration : second))
  void video.play().catch(() => { ElMessage.info('请点击录像播放按钮回看。') })
}

const downloadRecording = async (index: number) => {
  const item = localRecordings.value[index]
  if (!item) return
  try { const blob = await fetch(item.url).then(response => response.blob()); await saveDownload(blob, `filemate-interview-${session.value?.interview_id}-q${index + 1}.webm`) } catch { ElMessage.error('录像暂时无法下载，请保留当前页面后重试。') }
}
const removeRecording = async (index: number) => {
  try { await ElMessageBox.confirm('删除这段当前页面的本地录像，保留回答和已提交观察摘要。确认继续？', '删除本地录像', { confirmButtonText: '确认删除录像', cancelButtonText: '保留录像' }) }
  catch { return }
  const item = localRecordings.value[index]
  if (item) URL.revokeObjectURL(item.url)
  const remaining = { ...localRecordings.value }; delete remaining[index]; localRecordings.value = remaining
}

const clearLocalRecordings = () => {
  mediaEpoch++;coachSpeech.stop()
  new Set([...Object.values(localRecordings.value),...Object.values(coachRecordings.value)].map(r=>r.url)).forEach(url=>URL.revokeObjectURL(url))
  coachRecordings.value={}
  localRecordings.value = {}
}

const reset = async () => {
  if (!(await confirmLeave())) return
  await resetInterviewState()
}
const deletedInterview = async () => { await resetInterviewState() }
const resetInterviewState = async () => {
  window.speechSynthesis?.cancel()
  stopSpeechRecording()
  stopVideoRecording(true)
  stopCamera()
  vision.reset()
  clearLocalRecordings()
  interviewAudio.clear(); interviewVideo.clear()
  coach.dispose()
  session.value = null
  focusWrongId.value = ''
  originGoalId.value = ''
  answer.value = ''
  fluencyMetrics.value = undefined
  recordingDuration.value = 0
  fillerCount.value = 0
  longPauseCount.value = 0
  speechOffset = undefined
  fluencyMarkers.value = []
  resumeError.value = ''
  initialPreparation.value = preparationSnapshot()
  void syncSessionQuery()
  void loadRecent()
  void loadMemories()
}

async function syncSessionQuery(id?: string): Promise<void> {
  const target = router.resolve({ path: '/interview', query: id ? { interview: id } : {} }).fullPath
  syncingSessionTarget = target
  try { await router.replace(target) }
  finally { if (syncingSessionTarget === target) syncingSessionTarget = null }
}


function preparationSnapshot(): string {
  return JSON.stringify([form.value, configuration.value, projectName.value, projectDetails.value, rememberForFuture.value, selectedMemoryId.value])
}
function applyPreparationRoute(): void {
  needsConfigurationChoice.value = false
  form.value = { targetRole: typeof route.query.target === 'string' ? route.query.target.slice(0, 120) : '', scenario: interviewModes.includes(String(route.query.scenario)) ? String(route.query.scenario) : '知识讲解', difficulty: '标准', sourceId: typeof route.query.source === 'string' ? route.query.source : '' }
  configuration.value = configurationForScenario(form.value.scenario, form.value.difficulty)!
  projectName.value = ''; projectDetails.value = ''; rememberForFuture.value = false; selectedMemoryId.value = null
}
applyPreparationRoute()
const initialPreparation = ref(preparationSnapshot())

const draftPresent = computed(() => hasInterviewDraft({
  answer: answer.value, recording: recording.value || interviewAudio.busy.value || interviewVideo.busy.value, videoStarting: videoStarting.value,
  videoRecording: videoRecording.value, videoStopping: videoStopping.value,
  localRecordings: Object.keys(localRecordings.value).length + interviewAudio.items.value.length + interviewVideo.items.value.length,
  preparation: !session.value && preparationSnapshot() !== initialPreparation.value
}))

async function confirmLeave(): Promise<boolean> {
  if (loading.value || memoryBusy.value || coachBusy.value || configurationState.value.busy) { ElMessage.info('正在保存或读取面试，请稍候再切换。'); return false }
  if (!draftPresent.value) return true
  try {
    await ElMessageBox.confirm(session.value?.runtime ? '未保存配置和本地录音和录像不会保留。实战文字草稿仅临时保存在当前标签页，建议先复制；已保存回答保留。确定离开吗？' : '未保存配置、未提交的文字和本地录音和录像不会保留。已保存配置与回答仍会保留，确定离开吗？', '离开当前练习', { confirmButtonText: '离开', cancelButtonText: '继续练习', type: 'warning' })
    return true
  } catch { return false }
}

function protectBrowserExit(event: BeforeUnloadEvent): void {
  if (loading.value || memoryBusy.value || configurationState.value.busy || draftPresent.value) { event.preventDefault(); event.returnValue = '' }
}

watch(answer,text=>{if(coachEnabled){coachSpeech.stop();coach.setDraft(text,coach.composing.value)}})
onBeforeRouteLeave(async()=>{coachSpeech.stop();return confirmLeave()})
onBeforeRouteUpdate(to => to.fullPath === syncingSessionTarget ? true : confirmLeave())
watch(() => route.fullPath, fullPath => {
  if (fullPath === syncingSessionTarget) return
  const id = typeof route.query.interview === 'string' ? route.query.interview : ''
  if (id === session.value?.interview_id) return
  stopSpeechRecording(); stopVideoRecording(true); stopCamera(); clearLocalRecordings(); interviewAudio.clear(); interviewVideo.clear()
  window.speechSynthesis?.cancel()
  answer.value = ''
  if (id) { void restoreInterview(id, true); return }
  session.value = null
  applyPreparationRoute()
  initialPreparation.value = preparationSnapshot()
  focusWrongId.value = typeof route.query.focus === 'string' ? route.query.focus : ''
  originGoalId.value = typeof route.query.goal === 'string' ? route.query.goal : ''
})

onBeforeUnmount(() => {
  draftController.dispose()
  disposeMediaEnvironment?.()
  window.removeEventListener('beforeunload', protectBrowserExit)
  disposed = true
  interviewAudio.dispose(); interviewVideo.dispose()
  coach.dispose();coachSpeech.stop()
  stopSpeechRecording()
  stopVideoRecording(true)
  stopCamera()
  clearLocalRecordings()
  if (recordingTimer !== undefined) window.clearInterval(recordingTimer)
  window.speechSynthesis?.cancel()
})
onMounted(async () => {
  if(videoEnabled)disposeMediaEnvironment=watchMediaEnvironment(document,navigator.mediaDevices,{hidden:()=>{interviewVideo.interrupted();vision.finish();vision.stop()},devicesChanged:()=>{void interviewVideo.refresh()}})
  window.addEventListener('beforeunload', protectBrowserExit)
  void draftController.load()
  if (reviewEnabled.value) { try { reviewEnabled.value = (await getInterviewReviewStatus()).enabled } catch { reviewEnabled.value = false } }
  void loadRecent()
  void loadMemories()
  if (typeof route.query.interview === 'string') void restoreInterview(route.query.interview, true)
  try { knowledgeSources.value = await getKnowledgeSources(100) }
  catch { knowledgeSources.value = [] }
  if (!form.value.sourceId) focusWrongId.value = ''
  if (!focusWrongId.value) originGoalId.value = ''
})
</script>

<style scoped>
.interview-page{max-width:1320px;margin:0 auto;padding:0;color:var(--text-primary)}.page-head{display:flex;justify-content:space-between;gap:24px;align-items:end;margin-bottom:26px}.eyebrow{margin:0;color:var(--accent);font-size: var(--type-meta);font-weight:800;letter-spacing:.15em}.page-head h1{font-size:32px;margin:0 0 7px}.page-head p{margin:0;color:var(--text-secondary)}.status-pill{display:flex;align-items:center;gap:8px;padding:8px 12px;border:1px solid var(--accent-border);border-radius:999px;color:var(--accent);background:var(--accent-soft)}.status-pill i,.online i{width:7px;height:7px;border-radius:50%;background:#36a269}.setup-card,.studio,.evaluation,.review-list{background:var(--bg-surface);border:1px solid var(--border-subtle);border-radius:18px}.setup-card{padding:30px}.setup-copy span{color:var(--accent);font-size: var(--type-meta);font-weight:700}.setup-copy h2{font-size:24px;margin:8px 0}.setup-copy p{color:var(--text-secondary)}.form-grid{display:grid;grid-template-columns:2fr 1fr 1fr;gap:14px;margin:26px 0}.form-grid label{font-size: var(--type-meta);color:var(--text-secondary)}input,select,textarea{box-sizing:border-box;width:100%;margin-top:7px;padding:12px;border:1px solid var(--border-default);border-radius:10px;background:var(--bg-elevated);color:var(--text-primary);font:inherit}textarea{resize:vertical;line-height:1.7}.primary,.ghost,.voice{border:0;border-radius:10px;padding:11px 17px;cursor:pointer}.primary{background:var(--action-fill, var(--accent));color:white;font-weight:700}.primary:disabled{opacity:.45}.studio{display:grid;grid-template-columns:310px 1fr;overflow:hidden}.interviewer-panel{padding:30px;background:var(--sidebar-bg);text-align:center;border-right:1px solid var(--border-subtle)}.avatar-stage{position:relative;width:180px;height:180px;margin:12px auto 24px;display:grid;place-items:center}.avatar-face{position:relative;z-index:2;width:124px;height:124px;display:grid;place-items:center;overflow:hidden;border:4px solid rgba(255,255,255,.9);border-radius:50%;background:linear-gradient(145deg,var(--brand-blue-soft),#e7f6ee);box-shadow:0 16px 35px rgba(37,99,235,.18)}.avatar-face img{width:100%;height:100%;object-fit:cover;object-position:50% 22%;transform:scale(1.08)}.pulse{position:absolute;border:1px solid var(--brand-blue-border);border-radius:50%}.pulse-one{inset:12px}.pulse-two{inset:0}.speaking .pulse{animation:pulse 1.3s infinite}.voice-bars{position:absolute;bottom:1px;display:flex;gap:3px}.voice-bars i{width:3px;height:8px;background:var(--action-fill, var(--accent));border-radius:3px}.speaking .voice-bars i{animation:bars .7s infinite alternate}.voice-bars i:nth-child(2n){animation-delay:.2s}.role{font-weight:700}.online{font-size: var(--type-meta);color:var(--text-secondary)}.online i{display:inline-block;margin-right:5px}.ghost{margin-top:18px;border:1px solid var(--accent-border);background:transparent;color:var(--accent)}.conversation-panel{padding:30px}.progress-row{display:flex;justify-content:space-between;color:var(--text-secondary);font-size: var(--type-meta)}.progress{height:5px;background:var(--bg-elevated);border-radius:5px;margin:10px 0 28px}.progress i{display:block;height:100%;background:var(--action-fill, var(--accent));border-radius:5px}.question-block>p{font-size: var(--type-meta);color:var(--accent)}.question-block h2{font-size:22px;line-height:1.5}.answer-actions{display:flex;gap:12px;align-items:center;margin-top:12px}.answer-actions span{color:var(--text-muted);font-size: var(--type-action);margin-right:auto}.voice{border:1px solid var(--accent-border);color:var(--accent);background:var(--accent-soft)}.voice.recording{background:#fff0ec;color:#b44b34}.evaluation,.review-list{margin-top:18px;padding:24px}.evaluation-head{display:flex;justify-content:space-between;gap:20px}.evaluation-head h2{font-size:17px}.evaluation-head>strong{font-size:42px;color:var(--accent)}.dimension-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:16px}.dimension-grid>div{display:grid;grid-template-columns:1fr auto;gap:8px}.dimension-grid i{grid-column:1/-1;height:5px;background:var(--bg-elevated);border-radius:5px}.dimension-grid em{display:block;height:100%;background:var(--action-fill, var(--accent));border-radius:5px}.review-list h2{font-size:18px}.review-list details{border-top:1px solid var(--border-subtle);padding:14px 0}.review-list summary{display:flex;justify-content:space-between;gap:18px;cursor:pointer}.review-list p,.review-list small{color:var(--text-secondary);line-height:1.7}.completion{display:flex;align-items:center;justify-content:center;gap:24px;padding:60px 20px}.score-ring{width:110px;height:110px;display:grid;place-items:center;border:8px solid var(--accent-soft);outline:2px solid var(--accent);border-radius:50%;font-size:34px;font-weight:800;color:var(--accent)}@keyframes pulse{50%{transform:scale(1.05);opacity:.45}}@keyframes bars{to{height:25px}}@media(max-width:800px){.studio{grid-template-columns:1fr}.interviewer-panel{border-right:0;border-bottom:1px solid var(--border-subtle)}.form-grid,.dimension-grid{grid-template-columns:1fr 1fr}.page-head{align-items:start;flex-direction:column}}@media(max-width:520px){.form-grid,.dimension-grid{grid-template-columns:1fr}.interview-page{padding:16px}.conversation-panel{padding:20px}.answer-actions{flex-wrap:wrap}.answer-actions .primary{width:100%}}

.live-face{border-top:1px solid var(--border-subtle);padding-top:12px}.live-face h3{font-size:18px;margin:0 0 10px}.live-face p{font-size: var(--type-copy);line-height:1.6}.face-reading{display:grid;grid-template-columns:1fr auto;gap:6px 12px;margin:12px 0;font-size:15px}.face-reading strong{font-size:17px}.face-reading meter{grid-column:1/-1;width:100%;height:12px;accent-color:var(--accent)}.live-face small{font-size: var(--type-copy);line-height:1.7}
</style>

<style scoped>
.vision-controls{display:grid;gap:8px;margin-top:12px;padding:12px;background:var(--accent-soft);border-radius:10px;text-align:left}.vision-controls button{padding:10px;border:1px solid var(--accent-border);border-radius:8px;background:white;color:var(--accent);cursor:pointer}.vision-controls button:disabled{opacity:.5}.vision-controls small{font-size: var(--type-meta);line-height:1.6;color:var(--text-secondary)}.speech-privacy{display:block;margin-top:10px;line-height:1.6;color:var(--text-muted);font-size: var(--type-meta)}.recording-actions{display:flex;flex-wrap:wrap;gap:8px}.recording-actions .ghost{margin-top:10px}.review-list p{white-space:pre-wrap;overflow-wrap:anywhere}

.live-face{border-top:1px solid var(--border-subtle);padding-top:12px}.live-face h3{font-size:18px;margin:0 0 10px}.live-face p{font-size: var(--type-copy);line-height:1.6}.face-reading{display:grid;grid-template-columns:1fr auto;gap:6px 12px;margin:12px 0;font-size:15px}.face-reading strong{font-size:17px}.face-reading meter{grid-column:1/-1;width:100%;height:12px;accent-color:var(--accent)}.live-face small{font-size: var(--type-copy);line-height:1.7}
</style>

<style scoped>
.camera-dock {
  margin-top: 20px;
  padding-top: 18px;
  border-top: 1px solid var(--border-subtle);
}
.source-field { grid-column: 1 / -1; }
.source-field small { display: block; margin-top: 6px; color: var(--text-muted); font-size: var(--type-meta); line-height: 1.5; }
.source-evidence { display: inline-flex; margin-top: 3px; padding: 5px 8px; border: 1px solid var(--brand-blue-border); border-radius: 7px; background: var(--brand-blue-soft); color: var(--brand-blue-strong); font-size: var(--type-meta); }
.source-location-evidence { display: flex; width: fit-content; border-color: var(--accent-border); background: var(--accent-soft); color: var(--accent); }
.source-location-evidence.unavailable { border-color: #efcfaa; background: #fff5e9; color: #80551d; }

.camera-preview {
  position: relative;
  width: 100%;
  aspect-ratio: 4 / 3;
  overflow: hidden;
  border: 1px solid #cbd9e4;
  border-radius: 14px;
  background: linear-gradient(145deg, #eaf2ff, #eef8f3);
}

.camera-preview video {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transform: scaleX(-1);
}

.camera-placeholder {
  position: absolute;
  inset: 0;
  display: grid;
  place-content: center;
  gap: 6px;
  padding: 14px;
  color: var(--text-secondary);
  text-align: center;
}

.camera-placeholder::before {
  width: 46px;
  height: 34px;
  margin: 0 auto 4px;
  border: 2px solid var(--brand-blue);
  border-radius: 9px;
  background: rgba(255, 255, 255, .65);
  box-shadow: 10px 0 0 -6px var(--brand-blue);
  content: '';
}

.camera-placeholder span { font-size: var(--type-meta); font-weight: 700; }
.camera-placeholder small,
.camera-dock > small { color: var(--text-muted); font-size: var(--type-meta); line-height: 1.5; }
.camera-toggle {
  width: 100%;
  margin: 10px 0 7px;
  padding: 9px 11px;
  border: 1px solid var(--accent-border);
  border-radius: 9px;
  background: #fff;
  color: var(--accent);
  font-weight: 700;
  cursor: pointer;
}
.camera-dock.active .camera-toggle { color: #9a493c; border-color: #efc4bc; background: #fff7f5; }
.record-toggle {
  width: 100%;
  margin: 0 0 7px;
  padding: 9px 11px;
  border: 1px solid #c9d9e7;
  border-radius: 9px;
  background: #f5f9ff;
  color: #315f8f;
  font-weight: 700;
  cursor: pointer;
}
.record-toggle.recording {
  border-color: #eab5aa;
  background: #fff0ed;
  color: #ad402f;
  box-shadow: 0 0 0 3px rgba(190, 69, 49, .08);
}
.record-toggle:disabled { cursor: not-allowed; opacity: .5; }
.camera-error { display: block; color: #a34235 !important; }

.fluency-strip {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  margin-top: 14px;
  padding: 13px;
  border: 1px solid #cfe0e8;
  border-radius: 12px;
  background: linear-gradient(90deg, #f4f8ff, #f2faf6);
}
.fluency-strip span { color: var(--text-secondary); font-size: var(--type-meta); }
.fluency-strip b { display: block; margin-bottom: 3px; color: var(--text-primary); font-size: 18px; }
.fluency-strip small { grid-column: 1 / -1; color: var(--text-muted); }
.live-timeline,
.replay-timeline,
.evidence-only-timeline {
  margin-top: 12px;
  padding: 12px 13px;
  border: 1px solid var(--border-subtle);
  border-radius: 11px;
  background: #fbfcfd;
}
.timeline-track {
  position: relative;
  height: 8px;
  margin: 4px 6px 9px;
  border-radius: 999px;
  background: linear-gradient(90deg, #d7e7df, #d8e7f5);
}
.timeline-track > i,
.timeline-track > button {
  position: absolute;
  top: 50%;
  width: 12px;
  height: 12px;
  margin: -6px 0 0 -6px;
  padding: 0;
  border: 2px solid #fff;
  border-radius: 50%;
  background: #d28b2e;
  box-shadow: 0 1px 5px rgba(34, 65, 55, .24);
}
.timeline-track > .filler { background: #3c7fb2; }
.timeline-track > button { cursor: pointer; }
.timeline-track > button:focus-visible { outline: 3px solid rgba(45, 118, 91, .24); outline-offset: 2px; }
.live-timeline p { display: flex; justify-content: space-between; margin: 0; color: var(--text-muted); font-size: var(--type-meta); }
.live-timeline b { color: var(--text-secondary); font-weight: 650; }
.local-replay { margin-top: 14px; padding: 14px; border: 1px solid #cfe0e8; border-radius: 12px; background: linear-gradient(145deg, #f7fbff, #f6fbf8); }
.replay-head { display: flex; justify-content: space-between; gap: 12px; margin-bottom: 10px; }
.replay-head strong { font-size: var(--type-meta); }
.replay-head span,
.evidence-only-timeline > span { color: var(--text-muted); font-size: var(--type-meta); }
.local-replay video { width: min(100%, 620px); max-height: 350px; display: block; margin: 0 auto; border-radius: 10px; background: #132019; }
.marker-list { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 9px; }
.marker-list button,
.marker-list span { display: inline-flex; align-items: center; gap: 5px; padding: 5px 7px; border: 1px solid var(--border-subtle); border-radius: 7px; background: #fff; color: var(--text-secondary); font-size: var(--type-action); }
.marker-list button { cursor: pointer; }
.marker-list i { width: 7px; height: 7px; border-radius: 50%; background: #d28b2e; }
.marker-list i.filler { background: #3c7fb2; }
.evidence-only-timeline > strong { margin-right: 8px; font-size: var(--type-meta); }
.completion-companion { margin-top: 18px; }
.resume-panel { margin-bottom: 24px; padding: 24px; background: var(--bg-surface); border: 1px solid var(--border-subtle); border-radius: 14px; }
.resume-heading { display: flex; align-items: start; justify-content: space-between; gap: 16px; }
.resume-heading h2 { margin: 0 0 8px; font-size: 20px; }
.resume-heading p, .resume-empty { color: var(--text-secondary); font-size: var(--type-meta); }
.resume-heading p { margin: 0 0 16px; }
.resume-heading .ghost { white-space: nowrap; }
.resume-list { display: grid; }
.resume-item { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 16px 4px; min-height: 64px; border: 0; border-top: 1px solid var(--border-subtle); text-align: left; background: transparent; color: var(--text-primary); cursor: pointer; }
.resume-item:hover { background: var(--accent-soft); }
.resume-item:disabled { opacity: .6; cursor: wait; }
.resume-item b, .resume-item small { display: block; overflow-wrap: anywhere; }
.resume-item small { margin-top: 6px; color: var(--text-secondary); }
.resume-action { flex-shrink: 0; font-size: var(--type-action); color: var(--accent); }
@media (max-width: 600px) { .resume-panel { padding: 16px; } .resume-heading { flex-wrap: wrap; } }
.score-ring { flex-shrink: 0; }
.score-ring.unassessed { font-size: 22px; white-space: nowrap; text-align: center; }
.evaluation-head > strong { flex-shrink: 0; white-space: nowrap; }
.dimension-grid { grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); }

@media (max-width: 800px) {
  .camera-preview { max-width: 300px; margin: 0 auto; }
  .camera-toggle { max-width: 300px; }
}

@media (max-width: 620px) {
  .fluency-strip { grid-template-columns: 1fr 1fr; }
  .replay-head { align-items: flex-start; flex-direction: column; }
}

@media (prefers-reduced-motion: reduce) {
  .speaking .pulse,
  .speaking .voice-bars i { animation: none; }
}

.live-face{border-top:1px solid var(--border-subtle);padding-top:12px}.live-face h3{font-size:18px;margin:0 0 10px}.live-face p{font-size: var(--type-copy);line-height:1.6}.face-reading{display:grid;grid-template-columns:1fr auto;gap:6px 12px;margin:12px 0;font-size:15px}.face-reading strong{font-size:17px}.face-reading meter{grid-column:1/-1;width:100%;height:12px;accent-color:var(--accent)}.live-face small{font-size: var(--type-copy);line-height:1.7}
</style>
