---
name: imagehosting-github-sync-plan
description: ImageHosting 本地图床增加 GitHub 双模式同步的完整方案，已搁置待后续实现
metadata:
  type: project
---

# ImageHosting GitHub 图床同步方案

## 项目位置
- 本地图床: `D:\Projects\_Custom\ImageHosting` (Flask + MD3 UI)
- 新项目(空): `D:\Projects\_Custom\GithubImageHosting`

## 用户需求
在现有本地图床基础上，增加 GitHub 网络图床模式，通过 `mode=local` / `mode=network` 参数实现解耦。

## 架构要点
- **API 解耦**: 所有 API 加 `mode` 参数，local→本地文件系统，network→GitHub REST API
- **暂存共享**: 无论什么 mode，stage 都在本地 staging 目录，confirm 时才决定去向
- **命名冲突**: stage 时检查目标存储（本地目录或 GitHub repo）→ 409；network 模式在 confirm 时再次检查防抢先
- **前端切换**: 顶部栏切换 Local/Network 显示模式，上传时可独立选择目标存储
- **关机可用**: 一旦上传到 GitHub，CDN URL 永久可用，不依赖本地服务

## 关键新增文件
- `github_sync.py` — GitHub REST API 封装

## 关键修改文件
- `config.py` — 添加 GitHub 配置
- `app.py` — mode 参数分发
- `staging.py` — confirm 增加 mode 分支
- `templates/index.html` — 模式切换 UI
- `static/js/app.js` — 双模式数据流

## 完整计划
详见 `.claude/plans/github-indexed-bee.md`
