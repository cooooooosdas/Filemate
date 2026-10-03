import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { pageLoadFailure } from './load-errors'

const routes: RouteRecordRaw[] = [
  {
    path: '/recover', name: 'Recover', component: () => import('../views/Auth.vue'),
    meta: { title: '找回密码', layout: 'auth' }
  },
  {
    path: '/login',
    name: 'Login',
    component: () => import('../views/Auth.vue'),
    meta: { title: '登录', layout: 'auth' }
  },
  {
    path: '/register',
    name: 'Register',
    component: () => import('../views/Auth.vue'),
    meta: { title: '注册', layout: 'auth' }
  },
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
    meta: { title: '导入资料' }
  },
  {
    path: '/classification',
    name: 'Classification',
    component: () => import('../views/FileReview.vue'),
    meta: { title: '资料审核' }
  },
  {
    path: '/naming',
    name: 'Naming',
    component: () => import('../views/FileReview.vue'),
    meta: { title: '资料审核' }
  },
  {
    path: '/schedule',
    name: 'Schedule',
    component: () => import('../views/Schedule.vue'),
    meta: { title: '学习日程' }
  },
  {
    path: '/history',
    name: 'History',
    component: () => import('../views/History.vue'),
    meta: { title: '处理记录' }
  },
  {
    path: '/ai-tools',
    name: 'AITools',
    component: () => import('../views/LearningWorkspace.vue'),
    meta: { title: '学习工作区' }
  },
  ...(import.meta.env.VITE_ENABLE_DIGITAL_HUMAN === 'false' ? [{
    path: '/digital-human',
    redirect: '/ai-tools',
  }] : [{
    path: '/digital-human',
    name: 'DigitalHuman',
    component: () => import('../views/DigitalHuman.vue'),
    meta: { title: 'AI 导师讲解' }
  }]),
  {
    path: '/study-plan',
    name: 'StudyPlan',
    component: () => import('../views/StudyPlan.vue'),
    meta: { title: '学习计划' }
  },
  ...(import.meta.env.VITE_ENABLE_KNOWLEDGE_GRAPH === 'false' ? [{
    path: '/knowledge-graph',
    redirect: '/ai-tools',
  }] : [{
    path: '/knowledge-graph',
    name: 'KnowledgeGraph',
    component: () => import('../views/KnowledgeGraph.vue'),
    meta: { title: '我的知识图谱' }
  }]),
  {
    path: '/goals',
    name: 'GoalPlanner',
    component: () => import('../views/GoalPlanner.vue'),
    meta: { title: '目标反推' }
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
    path: '/interview-bank',
    name: 'InterviewBank',
    component: () => import('../views/InterviewBank.vue'),
    meta: { title: '题库管理' }
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
  },
  ...(import.meta.env.VITE_ENABLE_PROGRAMMING === 'false' ? [{
    path: '/programming', redirect: '/ai-tools',
  }] : [{
    path: '/programming', name: 'Programming',
    component: () => import('../views/Programming.vue'),
    meta: { title: '编程练习' },
  }]),
  {
    path: '/trust',
    name: 'TrustCenter',
    component: () => import('../views/TrustCenter.vue'),
    meta: { title: '可信与隐私' }
  },
  ...(import.meta.env.VITE_ENABLE_CAREER === 'false' ? [{ path: '/career', redirect: '/ai-tools' }] : [{
    path: '/career', name: 'Career', component: () => import('../views/Career.vue'), meta: { title: '求职训练中心' }
  }])
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.onError((_error, to) => {
  pageLoadFailure.value = { path: to.fullPath }
})
router.afterEach((_to, _from, failure) => {
  if (!failure) pageLoadFailure.value = null
})

// 路由守卫 - 更新页面标题
router.beforeEach((to, _from, next) => {
  document.title = `${to.meta.title || '学习工作台'} · FileMate`
  next()
})

export default router
