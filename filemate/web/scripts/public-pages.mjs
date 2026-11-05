export const publicPages = [
 {path:'/',title:'FileMate · 大学生 AI 学习工作台',description:'打开课件，读原文、记笔记、做练习。'},
 {path:'/login',title:'登录 FileMate',description:'保存课件和笔记，记录练习与复习。登录后回到自己的学习空间。'},
 {path:'/register',title:'注册 FileMate',description:'创建你的学习空间，保存课程资料、练习与复习记录。'},
 {path:'/trust',title:'可信与隐私 · FileMate',description:'查看资料授权、任务处理过程，以及系统保存的记忆。'},
]
const esc = text => text.replaceAll('&','&amp;').replaceAll('"','&quot;').replaceAll('<','&lt;')
export function decoratePage(html,page){
 const url='https://filemate.asia'+page.path,image='https://filemate.asia/share/filemate-1200x630.png'
 const meta=`<meta name="description" content="${esc(page.description)}" />
<link rel="canonical" href="${url}" />
<meta property="og:type" content="website" />
<meta property="og:site_name" content="FileMate" />
<meta property="og:title" content="${esc(page.title)}" />
<meta property="og:description" content="${esc(page.description)}" />
<meta property="og:url" content="${url}" />
<meta property="og:image" content="${image}" />
<meta property="og:image:width" content="1200" /><meta property="og:image:height" content="630" />
<meta name="twitter:card" content="summary_large_image" /><meta name="twitter:title" content="${esc(page.title)}" />
<meta name="twitter:description" content="${esc(page.description)}" /><meta name="twitter:image" content="${image}" />
<script type="application/ld+json">${JSON.stringify({'@context':'https://schema.org','@graph':[{'@type':'Organization',name:'FileMate',url:'https://filemate.asia',logo:image},{'@type':'WebSite',name:'FileMate',url:'https://filemate.asia',inLanguage:'zh-CN'}]})}</script>`
 return html.replace(/<title>.*?<\/title>/s,`<title>${page.title}</title>`).replace(/<meta name="description"[^>]*>/,'').replace('</head>',meta+'\n</head>')
}
export function validateSnapshot(markup){
 if(!/<h1\b/.test(markup)||!/<p\b/.test(markup))throw new Error('missing public heading or paragraph')
 if(/\bvalue="[^"]+"|recovery_code|confirmation_token|Bearer\s|sk-[a-zA-Z0-9]{12}/.test(markup))throw new Error('private input in public snapshot')
}
export async function captureOrFallback(spa,capture,warn=console.warn){
 try{return await capture()}catch(error){warn(`[FileMate prerender] ${error.message}; keeping SPA fallback.`);return spa}
}
