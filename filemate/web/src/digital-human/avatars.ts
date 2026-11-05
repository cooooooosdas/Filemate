import campusImage from '../assets/optimized/filemate-mascot-tutor.webp'
import expressionsImage from '../assets/optimized/filemate-mascot-expressions-tutor.webp'

export interface DigitalHumanAvatar {
  avatarId: string
  avatarName: string
  avatarType: 'illustration'
  gender: 'female'
  style: 'campus' | 'portrait'
  voiceId: string
  skinId: string
  provider: 'microsoft_edge'
  configuration: { presentation: 'full_body' | 'expression_sprite' }
  image: string
}

export const AVATARS: DigitalHumanAvatar[] = [
  {
    avatarId: 'filemate-campus', avatarName: '校园导师',
    avatarType: 'illustration', gender: 'female', style: 'campus',
    voiceId: 'zh-CN-XiaoxiaoNeural', skinId: 'filemate-original', provider: 'microsoft_edge',
    configuration: { presentation: 'full_body' }, image: campusImage,
  },
  {
    avatarId: 'filemate-portrait', avatarName: '近景导师',
    avatarType: 'illustration', gender: 'female', style: 'portrait',
    voiceId: 'zh-CN-XiaoxiaoNeural', skinId: 'filemate-expressions', provider: 'microsoft_edge',
    configuration: { presentation: 'expression_sprite' }, image: expressionsImage,
  },
]
