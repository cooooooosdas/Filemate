# FileMate Tauri Desktop App

## 快速开始

### 前置要求
- Node.js 18+
- Rust (stable)
- pnpm 或 npm

### 安装依赖

```bash
cd src-tauri
pnpm install
```

### 开发模式

```bash
# 同时启动前端和后端
pnpm tauri dev
```

### 构建生产版本

```bash
pnpm tauri build
```

## 项目结构

```
src-tauri/
├── src/              # Rust 后端代码
│   ├── main.rs       # 入口文件
│   └── lib.rs        # 库文件
├── src-tauri.conf.json  # Tauri 配置
├── Cargo.toml        # Rust 依赖
└── icons/            # 应用图标
```

## 功能特性

- [x] 文件上传和处理
- [x] 智能分类
- [x] 里程碑识别
- [x] 日程同步 (.ics)
- [ ] 系统托盘
- [ ] 快捷键
- [ ] 文件拖拽

## 注意事项

1. 后端 API 运行在 http://localhost:8000
2. 前端通过代理访问后端
3. 首次启动需要下载 Tauri 运行时