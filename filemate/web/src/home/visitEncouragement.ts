import { getEncouragementQuote } from '../services/api'
import { createEncouragementPicker } from './encouragement'

// 同一次SPA访问只请求一次，返回首页时保持原句。
export const getVisitEncouragement = createEncouragementPicker({
  load: getEncouragementQuote,
  storage: () => typeof window === 'undefined' ? undefined : window.localStorage,
})
