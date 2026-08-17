import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'Home',
    component: () => import('../views/Home.vue'),
    meta: { title: '学习工作台' }
  },
  {
    path: '/today',
    name: 'Today',
    component: () => import('../views/Today.vue'),
    meta: { title: '今日学习' }
  },
  {
    path: '/import',
    name: 'Import',
    component: () => import('../views/Import.vue'),
    meta: { title: '导入文件' }
  },
  {
    path: '/classification',
    name: 'Classification',
    component: () => import('../views/Classification.vue'),
    meta: { title: '分类预览' }
  },
  {
    path: '/naming',
    name: 'Naming',
    component: () => import('../views/Naming.vue'),
    meta: { title: '命名预览' }
  },
  {
    path: '/schedule',
    name: 'Schedule',
    component: () => import('../views/Schedule.vue'),
    meta: { title: '日程预览' }
  },
  {
    path: '/history',
    name: 'History',
    component: () => import('../views/History.vue'),
    meta: { title: '历史记录' }
  },
  {
    path: '/ai-tools',
    name: 'AITools',
    component: () => import('../views/AITools.vue'),
    meta: { title: 'AI工具箱' }
  },
  {
    path: '/study-plan',
    name: 'StudyPlan',
    component: () => import('../views/StudyPlan.vue'),
    meta: { title: 'AI 学习计划' }
  },
  {
    path: '/wrongbook',
    name: 'Wrongbook',
    component: () => import('../views/Wrongbook.vue'),
    meta: { title: '错题复盘' }
  },
  {
    path: '/interview',
    name: 'Interview',
    component: () => import('../views/Interview.vue'),
    meta: { title: '模拟面试' }
  },
  {
    path: '/growth',
    name: 'Growth',
    component: () => import('../views/Growth.vue'),
    meta: { title: '成长数据' }
  },
  {
    path: '/knowledge',
    name: 'Knowledge',
    component: () => import('../views/Knowledge.vue'),
    meta: { title: '个人知识库' }
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

// 路由守卫 - 更新页面标题
router.beforeEach((to, _from, next) => {
  document.title = `${to.meta.title || 'FileMate'} - 大学生学习智能体`
  next()
})

export default router
