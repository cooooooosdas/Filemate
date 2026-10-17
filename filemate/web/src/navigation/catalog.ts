export type Tool = {
  path: string
  title: string
  icon: string
  group: string
  family: string
  primary: string
  keywords: string[]
  flag?: string
  aliases?: string[]
}

const catalog: Tool[] = [
  { path: '/', title: '学习工作台', icon: 'House', group: '今天', family: 'home', primary: '/', keywords: ['首页', 'dashboard', 'filemate'] },
  { path: '/today', title: '今日学习', icon: 'DataLine', group: '今天', family: 'plan', primary: '/today', keywords: ['任务', '复习', '提醒'] },
  { path: '/study-plan', title: '学习计划', icon: 'Reading', group: '今天', family: 'plan', primary: '/today', keywords: ['安排', '任务'] },
  { path: '/semester', title: '学期模式', icon: 'Calendar', group: '今天', family: 'plan', primary: '/today', keywords: ['课程', '考试', 'semester'], flag: 'VITE_ENABLE_SEMESTER' },
  { path: '/goals', title: '目标反推', icon: 'Aim', group: '今天', family: 'plan', primary: '/today', keywords: ['学习目标', '规划'] },
  { path: '/ai-tools', title: '阅读与问答', icon: 'Reading', group: '资料与理解', family: 'read', primary: '/knowledge', keywords: ['学习工作区', '问答', '摘要', '笔记', '卡片', '练习'] },
  { path: '/digital-human', title: 'AI 导师讲解', icon: 'VideoPlay', group: '资料与理解', family: 'read', primary: '/knowledge', keywords: ['数字人', '朗读', '语音', 'tts'], flag: 'VITE_ENABLE_DIGITAL_HUMAN' },
  { path: '/knowledge', title: '资料与笔记', icon: 'FolderOpened', group: '资料与理解', family: 'read', primary: '/knowledge', keywords: ['个人知识库', '资料', '文件', '搜索'] },
  { path: '/knowledge-graph', title: '我的知识图谱', icon: 'Share', group: '资料与理解', family: 'read', primary: '/knowledge', keywords: ['节点', '关系', 'graph'], flag: 'VITE_ENABLE_KNOWLEDGE_GRAPH' },
  { path: '/import', title: '导入资料', icon: 'DocumentAdd', group: '资料与理解', family: 'archive', primary: '/knowledge', keywords: ['添加', '上传', '文件'] },
  { path: '/classification', title: '资料审核', icon: 'Collection', group: '资料与理解', family: 'archive', primary: '/knowledge', keywords: ['分类', '命名', '归档', '确认'], aliases: ['/naming'] },
  { path: '/schedule', title: '学习日程', icon: 'Calendar', group: '资料与理解', family: 'archive', primary: '/today', keywords: ['日历', '考试', '时间'] },
  { path: '/history', title: '处理记录', icon: 'Clock', group: '资料与理解', family: 'archive', primary: '/knowledge', keywords: ['历史', '撤销', '归档'] },
  { path: '/programming', title: '编程练习', icon: 'Cpu', group: '练习与求职', family: 'code', primary: '/programming', keywords: ['oj', 'c++', '编译', '判题', '编程教练', '算法'], flag: 'VITE_ENABLE_PROGRAMMING' },
  { path: '/wrongbook', title: '错题复盘', icon: 'Tickets', group: '练习与求职', family: 'plan', primary: '/today', keywords: ['错题本', '复习', '间隔重复', 'spaced repetition'] },
  { path: '/interview', title: '面试与求职', icon: 'Microphone', group: '练习与求职', family: 'career', primary: '/interview', keywords: ['模拟面试', 'ai interview', '回答', '摄像头', '报告'] },
  { path: '/interview-bank', title: '题库管理', icon: 'Notebook', group: '练习与求职', family: 'career', primary: '/interview', keywords: ['面试题', '题目', '导入'] },
  { path: '/career', title: '求职训练中心', icon: 'Aim', group: '练习与求职', family: 'career', primary: '/interview', keywords: ['岗位', '企业', '匹配', '笔试', 'job'], flag: 'VITE_ENABLE_CAREER' },
  { path: '/resume', title: '我的简历', icon: 'Notebook', group: '练习与求职', family: 'career', primary: '/interview', keywords: ['履历', '项目', 'resume'], flag: 'VITE_ENABLE_RESUME' },
  { path: '/growth', title: '成长记录', icon: 'DataAnalysis', group: '成长与设置', family: 'growth', primary: '/growth', keywords: ['成长数据', '成长报告', '用户画像', '学习证据', '统计', 'profile'] },
  { path: '/skills', title: '技能树', icon: 'Share', group: '成长与设置', family: 'growth', primary: '/growth', keywords: ['能力', 'skill tree'], flag: 'VITE_ENABLE_SKILL_TREE' },
  { path: '/trust', title: '可信与隐私', icon: 'Lock', group: '成长与设置', family: 'privacy', primary: '/trust', keywords: ['设置', 'api', '密钥', '备份', '恢复', '导出', '删除'] },
]

export function availableTools(flags: Record<string, unknown> = {}): Tool[] {
  return catalog.filter(tool => !tool.flag || flags[tool.flag] !== 'false')
}

export function primaryPath(path: string, tools: Tool[]): string | undefined {
  return tools.find(tool => tool.path === path || tool.aliases?.includes(path))?.primary
}

export function primaryGroups(tools: Tool[]): { label: string; items: Tool[] }[] {
  return ['今天', '资料与理解', '练习与求职', '成长与设置'].map(label => ({
    label, items: tools.filter(tool => tool.group === label && tool.primary === tool.path),
  })).filter(group => group.items.length)
}

export function childrenTools(primary: string, tools: Tool[]): Tool[] {
  return tools.filter(tool => tool.primary === primary && tool.path !== primary)
}

export function relatedTools(path: string, intent: unknown, tools: Tool[]): Tool[] {
  const current = tools.find(tool => tool.path === path || tool.aliases?.includes(path))
  const family = path === '/import' && intent !== 'archive' ? 'read' : current?.family
  if (!family || ['home', 'privacy', 'code'].includes(family)) return []
  return tools.filter(tool => tool.family === family && tool.path !== '/import')
}

function normalize(value: string): string {
  return value.normalize('NFKC').toLocaleLowerCase().trim().replace(/\s+/g, ' ')
}

export function searchTools(query: string, tools: Tool[]): Tool[] {
  const terms = normalize(query).split(' ').filter(Boolean)
  if (!terms.length) return tools
  return tools.filter(tool => {
    const haystack = normalize([tool.title, tool.group, ...tool.keywords].join(' '))
    return terms.every(term => haystack.includes(term))
  }).sort((a, b) => {
    const relevance = (tool: Tool) => normalize(tool.title) === normalize(query) ? 0
      : normalize(tool.title).includes(normalize(query)) ? 1 : 2
    return relevance(a) - relevance(b)
  })
}
