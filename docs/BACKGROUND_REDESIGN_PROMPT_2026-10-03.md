# FileMate 新背景设计提示词

这是根据公开参考和FileMate现役任务改写的实施提示词，可直接复制用于后续界面迭代；不是参考站付费模板源码或原站提示词的逐字副本。Aceternity公开页面的「Copy prompt」操作在本次浏览器连接中超时，未取得可核验的剪贴板内容。

## 已采用的参考

- [Aceternity Background Beams](https://ui.aceternity.com/components/background-beams)：大面积曲线路径构成背景，而非小卡片装饰；已直接观察实际预览。
- [Aceternity Aurora Background](https://ui.aceternity.com/components/aurora-background)：参考分层光场；[Startup Landing Page Template](https://ui.aceternity.com/templates/startup-landing-page-template)参考标题、动作和主视觉的比例，未购买或复制其付费源码。
- [React Bits Side Rays](https://reactbits.dev/c/backgrounds/side-rays)：参考从角落展开的光线和可调配色；采用原创SVG与CSS实现，未引入React、OGL或WebGL运行时。
- [Uiverse AatreyuShau背景图案](https://uiverse.io/AatreyuShau/breezy-turkey-82)：参考等高线、几何线条和层次标签，未复制其代码。
- [Anime.js](https://animejs.com/)：现有独立WAAPI入口用于背景慢移和有限进入动画。
- [Showreel.design UI/UX Motion](https://showreel.design/category/uiux-motion/)：浏览作品分类用于构图筛选。「showrealdesign」没有提供精确域名，该站是候选解释，不能视为已核实的同一网站。
- [motion.sites](https://motion.sites/)：检索工具不可访问，用户当前浏览页也显示无法加载、ERR_CONNECTION_CLOSED；没有取得该站模板或提示词，不用其他近似域名冒充。

## 可复制提示词

```text
为现有大学生本地优先学习工作台FileMate重做整页背景和前端配色。
参考Aceternity Background Beams的大面积曲线路径、Aurora的分层光场、React Bits Side Rays的角落光线，以及Uiverse等高线背景的构图。采用原创实现，把光线解释为资料流入、理解成形、练习延续的学习过程。

采用“钴蓝光束”方向：画布#CAD9F3，导航#E1EAFE，主要面板#F2F6FF，墨蓝文字#15264A，操作色#2454D7，主视觉点缀#FFDA91。整个内容区都有连续的冰蓝光场；不要留下旧浅绿画布，不用纯白铺满，不增加紫粉渐变。
首页主视觉占满标题区域，深钴蓝到亮蓝的空间背景、横跨全区的弯曲细光束、右侧大透镜和“资料/理解/练习”折页。左侧保持稳定的深蓝文字衬底，标题44–70px，短句说明18–20px，一个醒目的暖金导入动作。装饰不遮挡点击，不用大量小字或虚构指标。
正文面板用浅冰蓝或近白蓝，正文18px，任务按钮17–18px，触达区域至少44px。侧栏、页头、当前任务导航、导入页、学习工作区、归档预览、登录页统一配色。功能相近的操作放在连续模块中，不为展示效果增加下拉或配置步骤。
只修改视觉和布局，保留所有现役Source/Artifact/Context、引用、保存、失败重试、预览确认、撤销、输入保护和已有路由。
保持Vue3和现有Element Plus，不为参考React组件引入第二套框架。背景只使用原创CSS/SVG与既有Anime.js WAAPI的透明度/变换；滚出视口、页面隐藏时暂停，减少动画时静态，离开页面清理。保留原首屏体积预算，不加载外部字体、媒体或遥测。
在375、768、1024、1440px检查实际编译页面；确认大背景覆盖、字体、对比度、焦点、点击和真实业务闭环。提供三套差异明显的整页样例、选型理由和实装截图。样例数据必须明确标示示意；工程夹具不能代表学习效果。
```
