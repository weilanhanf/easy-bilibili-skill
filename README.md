# Easy-Bilibili-Skill

> B站个人视频知识库 - 智能收藏检索 AI Skill

## 核心特性

- **精准触发** - 必须包含"B站/哔哩哔哩"关键词才执行
- **分层索引** - 通过 `data_structure.md` 智能导航收藏夹
- **组合检索** - 使用正则表达式精准匹配主题
- **执行透明** - 先输出执行步骤，再给出结果

## 安装

### 方式一：NPX 远程安装（推荐）

```bash
npx skills add weilanhanf/easy-bilibili-skill
```

### 方式二：本地目录安装

```bash
git clone https://github.com/weilanhanf/easy-bilibili-skill.git

# Windows:
xcopy easy-bilibili-skill\.agent\skills\easy-bilibili %USERPROFILE%\.claude\skills\easy-bilibili\ /E /I
# macOS/Linux:
cp -r easy-bilibili-skill/.agent/skills/easy-bilibili ~/.claude/skills/
```

## 依赖安装

本项目依赖 Python 3.8+ 和以下包：

```bash
pip install requests>=2.28.0
```

或直接安装：

```bash
pip install -r scripts/requirements.txt
```

## 快速开始

### 第一步：配置 Cookie

B站收藏数据需要登录才能访问，请配置 Cookie：

1. 登录 [bilibili.com](https://www.bilibili.com)
2. 按 `F12` 打开开发者工具 → Network 标签
3. 刷新页面，点击任意请求 → Headers → Request Headers
4. 复制整行 Cookie 内容
5. 运行配置脚本：

```bash
python scripts/login.py
```

按提示粘贴 Cookie，脚本会自动验证并保存。

**配置文件示例** (`config.json`)：

```json
{
  "user_id": "",
  "user_name": "",
  "cookie": "SESSDATA=你的SESSDATA; bili_jct=你的bili_jct; ...",
  "last_sync": null,
  "sync_interval_hours": 24
}
```

**Cookie 有效期**：约 30 天，过期后重新运行 `login.py` 更新即可。

### 第二步：验证登录

```bash
python scripts/login.py --check
```

### 第三步：同步数据

```bash
# 完整同步（推荐首次使用）
python scripts/sync.py

# 快速同步（仅更新播放量和收藏数）
BILIBILI_QUICK_SYNC=1 python scripts/sync.py
# Windows:
set BILIBILI_QUICK_SYNC=1 && python scripts/sync.py
```

首次使用**必须执行一次同步**，将收藏数据下载到本地。

**同步关注UP主**：

```bash
python scripts/sync_followings.py
```

## 使用示例

### 搜索视频

```
问：B站搜索 Java 教程
问：B站收藏的西安美食视频
问：我的B站收藏有多少个视频？
```

### 同步收藏

```
问：同步我的B站收藏
```

## 项目结构

```
easy-bilibili-skill/
├── .agent/skills/easy-bilibili/  # Skill 主文件
├── scripts/                      # 同步脚本
│   ├── login.py                  # Cookie 配置
│   ├── sync.py                   # 数据同步
│   └── sync_followings.py        # 关注同步
├── knowledge/                    # 知识库（自动生成）
│   ├── data_structure.md         # 根索引
│   ├── folders.md                # 收藏夹列表
│   ├── videos/                   # 视频文档
│   └── followings/               # UP主文档
├── config.json                   # 配置文件（本地）
└── README.md
```

## 故障排查

| 错误 | 原因 | 解决方案 |
|------|------|----------|
| HTTP 412 | 触发反爬 | 等待 30 分钟后重试 |
| Cookie 无效 | 已过期 | 运行 `login.py` 更新 |
| 无数据 | 未同步 | 运行 `sync.py` 初始化 |

## 注意事项

- **Cookie 有效期**：约 30 天，过期后重新配置即可
- **同步频率**：按需同步，避免频繁调用触发反爬
- **数据范围**：仅支持检索自己的收藏数据

## 许可证

本项目仅供个人学习使用，禁止商用。视频内容版权归 B站及相应 UP主 所有。

## 相关资源

- [RAG Skill 参考](https://github.com/ConardLi/rag-skill)
