# ImageHosting 改造计划 V2 — 本地/网络双模式解耦架构

## Context

改造现有本地图床，增加 GitHub 网络图床模式，通过 `mode` 参数实现本地/网络存储完全解耦。
核心原则：**本地模式行为不变，网络模式新增逻辑，两者共存互不干扰**。

## 架构概览

```
Web UI ← [mode=local / mode=network] 切换
           ↓
Flask API (mode 参数分发)
    ├── mode=local  → 本地文件系统 (现有逻辑)
    └── mode=network → GitHub REST API (新增逻辑)

Stage/Confirm 暂存: 无论什么 mode，暂存都在本地
                    (confirm 时 mode=local→移入本地; mode=network→上传 GitHub)
```

## API 设计

### 通用改造：所有 API 增加 `mode` 参数

现有 API 端点 + mode 参数，mode 默认 `local` 保持兼容：

| 现有端点 | 改造后 | mode=local | mode=network |
|---------|--------|-----------|-------------|
| `GET /api/images?mode=&group=` | 获取图片列表 | 扫描本地目录 | 调用 GitHub Contents API 列出远程文件 |
| `POST /api/upload?mode=&group=` | 直接上传 | 存本地文件（现有逻辑） | 上传到 GitHub 仓库，返回 CDN URL |
| `POST /api/upload/stage?mode=&group=` | 暂存 | 存本地 staging（现有逻辑） | 存本地 staging，返回预览+预测 GitHub URL |
| `POST /api/upload/confirm?mode=` | 确认暂存 | 移入本地 uploads | 上传 staging 文件到 GitHub，返回 CDN URL |
| `POST /api/upload/cancel?mode=` | 取消暂存 | 同现有逻辑 | 同现有逻辑 |
| `GET /api/groups?mode=` | 获取分组列表 | 扫描本地目录 | 扫描 GitHub repo 子目录 |
| `DELETE /api/image/<name>?mode=&group=` | 删除 | 删本地文件 | 调用 GitHub API 删除远程文件 |
| `POST /api/settings/github` | 保存 GitHub 配置 | — | — |

### mode=network 的端点的特殊行为

#### `POST /api/upload?mode=network`
- 直接上传到 GitHub 仓库（不经过 staging）
- 返回数据结构：
  ```json
  {
    "uploaded": [{
      "filename": "photo.jpg",
      "group": "general",
      "cdn_url": "https://cdn.jsdelivr.net/gh/owner/repo@main/images/general/photo.jpg",
      "raw_url": "https://raw.githubusercontent.com/...",
      "sha": "abc123..."
    }],
    "errors": []
  }
  ```

#### `POST /api/upload/stage?mode=network`
- 文件存本地 staging（同 local 模式）
- 在 staging 时**检查 GitHub 仓库是否存在同名文件**→ 冲突返回 409
- 返回增加 `predicted_cdn_url`、`predicted_raw_url` 字段：
  ```json
  {
    "token": "abc...",
    "filename": "photo.jpg",
    "group": "general",
    "expires_in": 300,
    "preview": "data:image/...",
    "predicted_cdn_url": "https://cdn.jsdelivr.net/gh/owner/repo@main/images/general/photo.jpg",
    "predicted_raw_url": "https://raw.githubusercontent.com/..."
  }
  ```

#### `POST /api/upload/confirm?mode=network`
- 从 staging 读取文件 → 上传到 GitHub → 返回正式 CDN URL
- **confirm 时再次检查命名冲突**：若 GitHub 上已有同名文件（stage 到 confirm 之间被人手动上传），返回 409 并建议重命名
  ```json
  {
    "success": true,
    "filename": "photo.jpg",
    "group": "general",
    "cdn_url": "https://cdn.jsdelivr.net/gh/owner/repo@main/images/general/photo.jpg",
    "raw_url": "https://raw.githubusercontent.com/...",
    "sha": "abc123..."
  }
  ```

#### `GET /api/images?mode=network&group=general`
- 调用 GitHub Contents API 列出 `images/general/` 目录
- 返回与 local 模式兼容的图片信息格式：
  ```json
  [
    {
      "filename": "photo.jpg",
      "group": "general",
      "cdn_url": "https://cdn.jsdelivr.net/gh/...",
      "raw_url": "https://raw.githubusercontent.com/...",
      "size": 123456,
      "formatted_size": "120.6 KB",
      "sha": "abc123...",
      "created": "2026-07-10T12:00:00",
      "created_formatted": "2026-07-10 12:00"
    }
  ]
  ```

#### `GET /api/groups?mode=network`
- 扫描 GitHub repo 的 `images/` 目录下的子目录
- 返回与 local 模式相同格式的分组列表

## 前端设计

### 模式切换

在顶部栏增加模式切换开关：
```
[photo_library] ImageHosting    [Local ▼ | Network]   [:6951] [...]
                                   ↑ 下拉或按钮切换
```

- **Local 模式**：显示本地图片（现有 UI 不变）
  - 上传默认存本地
  - 可切换到 "Upload to Network" 上传到 GitHub

- **Network 模式**：显示 GitHub 仓库中的图片
  - 上传默认到 GitHub
  - 可切换到 "Upload to Local" 存本地
  - 图片 URL 显示 CDN 链接

### 上传区域的模式选择

在原有上传卡片底部增加一个上传目标选择器：
```
[Click to upload or drag & drop]

Upload to: [Local ▼ | Network]
           └── 独立于显示模式，可随时切换
```

### 图片卡片/灯箱的 URL 显示

- **Local 模式**：显示本地 URL（现有行为）+ 可选 "Upload to GitHub" 按钮
- **Network 模式**：显示 CDN URL，复制按钮直接复制 Markdown 链接

## 命名冲突策略

### stage 阶段（两种模式一致）
| 模式 | 冲突检查目标 | 处理方式 |
|------|-------------|---------|
| mode=local | 本地 `uploads/<group>/` 目录 | 已有同名 → 409 |
| mode=network | GitHub 仓库 `images/<group>/` 目录 | 已有同名 → 409 |

### 冲突再检查（confirm 阶段）
- **mode=local**：不需再检查（stage 时已检查，文件不会被他人创建）
- **mode=network**：**需再次检查**（stage 到 confirm 之间可能被别人手动上传到 GitHub）
  - 若冲突 → 409 返回，推荐用户在文件名后加时间戳重试

## 新增/修改文件

| 文件 | 改动 |
|------|------|
| `github_sync.py` | **新增** — GitHub REST API 封装（上传/列表/删除/冲突检查/状态检测） |
| `config.py` | **修改** — 添加 GitHub 配置字段、settings.json 持久化 |
| `app.py` | **修改** — 现有路由增加 `mode` 参数分发，新增 GitHub 配置 API |
| `staging.py` | **修改** — confirm 逻辑增加 mode 分支（local→移入本地，network→上传GitHub） |
| `templates/index.html` | **修改** — 增加模式切换 UI、GitHub 配置面板、上传目标选择 |
| `static/js/app.js` | **修改** — 模式状态管理、双模式数据加载、上传目标切换逻辑 |
| `static/css/style.css` | **修改** — 模式切换组件样式 |
| `requirements.txt` | **修改** — 添加 `requests` |

## 实施步骤

### Step 1: 创建 `github_sync.py`
- `GithubSync` 类：封装所有 GitHub REST API 调用
- 方法：`upload_file` / `upload_bytes` / `check_exists` / `list_files` / `delete_file` / `get_cdn_url` / `test_connection`
- 连接测试：验证 Token + repo 可访问

### Step 2: 修改 `config.py`
- 新增 `GITHUB_TOKEN` / `GITHUB_REPO` / `GITHUB_BRANCH` / `GITHUB_PATH` / `GITHUB_CDN_DOMAIN`
- 从 `settings.json` 读取/写入配置

### Step 3: 修改 `app.py`
- 所有图片相关路由增加 `mode` 参数
- 模式分发：`mode=local` → 现有逻辑，`mode=network` → 调用 github_sync
- 新增 `GET/PUT /api/settings/github` 配置管理端点

### Step 4: 修改 `staging.py`
- `api_upload_confirm`：增加 mode 分支
  - `mode=local` → 现有行为
  - `mode=network` → 从 staging 读取 → 上传 GitHub → 返回 CDN URL

### Step 5: 修改前端
- `index.html`：模式切换、GitHub 配置面板、上传目标选择器
- `app.js`：模式状态管理、双模式数据流、GitHub 配置 CRUD

### Step 6: 修改样式
- `style.css`：模式切换开关、GitHub 状态指示灯样式

## 验证方式

1. **local 模式回归**：所有现有功能正常（上传/暂存/确认/取消/删除/分组/搜索）
2. **network 模式上传**：上传到 GitHub，浏览器打开 CDN URL 确认图片可访问
3. **network 暂存确认**：暂存后关机再确认 → 确认失败（合理），暂存后先确认再关机 → URL 可用
4. **命名冲突**：stage 时 GitHub 已有同名文件 → 409；confirm 时被他人抢先上传 → 409
5. **模式切换**：local↔network 切换，列表数据正确切换
6. **跨模式上传**：local 模式下上传到 network，network 模式下上传到 local
7. **配置持久化**：关闭程序再启动，GitHub 配置保留
8. **关机后图片访问**：已上传到 GitHub 的图片 CDN URL 仍可正常访问
