import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'Home',
    component: () => import('../views/Home.vue'),
    meta: { title: '首页' }
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
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

// 路由守卫 - 更新页面标题
router.beforeEach((to, _from, next) => {
  document.title = `${to.meta.title || 'FileMate'} - 智能文件管理`
  next()
})

export default router