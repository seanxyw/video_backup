# video-backup

把手机里的照片和视频备份到 YouTube（视频）和本地（照片）的命令行工具。

## 它做什么

1. **scan** — 扫描一个文件夹，读取每个文件的拍摄时间（从 EXIF / 视频元数据中提取），并生成一份索引文件
2. **split** — 把文件夹里的内容按类型分开：照片 → `output/photos/`，视频 → `output/youtube/`
3. **upload** — 把视频上传到 YouTube（不公开，仅限链接访问），验证上传成功后自动删除本地副本

每次运行都是**幂等的**：中途失败或重复运行不会重复上传，已完成的文件会自动跳过。

---

## 准备工作

### 1. 安装 uv（Python 包管理器）

```bash
brew install uv
```

### 2. 安装 ffprobe（用于读取视频时长）

```bash
brew install ffmpeg
```

### 3. 安装 Python 依赖

在项目目录下运行：

```bash
uv sync
```

### 4. 配置 YouTube API

上传视频需要先获得 Google 的授权。只需要做一次。

**第一步：创建 Google Cloud 项目**

1. 打开 [Google Cloud Console](https://console.cloud.google.com/)
2. 点击顶部的项目选择器 → 「新建项目」，起个名字（比如 `video-backup`）
3. 左侧菜单 → 「API 和服务」→「启用 API 和服务」
4. 搜索 `YouTube Data API v3`，点击启用

**第二步：创建 OAuth 凭据**

1. 左侧菜单 → 「API 和服务」→「凭据」
2. 点击「创建凭据」→「OAuth 客户端 ID」
3. 如果提示先配置同意屏幕：
   - 选择「外部」→ 填写应用名称（随便写）→ 保存
   - 在「测试用户」里添加你自己的 Google 账号邮箱
4. 应用类型选「桌面应用」→ 创建
5. 下载 JSON 文件，放到项目的 `secrets/` 文件夹下（文件名类似 `client_secret_xxx.json`）

---

## 使用方法

所有命令都在项目根目录下运行，格式为：

```bash
uv run python main.py <命令> <参数>
```

### 第一步：扫描

```bash
uv run python main.py scan /path/to/2025-12-19-生态瓶
```

可以用 `--output-dir` 指定输出目录（默认是项目目录下的 `output/`）：

```bash
uv run python main.py scan /path/to/2025-12-19-生态瓶 --output-dir /Volumes/MyDisk/backup
```

- 支持任意路径（绝对路径或相对路径均可）
- 递归扫描文件夹里的所有文件
- 读取拍摄时间并更新文件的修改时间
- 生成 `index/2025-12-19-生态瓶.json`（记录输入和输出目录路径，后续命令自动使用）

### 第二步：分类

```bash
uv run python main.py split 2025-12-19-生态瓶
```

- 照片 → `output/photos/2025-12-19-生态瓶/`
- 视频 → `output/youtube/2025-12-19-生态瓶/`（平铺，无子目录）
- 未知格式 → `output/unknown/2025-12-19-生态瓶/`

### 第三步：上传视频

```bash
uv run python main.py upload 2025-12-19-生态瓶
```

- 首次运行会打开浏览器，完成 Google 账号授权（只需一次）
- 逐个上传视频，等待 YouTube 处理完成
- 验证每个视频：隐私状态（不公开）+ 文件大小 + 视频时长
- 全部验证通过后，在 YouTube 上创建对应播放列表，并删除本地视频副本

可以用 `--title` 自定义播放列表名称：

```bash
uv run python main.py upload 2025-12-19-生态瓶 --title "生态瓶观察记录"
```

---

## 文件结构

```
video-backup/
├── output/              # 默认输出目录（可用 --output-dir 指定其他位置）
│   ├── photos/          # 分类后的照片
│   ├── youtube/         # 待上传的视频（上传验证通过后自动删除）
│   └── unknown/         # 无法识别格式的文件
├── index/               # 每个文件夹的扫描 + 上传状态（JSON）
├── secrets/             # Google OAuth 凭据（不纳入 git）
├── main.py              # 入口
├── scan.py              # Workflow 1
├── split.py             # Workflow 2
└── upload.py            # Workflow 3
```

## 支持的文件格式

| 类型 | 格式 |
|------|------|
| 照片 | JPG, JPEG, PNG, HEIC, HEIF, DNG, RAF, CR2, CR3, GPR, INSP, TIFF |
| 视频 | MP4, MOV, MTS, M2TS, INSV, AVI, MKV |
| 忽略 | LRV, THM, DS_Store（GoPro 缩略图等辅助文件）|

---

## 常见问题

**Q：上传到一半断了怎么办？**
重新运行同样的命令。已上传并验证的视频会自动跳过，只会继续处理未完成的。

**Q：YouTube 每天能上传多少？**
YouTube API 有每日配额限制，大约能上传 6 个视频/天（每个视频消耗约 1600 配额单位，每天总额 10000）。配额在太平洋时间午夜重置。

**Q：上传的视频别人能看到吗？**
不能。所有视频和播放列表都设置为「不公开」（unlisted）——只有拥有链接的人才能访问，不会出现在搜索结果里。
