export interface Encouragement {
  id: string
  text: string
  source: string | null
  author: string | null
  url: string
  provider: 'hitokoto' | 'classic'
  category: 'a' | 'b' | 'd' | 'i' | 'k'
}
