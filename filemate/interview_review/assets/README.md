# PDF中文字体

`NotoSansSC-Regular.ttf` 是 Google Fonts 的Noto Sans SC可变TTF实例化到weight=400的静态字体，用于ReportLab的TrueType子集嵌入。字体嵌入导出的PDF，阅读器不需要安装系统中文字体。

源文件：[Google Fonts NotoSansSC wght](https://github.com/google/fonts/blob/main/ofl/notosanssc/NotoSansSC%5Bwght%5D.ttf)，2026-10-01下载；使用fontTools `instantiateVariableFont(font, {'wght': 400}, inplace=True, updateFontNames=True)` 生成。fontTools仅是构建本资产时使用的工具，不是应用运行依赖。

许可为SIL Open Font License 1.1，完整原文保留于同目录 `OFL.txt`，见 [官方许可文件](https://github.com/google/fonts/blob/main/ofl/notosanssc/OFL.txt)。不作为单独字体售卖。

Python wheel通过package-data包含字体和许可；Windows桌面sidecar的构建脚本显式collect-data。常用中文、拉丁文字可导出；字体不覆盖的特殊符号仍需其他字体扩展。
