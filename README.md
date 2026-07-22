# ImageHosting

本地局域网图床服务，Material Design 3 暗色风格 Web UI。在浏览器中上传、浏览、搜索、管理图片，局域网内任何设备均可访问。

## 功能

- **上传与管理** — 拖拽/点击上传，网格浏览，灯箱预览
- **暂存确认** — 先暂存再确认，超时自动清理未确认的文件
- **分组** — 按文件夹组织图片，自由创建/切换/删除分组
- **重命名** — 灯箱中直接重命名图片
- **批量操作** — 多选后批量移动、删除或打标签
- **标签** — 每张图片可打一个标签，按标签筛选，支持全局重命名/删除标签
- **搜索** — 实时文件名搜索，自动补全提示，键盘上下选择
- **排序** — 按名称（A-Z / Z-A）或上传时间（最新/最早）排序
- **复制链接** — 支持 Markdown、HTML、原始 URL 三种格式
- **运行时切换目录** — 设置中修改存储路径，文件自动迁移
- **运行时配置端口** — 设置中修改端口，下次启动生效
- **运行时配置超时** — 设置中修改暂存确认超时时间
- **系统托盘** — 后台运行，托盘图标支持双击打开浏览器
- **Material Design 3** — 亮 / 暗 / 自动主题切换，响应式布局（桌面到手机）
- **局域网访问** — 启动时显示 IP，同网络设备直接访问
- **跨源访问控制** — 端口白名单，默认仅同源；管理/破坏性接口仅限本机调用
- **离线可用** — Material Symbols 字体自托管，无需连接 Google Fonts

## 快速启动

```bash
pip install flask Pillow pystray
python app.py
```

浏览器打开 http://localhost:6951

### 命令行参数

```bash
python app.py                          # 默认端口 6951
python app.py --port 8080              # 自定义端口（覆盖 settings.json）
python app.py --data-dir D:\我的图库    # 自定义存储目录
python app.py --tray                   # 托盘模式运行（打包后默认）
```

## Settings 面板

网页端 Settings 对话框支持多项独立配置，每项单独保存，互不干扰：

| 设置项 | 说明 | 生效时机 |
|--------|------|---------|
| Image Storage Root Directory | 修改图片存储根目录 | 立即迁移（自动移动文件 + 清理旧目录） |
| Staging Timeout (minutes) | 暂存确认超时时间 | 立即生效 |
| Server Port | 服务端口 | 下次启动生效（保存后重启服务器） |
| Allowed Cross-Origin Ports | 允许跨源访问的端口白名单 | 即时生效（无需重启） |
| Theme | 主题（自动 / 亮色 / 暗色） | 立即生效 |

> 存储目录、端口、白名单等管理类操作只能从**本机**（宿主机浏览器）调用；局域网其它设备访问这些接口会返回 403。

## 打包 MSI 安装包

运行 `scripts\build_msi.bat`，按提示输入版本号即可一键打包。

### 前置条件

```bash
pip install pyinstaller pystray
```

WiX Toolset v3.14+（确保 `candle` / `light` / `heat` 在 PATH 中）

### 一键打包

```bash
scripts\build_msi.bat
Enter version (default 1.0.0):
```

脚本会自动完成：写入 `version.txt` → PyInstaller → heat → candle → light → 清理中间文件。
最终输出 `dist\ImageHosting-X.X.X.msi`，仅保留 MSI 文件。

输入的版本号会：① 写入 `version.txt` 打进包，运行时显示在网页顶栏（`v1.0.0`）；
② 作为 MSI 版本用于升级检测。开始菜单的「Uninstall ImageHosting」使用独立图标
`assets\uninstall.ico`。

图标由 `assets\*.svg` 生成：`python scripts\convert_icons.py`（`app` 主图标 +
`uninstall` 卸载图标）。改了 SVG 后需重新运行以更新对应 `.ico`。

### 手动分步

```bash
# 0. 写入版本号（build_msi.bat 会用输入的版本号自动生成）
#    运行时读取此文件显示在顶栏；开发运行无此文件则回退显示局域网地址
echo|set /p="1.0.0">version.txt

# 1. PyInstaller — 打包为 exe
rm -rf dist build *.spec
python -m PyInstaller --onedir --name ImageHosting --icon assets\icon.ico ^
  --add-data "templates;templates" --add-data "static;static" ^
  --add-data "assets\icon.ico;." --add-data "version.txt;." ^
  --hidden-import PIL --hidden-import pystray --noconsole --clean app.py

# 2. 复制图标到输出目录
copy /Y assets\icon.ico dist\ImageHosting\icon.ico

# 3. heat — 收集文件清单
heat.exe dir "dist\ImageHosting" -nologo -ag -cg HarvestedFiles ^
  -dr INSTALLDIR -srd -var "var.SourceDir" -out "dist\ImageHosting.wxs"

# 4. candle — 编译
candle.exe scripts\installer.wxs dist\ImageHosting.wxs ^
  -nologo -dSourceDir="dist\ImageHosting" -dVersion=1.0.0 -out "dist\"

# 5. light — 链接为 MSI
light.exe dist\installer.wixobj dist\ImageHosting.wixobj ^
  -nologo -ext WixUIExtension -cultures:en-US ^
  -out "dist\ImageHosting-1.0.0.msi"

# 6. 清理中间文件
rm -rf build ImageHosting.spec dist\ImageHosting dist\*.wxs dist\*.wixobj dist\*.wixpdb
```

## 安装目录结构

| 路径 | 内容 |
|------|------|
| `C:\Program Files (x86)\ImageHosting\` | 程序文件（只读） |
| `%APPDATA%\ImageHosting\uploads\` | 上传的图片（可读写） |
| `%APPDATA%\ImageHosting\thumbnails\` | 缩略图缓存 |
| `%APPDATA%\ImageHosting\staging\` | 暂存区（自动清理） |
| `%APPDATA%\ImageHosting\settings.json` | 持久化设置 |

## 系统托盘

打包为 `--noconsole` 后，程序后台运行，显示托盘图标。

| 操作 | 行为 |
|------|------|
| **左键单击** | 弹出右键菜单 |
| **左键双击** | 打开浏览器 (`http://localhost:6951`) |
| **菜单：Open Browser** | 打开浏览器 |
| **菜单：Restart Server** | 重启 Flask 服务（新端口生效） |
| **菜单：Exit** | 退出程序 |

## API 概览

| 方法 | 端点 | 说明 |
|------|------|------|
| `GET` | `/` | 主页面 |
| `GET` | `/api/images?group=general` | 获取分组图片列表 |
| `POST` | `/api/upload?group=general` | 上传图片（支持重命名） |
| `POST` | `/api/upload/stage` | 暂存上传（返回 token + 预览 + 预测路径） |
| `POST` | `/api/upload/confirm` | 确认暂存文件（移入正式目录） |
| `POST` | `/api/upload/cancel` | 取消暂存（删除临时文件） |
| `DELETE` | `/api/image/<name>?group=general` | 删除图片 |
| `PUT` | `/api/image/<name>/rename?group=general` | 重命名图片 |
| `PUT` | `/api/image/<name>/move?group=general` | 移动图片到其他分组 |
| `PUT` | `/api/image/<name>/tag?group=general` | 设置图片标签 |
| `DELETE` | `/api/image/<name>/tag?group=general` | 移除图片标签 |
| `POST` | `/api/images/batch-delete` | 批量删除 |
| `POST` | `/api/images/batch-move` | 批量移动 |
| `POST` | `/api/images/batch-tag` | 批量打标签 |
| `PUT` | `/api/tags/<tag>?group=general` | 全局重命名标签 |
| `DELETE` | `/api/tags/<tag>?group=general` | 全局删除标签 |
| `GET` | `/api/groups` | 获取全部分组 |
| `POST` | `/api/groups` | 创建分组 |
| `DELETE` | `/api/groups/<name>` | 删除分组 |
| `GET` | `/api/settings` | 获取当前设置 |
| `PUT` | `/api/settings/data-dir` | 修改存储目录（自动迁移） |
| `PUT` | `/api/settings/staging-timeout` | 修改暂存超时 |
| `PUT` | `/api/settings/port` | 修改端口（校验占用，下次启动生效） |
| `PUT` | `/api/settings/allowed-ports` | 设置允许跨源的端口白名单（即时生效） |
| `PUT` | `/api/settings/theme` | 切换主题（auto / light / dark） |
| `POST` | `/api/settings/browse` | 打开系统文件夹选择器 |
| `POST` | `/api/shutdown` | 优雅关闭（托盘使用） |
| `GET` | `/api/status` | 健康检查 |

> **仅本机接口**：`data-dir`、`port`、`allowed-ports`、`browse`、`shutdown`、`DELETE /api/groups/<name>` 只能从本机（loopback）调用，局域网调用返回 403。完整 API 参考见 [`docs/api.md`](docs/api.md)。

> 详细暂存 API 参考文档见 [`docs/staging-api.md`](docs/staging-api.md) —— 包含所有请求/响应字段、preview 机制、错误码和 JavaScript 示例。

### 跨源访问（CORS）

默认**只允许同源请求**。若要让运行在其它端口的网页（例如 `localhost:3000` 上的前端）从浏览器调用本服务，需先把该端口加入白名单：在 Settings 对话框的 "Allowed Cross-Origin Ports" 中添加，或调用接口：

```bash
curl -X PUT "http://localhost:6951/api/settings/allowed-ports" \
  -H "Content-Type: application/json" \
  -d '{"allowed_origin_ports": [3000, 8080]}'
```

白名单基于端口，覆盖 `localhost` / `127.0.0.1` / 本机局域网 IP 的 http 与 https 来源，**即时生效、无需重启**。列表为空即仅同源。下面涉及从其它站点发起的示例，都要求来源端口已在白名单内。

### 暂存确认示例

```javascript
// 1. 暂存上传 — 文件进入缓存区
fetch('http://192.168.8.146:6951/api/upload/stage', {
  method: 'POST',
  body: formData,
})
.then(r => r.json())
.then(data => {
  const token = data.token;
  console.log('暂存成功，token:', token);
  console.log('预测路径:', data.url);

  // 2. 确认上传 — 移入正式目录
  fetch('http://192.168.8.146:6951/api/upload/confirm', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token: token }),
  })
  .then(r => r.json())
  .then(result => console.log('确认结果:', result));
});
```

```bash
# 1. 暂存
curl -F "files=@photo.jpg" "http://localhost:6951/api/upload/stage?group=wallpapers"
# → {"token": "abc123...", "filename": "photo.jpg", "original_name": "photo.jpg", "expires_in": 300, "preview": "data:image/jpeg;base64,...", "url": "...", "absolute_path": "..."}

# 文件名含不安全字符（非 ASCII、空格、特殊符号）→ 400 拒绝，不自作主张修正：
curl -F "files=@我的照片 (1).jpg" "http://localhost:6951/api/upload/stage"
# → {"error": "Filename contains invalid or unsafe characters. Use only letters, numbers, dots, underscores, and hyphens."}

# 2. 确认
curl -X POST "http://localhost:6951/api/upload/confirm" \
  -H "Content-Type: application/json" \
  -d '{"token": "abc123..."}'
# → {"success": true, "filename": "photo.jpg", "url": "/uploads/wallpapers/photo.jpg", ...}

# 3. 取消（可选）
curl -X POST "http://localhost:6951/api/upload/cancel" \
  -H "Content-Type: application/json" \
  -d '{"token": "abc123..."}'
# → {"success": true}
```

超时时间在 Settings 页面配置，默认为 5 分钟。若目标分组已存在同名文件，stage 会返回 409 错误，不会暂存。

### Settings API 独立调用示例

各设置项都有独立的端点，互不干扰：

```bash
# 只改超时
curl -X PUT "http://localhost:6951/api/settings/staging-timeout" \
  -H "Content-Type: application/json" \
  -d '{"staging_timeout": 600}'

# 只改端口（下次启动生效）
curl -X PUT "http://localhost:6951/api/settings/port" \
  -H "Content-Type: application/json" \
  -d '{"port": 8080}'

# 只改存储目录（自动迁移）
curl -X PUT "http://localhost:6951/api/settings/data-dir" \
  -H "Content-Type: application/json" \
  -d '{"data_dir": "D:\\MyImages"}'
```

### 外部网站上传示例（需将来源端口加入白名单）

```javascript
const formData = new FormData();
formData.append('files', fileInput.files[0]);

fetch('http://192.168.8.146:6951/api/upload?group=wallpapers', {
  method: 'POST',
  body: formData,
})
.then(r => r.json())
.then(data => {
  console.log('图片URL:', data.uploaded[0].url);
  console.log('磁盘路径:', data.uploaded[0].absolute_path);
});
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `?group=名称` | 上传到指定分组 | `general` |
| `filenames`（FormData 字段） | 自定义文件名 JSON 数组 | 使用原始文件名 |

不传 `group` 时默认上传到 `general` 分组。

### 删除示例（跨源时需将来源端口加入白名单）

```javascript
// 单张删除
fetch('http://192.168.8.146:6951/api/image/photo.jpg?group=general', {
  method: 'DELETE',
})
.then(r => r.json())
.then(data => console.log('删除结果:', data));

// 批量删除
fetch('http://192.168.8.146:6951/api/images/batch-delete', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    files: ['photo1.jpg', 'photo2.jpg'],
    group: 'general',
  }),
})
.then(r => r.json())
.then(data => console.log('批量删除结果:', data));
```

```bash
# 单张删除（curl）
curl -X DELETE "http://localhost:6951/api/image/photo.jpg?group=general"

# 批量删除（curl）
curl -X POST "http://localhost:6951/api/images/batch-delete" \
  -H "Content-Type: application/json" \
  -d '{"files": ["a.jpg", "b.jpg"], "group": "general"}'
```

## 项目结构

```
ImageHosting/
├── app.py                  # Flask 应用初始化 + CORS + 设置/系统路由 + 静态服务 + 入口
├── helpers.py              # 纯请求助手（local_only 守卫、group/filename 校验）
├── routes/                 # 领域蓝图
│   ├── __init__.py         # register_blueprints(app)
│   ├── groups.py           # 分组 CRUD
│   └── images.py           # 图片 + 标签 + 批量操作
├── config.py               # 配置
├── utils.py                # 工具函数 + 标签存储 + 原子写 + 尺寸缓存
├── staging.py              # 暂存状态 + stage/confirm/cancel 路由
├── tray.py                 # 系统托盘
├── requirements.txt        # 运行依赖
├── requirements-dev.txt    # 开发/测试依赖（pytest）
├── pytest.ini              # pytest 配置
│
├── assets/                 # 图标
│   ├── icon.svg            # 主图标源（像素画）
│   ├── icon.ico            # 由 convert_icons.py 生成
│   ├── icon.png
│   ├── uninstall.svg       # 卸载图标源
│   └── uninstall.ico       # 由 convert_icons.py 生成（开始菜单 Uninstall）
│
├── docs/
│   ├── api.md              # 完整 API 参考
│   └── staging-api.md      # 暂存 API 参考文档
│
├── scripts/                # 打包脚本
│   ├── build.bat
│   ├── build_msi.bat
│   ├── installer.wxs
│   └── convert_icons.py    # SVG 像素画 → ICO（app / uninstall 图标）
│
├── tests/                  # pytest 套件
│   ├── conftest.py         # fixtures（隔离临时数据目录、client、上传/暂存助手）
│   ├── test_api.py         # 核心：分组/上传/标签/暂存/迁移/CORS/SVG
│   ├── test_utils.py       # 纯函数单测（校验、format_size、原子写、尺寸缓存、helpers）
│   ├── test_staging.py     # 暂存边界（冲突/上限/group 与 tag 覆盖/预览/幂等取消）
│   ├── test_settings.py    # 设置校验 + 端口占用 + 仅本机守卫
│   ├── test_images.py      # rename/move/批量/逐文件标签/非 Pillow 格式
│   └── test_convert_icons.py  # 图标 SVG 矩形解析（v 相对 / V 绝对坐标）
│
├── e2e/                    # Playwright 浏览器端到端测试（opt-in）
│   ├── conftest.py         # live_server（真服务线程）+ 每测试新数据目录
│   └── test_ui.py          # 上传出卡片 / 多选计数 / 删除 / 切主题
│
├── templates/
│   └── index.html          # 单页 Web UI（HTML 结构）
│
└── static/
    ├── css/                # 入口 style.css @import 以下分片（顺序即层叠序）
    │   ├── design-tokens.css      # MD3 设计令牌（颜色、阴影、形状）
    │   ├── material-symbols.css   # 自托管图标字体 @font-face
    │   ├── base.css               # reset / 滚动条 / 顶栏 / chip / 布局
    │   ├── components.css         # 上传 / 工具栏 / 标签 / 搜索 / 表单
    │   ├── cards.css              # 网格 / 卡片 / 图标按钮 / 空态 / toast
    │   ├── dialogs.css            # 灯箱 / 按钮 / 确认框
    │   └── style.css              # 入口（仅 @import）
    ├── fonts/
    │   └── material-symbols-outlined.woff2   # 自托管图标字体
    └── js/
        └── app.js                # 前端应用逻辑
```

## 测试

分两层。都跑在独立的临时数据目录里，不会碰到 `%APPDATA%` 下的真实数据。

**后端（快，默认）** — pytest 回归测试（112 项），覆盖分组 / 上传 / 标签 / 暂存 / 迁移 / 设置校验 / CORS / 仅本机守卫 / SVG 加固等，用 Flask `test_client`，毫秒级。

**前端 E2E（慢，opt-in）** — `e2e/` 下用 Playwright 驱动真 Chromium 点真 UI（上传出卡片、多选计数、删除、切主题），后台线程起真服务。黑盒，不依赖改 `app.js`。

```bash
# 安装开发依赖
pip install -r requirements-dev.txt

# 后端快测（testpaths=tests，不含 e2e）
pytest
pytest tests/test_settings.py -k port      # 单文件 / 过滤

# 前端 E2E（首次需下载浏览器）
playwright install chromium
pytest e2e
```

## 技术栈

- **后端：** Python 3、Flask、Pillow
- **前端：** 原生 JavaScript、Material Design 3（CSS）、Material Symbols（自托管，离线可用）
- **打包：** PyInstaller + WiX Toolset（MSI）
