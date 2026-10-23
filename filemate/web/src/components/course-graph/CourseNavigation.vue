<template>
  <nav class="cw-navigation" aria-label="课程与章节">
    <label class="cw-field">当前课程<select :value="browse.courseId" :disabled="loading" @change="$emit('course', ($event.target as HTMLSelectElement).value)"><option value="">选择课程</option><option v-for="course in courses.items" :key="course.course_id" :value="course.course_id">{{ course.name }}</option></select></label>
    <div v-if="courses.total > 50" class="cw-pagination"><button :disabled="courses.offset === 0 || loading" @click="$emit('coursePage', -1)">前页课程</button><button :disabled="courses.offset+50 >= courses.total || loading" @click="$emit('coursePage', 1)">后页课程</button></div>
    <template v-if="navigation">
      <p class="cw-kicker">课程目录</p><button class="cw-directory-item" :aria-pressed="!browse.chapterId" @click="filter('chapter_id', '')"><span>全部知识</span><span>{{ navigation.total_concepts }}</span></button>
      <ol v-if="chapterPath?.items.length" class="cw-chapter-path" aria-label="当前章节路径"><li v-for="(chapter, depth) in chapterPath.items" :key="chapter.id"><button :aria-current="chapter.id === browse.chapterId ? 'location' : undefined" @click="filter('chapter_id', chapter.id)"><IconCornerDownRight :size="17" aria-hidden="true" /><span>{{ depth+1 }}. {{ chapter.title }}</span></button></li></ol>
      <p v-if="chapterPath?.items.length" class="cw-caption">下级章节</p>
      <button v-for="group in navigation.groups" :key="group.id" class="cw-directory-item" :aria-pressed="browse.chapterId === group.id" @click="filter('chapter_id', group.id)"><span>{{ group.title }}<IconChevronRight v-if="group.child_count" :size="17" aria-hidden="true" /></span><span>{{ group.concept_count }}</span></button>
      <p v-if="chapterPath?.items.length && !navigation.groups.length" class="cw-caption">已到最末一级章节</p>
      <div v-if="navigation.group_total > navigation.group_limit" class="cw-pagination" aria-label="章节分页"><button :disabled="loading || navigation.group_offset === 0" @click="$emit('navigationPage', Math.max(0, navigation.group_offset-navigation.group_limit), navigation.source_offset)">前页章节</button><button :disabled="loading || navigation.group_offset+navigation.group_limit >= navigation.group_total" @click="$emit('navigationPage', navigation.group_offset+navigation.group_limit, navigation.source_offset)">后页章节</button></div>
      <label class="cw-field cw-source-filter">来源范围<select :value="browse.sourceId" :disabled="loading" @change="filter('source_id', ($event.target as HTMLSelectElement).value)"><option value="">全部有效资料</option><option v-for="source in navigation.sources.filter(s => s.active)" :key="source.source_id" :value="source.source_id">{{ source.original_name }}</option></select></label>
      <div v-if="navigation.source_total > navigation.source_limit" class="cw-pagination" aria-label="来源分页"><button :disabled="loading || navigation.source_offset === 0" @click="$emit('navigationPage', navigation.group_offset, Math.max(0, navigation.source_offset-navigation.source_limit))">前页资料</button><button :disabled="loading || navigation.source_offset+navigation.source_limit >= navigation.source_total" @click="$emit('navigationPage', navigation.group_offset, navigation.source_offset+navigation.source_limit)">后页资料</button></div>
    </template>
  </nav>
</template>
<script setup lang="ts">
import { IconChevronRight, IconCornerDownRight } from '@tabler/icons-vue'
import type { GraphCourse, GraphPage } from '../../types/courseGraph'
import type { CourseBrowse, WorkspaceChapterPath, WorkspaceFilter, WorkspaceNavigation } from '../../types/courseWorkspace'
const props = defineProps<{ courses: GraphPage<GraphCourse>; browse: CourseBrowse; navigation: WorkspaceNavigation | null; chapterPath?: WorkspaceChapterPath | null; loading: boolean }>()
const emit = defineEmits<{ course: [id: string]; filter: [filter: WorkspaceFilter]; openManager: []; coursePage: [delta: number]; navigationPage: [groups: number, sources: number] }>()
function filter(name: string, value: string) { emit('filter', { chapter_id: props.browse.chapterId || undefined, source_id: props.browse.sourceId || undefined, relations: props.browse.relations, [name]: value || undefined }) }
</script>
