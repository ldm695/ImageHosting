# ImageHosting

本地局域网图床服务，Material Design 3 暗色风格 Web UI。在浏览器中上传、浏览、搜索、管理图片，局域网内任何设备均可访问。

## 功能

- **上传与管理** — 拖拽/点击上传，网格浏览，灯箱预览
- **分组** — 按文件夹组织图片，自由创建/切换/删除分组
- **重命名** — 灯箱中直接重命名图片
- **批量操作** — 多选后批量移动或删除
- **搜索** — 实时文件名搜索，自动补全提示，键盘上下选择
- **排序** — 按名称（A-Z / Z-A）或上传时间（最新/最早）排序
- **复制链接** — 支持 Markdown、HTML、原始 URL 三种格式
- **运行时切换目录** — 设置中修改存储路径，文件自动迁移
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
python app.py --port 8080              # 自定义端口
python app.py --data-dir D:\我的图库    # 自定义存储目录
python app.py --tray                   # 托盘模式运行
```

## 打包 MSI 安装包

### 更新版本号

改两个地方：

| 文件 | 修改 |
|------|------|
| `scripts\installer.wxs` | `Version="1.0.1"` → 新版本号 |
| `scripts\build_msi.bat` | 输出文件名 `ImageHosting-1.0.1.msi` → 新版本号 |

### 前置条件

```bash
pip install pyinstaller pystray
```

WiX Toolset v3.14+（确保 `candle` / `light` / `heat` 在 PATH 中）

### 一键打包

```bash
scripts\build_msi.bat
```

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
  -nologo -dSourceDir="dist\ImageHosting" -out "dist\"

# 5. light — 链接为 MSI
light.exe dist\installer.wixobj dist\ImageHosting.wixobj ^
  -nologo -ext WixUIExtension -cultures:en-US ^
  -out "dist\ImageHosting-1.0.1.msi"
```

输出：`dist\ImageHosting-1.0.1.msi`

## 安装目录结构

| 路径 | 内容 |
|------|------|
| `C:\Program Files (x86)\ImageHosting\` | 程序文件（只读） |
| `%APPDATA%\ImageHosting\uploads\` | 上传的图片（可读写） |
| `%APPDATA%\ImageHosting\thumbnails\` | 缩略图缓存 |
| `%APPDATA%\ImageHosting\settings.json` | 持久化设置 |

## 系统托盘

打包为 `--noconsole` 后，程序后台运行，显示托盘图标。

| 操作 | 行为 |
|------|------|
| **左键单击** | 弹出右键菜单 |
| **左键双击** | 打开浏览器 (`http://localhost:6951`) |
| **菜单：Open Browser** | 打开浏览器 |
| **菜单：Restart Server** | 重启 Flask 服务 |
| **菜单：Exit** | 退出程序 |

## API 概览

| 方法 | 端点 | 说明 |
|------|------|------|
| `GET` | `/` | 主页面 |
| `GET` | `/api/images?group=general` | 获取分组图片列表 |
| `POST` | `/api/upload?group=general` | 上传图片（支持重命名） |
| `DELETE` | `/api/image/<name>?group=general` | 删除图片 |
| `PUT` | `/api/image/<name>/rename?group=general` | 重命名图片 |
| `PUT` | `/api/image/<name>/move?group=general` | 移动图片到其他分组 |
| `POST` | `/api/images/batch-delete` | 批量删除 |
| `POST` | `/api/images/batch-move` | 批量移动 |
| `GET` | `/api/groups` | 获取全部分组 |
| `POST` | `/api/groups` | 创建分组 |
| `DELETE` | `/api/groups/<name>` | 删除分组 |
| `GET` | `/api/settings` | 获取当前设置 |
| `PUT` | `/api/settings` | 修改存储目录（自动迁移） |
| `POST` | `/api/settings/browse` | 打开系统文件夹选择器 |
| `POST` | `/api/shutdown` | 优雅关闭（托盘使用） |

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
├── app.py                  # Flask 主程序
├── config.py               # 配置
├── tray.py                 # 系统托盘
├── requirements.txt        # 依赖
│
├── assets/                 # 图标
│   ├── icon.ico
│   ├── icon.png
│   └── picture.svg
│
├── scripts/                # 打包脚本
│   ├── build.bat
│   ├── build_msi.bat
│   └── installer.wxs
│
├── templates/
│   └── index.html          # 单页 Web UI
│
└── static/
    └── css/
        └── style.css       # Material Design 3 暗色主题
```

## 技术栈

- **后端：** Python 3、Flask、Pillow
- **前端：** 原生 JavaScript、Material Design 3（CSS）、Google Material Symbols
- **打包：** PyInstaller + WiX Toolset（MSI）
