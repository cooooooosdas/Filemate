import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
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
    component: () => import('../views/Classification.vue'),
    meta: { title: '分类确认' }
  },
  {
    path: '/naming',
    name: 'Naming',
    component: () => import('../views/Naming.vue'),
    meta: { title: '命名确认' }
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
  {
    path: '/study-plan',
    name: 'StudyPlan',
    component: () => import('../views/StudyPlan.vue'),
    meta: { title: '学习计划' }
  },
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
  {
    path: '/trust',
    name: 'TrustCenter',
    component: () => import('../views/TrustCenter.vue'),
    meta: { title: '可信与隐私' }
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

// 路由守卫 - 更新页面标题
router.beforeEach((to, _from, next) => {
  document.title = `${to.meta.title || '学习工作台'} · FileMate`
  next()
})

export default router
