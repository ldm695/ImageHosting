# ImageHosting

本地局域网图床服务，Material Design 3 暗色风格 Web UI。在浏览器中上传、浏览、搜索、管理图片，局域网内任何设备均可访问。

## 功能

- **上传与管理** — 拖拽/点击上传，网格浏览，灯箱预览
- **暂存确认** — 先暂存再确认，超时自动清理未确认的文件
- **分组** — 按文件夹组织图片，自由创建/切换/删除分组
- **重命名** — 灯箱中直接重命名图片
- **批量操作** — 多选后批量移动或删除
- **搜索** — 实时文件名搜索，自动补全提示，键盘上下选择
- **排序** — 按名称（A-Z / Z-A）或上传时间（最新/最早）排序
- **复制链接** — 支持 Markdown、HTML、原始 URL 三种格式
- **运行时切换目录** — 设置中修改存储路径，文件自动迁移
- **运行时配置端口** — 设置中修改端口，下次启动生效
- **运行时配置超时** — 设置中修改暂存确认超时时间
- **系统托盘** — 后台运行，托盘图标支持双击打开浏览器
- **Material Design 3** — 暗色主题，响应式布局（桌面到手机）
- **局域网访问** — 启动时显示 IP，同网络设备直接访问

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

网页端 Settings 对话框支持三项独立配置，每项单独保存，互不干扰：

| 设置项 | 说明 | 生效时机 |
|--------|------|---------|
| Image Storage Root Directory | 修改图片存储根目录 | 立即迁移（自动移动文件 + 清理旧目录） |
| Staging Timeout (minutes) | 暂存确认超时时间 | 立即生效 |
| Server Port | 服务端口 | 下次启动生效（保存后重启服务器） |

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
Enter version (default 1.0.3):
```

脚本会自动完成：PyInstaller → heat → candle → light → 清理中间文件。
最终输出 `dist\ImageHosting-X.X.X.msi`，仅保留 MSI 文件。

### 手动分步

```bash
# 1. PyInstaller — 打包为 exe
rm -rf dist build *.spec
python -m PyInstaller --onedir --name ImageHosting --icon assets\icon.ico ^
  --add-data "templates;templates" --add-data "static;static" ^
  --add-data "assets\icon.ico;." --hidden-import PIL --hidden-import pystray ^
  --noconsole --clean app.py

# 2. 复制图标到输出目录
copy /Y assets\icon.ico dist\ImageHosting\icon.ico

# 3. heat — 收集文件清单
heat.exe dir "dist\ImageHosting" -nologo -ag -cg HarvestedFiles ^
  -dr INSTALLDIR -srd -var "var.SourceDir" -out "dist\ImageHosting.wxs"

# 4. candle — 编译
candle.exe scripts\installer.wxs dist\ImageHosting.wxs ^
  -nologo -dSourceDir="dist\ImageHosting" -dVersion=1.0.3 -out "dist\"

# 5. light — 链接为 MSI
light.exe dist\installer.wixobj dist\ImageHosting.wixobj ^
  -nologo -ext WixUIExtension -cultures:en-US ^
  -out "dist\ImageHosting-1.0.3.msi"

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
| `POST` | `/api/images/batch-delete` | 批量删除 |
| `POST` | `/api/images/batch-move` | 批量移动 |
| `GET` | `/api/groups` | 获取全部分组 |
| `POST` | `/api/groups` | 创建分组 |
| `DELETE` | `/api/groups/<name>` | 删除分组 |
| `GET` | `/api/settings` | 获取当前设置 |
| `PUT` | `/api/settings/data-dir` | 修改存储目录（自动迁移） |
| `PUT` | `/api/settings/staging-timeout` | 修改暂存超时 |
| `PUT` | `/api/settings/port` | 修改端口（下次启动生效） |
| `POST` | `/api/settings/browse` | 打开系统文件夹选择器 |
| `POST` | `/api/shutdown` | 优雅关闭（托盘使用） |
| `GET` | `/api/status` | 健康检查 |

> 详细暂存 API 参考文档见 [`docs/staging-api.md`](docs/staging-api.md) —— 包含所有请求/响应字段、preview 机制、错误码和 JavaScript 示例。

### 暂存确认示例（CORS 已启用）

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
# → {"token": "abc123...", "filename": "photo.jpg", "original_name": "photo.jpg", "filename_changed": false, "expires_in": 300, "preview": "data:image/jpeg;base64,...", "url": "...", "absolute_path": "..."}

# 文件名被安全化时（非 ASCII、空格、特殊字符），filename_changed 为 true：
curl -F "files=@我的照片 (1).jpg" "http://localhost:6951/api/upload/stage"
# → {"filename": "_.jpg", "original_name": "我的照片 (1).jpg", "filename_changed": true, ...}

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

超时时间在 Settings 页面配置，默认为 5 分钟。重名检测已内置在 stage 响应中（`name_conflict` 字段），若存在同名文件，confirm 会直接覆盖。

### Settings API 独立调用示例

三个设置项有独立的端点，互不干扰：

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

### 外部网站上传示例（CORS 已启用）

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

### 删除示例（CORS 已启用）

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
    images: ['photo1.jpg', 'photo2.jpg'],
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
  -d '{"images": ["a.jpg", "b.jpg"], "group": "general"}'
```

## 项目结构

```
ImageHosting/
├── app.py                  # Flask 主程序（入口 + 路由）
├── config.py               # 配置
├── utils.py                # 工具函数
├── staging.py              # 暂存状态 + API 路由
├── tray.py                 # 系统托盘
├── requirements.txt        # 依赖
│
├── assets/                 # 图标
│   ├── icon.ico
│   ├── icon.png
│   └── picture.svg
│
├── docs/
│   └── staging-api.md      # 暂存 API 参考文档
│
├── scripts/                # 打包脚本├── scripts/                # 打包脚本
│   ├── build.bat
│   ├── build_msi.bat
│   └── installer.wxs
│
├── templates/
│   └── index.html          # 单页 Web UI（HTML 结构）
│
└── static/
    ├── css/
    │   ├── design-tokens.css   # MD3 设计令牌（颜色、阴影、形状）
    │   └── style.css           # 组件样式
    └── js/
        └── app.js              # 前端应用逻辑
```

## 技术栈

- **后端：** Python 3、Flask、Pillow
- **前端：** 原生 JavaScript、Material Design 3（CSS）、Google Material Symbols
- **打包：** PyInstaller + WiX Toolset（MSI）
