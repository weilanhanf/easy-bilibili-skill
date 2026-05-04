<div align="center">

# 📺 Easy-Bilibili-Skill

### B站个人视频知识库 — 智能收藏检索 AI Skill

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-blue.svg)](https://python.org)
[![Stars](https://img.shields.io/github/stars/weilanhanf/easy-bilibili-skill?style=social)](https://github.com/weilanhanf/easy-bilibili-skill/stargazers)

<br>

<table>
<tr><td align="left">

📁 &nbsp;你的B站收藏了上千个视频，却找不到那个"很有用的教程"？<br>
🔍 &nbsp;想找某个UP主的视频，但忘了收藏在哪个收藏夹？<br>
📊 &nbsp;想知道自己收藏了多少视频、看了多少、还剩多少没看？

</td></tr>
</table>

### ✨ Easy-Bilibili-Skill 让你用自然语言检索B站收藏

<br>

[🚀 快速开始](#-快速开始) · [📦 安装](#-安装) · [💡 使用示例](#-使用示例) · [🔧 故障排查](#-故障排查)

[**English**](#english) · [**中文**](#中文)

</div>

---

## 中文

### 核心特性

| 特性 | 说明 |
|------|------|
| 🎯 精准触发 | 必须包含"B站/哔哩哔哩"关键词才执行，避免误触发 |
| 📑 分层索引 | 通过 `data_structure.md` 智能导航收藏夹 |
| 🔍 组合检索 | 支持多关键词组合搜索，正则精准匹配 |
| 📊 观看状态 | 支持筛选未看/已看/部分观看的视频 |
| 👥 关注管理 | 同步关注的UP主信息 |
| 🔤 字幕检索 | 支持视频字幕内容搜索（需UP主上传字幕） |

---

## 📦 安装

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

### Python 依赖

```bash
pip install requests>=2.28.0
```

---

## 🚀 快速开始

### 第一步：配置 Cookie

B站收藏数据需要登录才能访问：

1. 登录 [bilibili.com](https://www.bilibili.com)
2. 按 `F12` → Network → 刷新页面
3. 点击任意请求 → Headers → 复制 Cookie 整行
4. 运行配置脚本：

```bash
python scripts/login.py
```

**Cookie 有效期**：约 30 天，过期后重新运行 `login.py` 更新即可。

### 第二步：验证登录

```bash
python scripts/login.py --check
```

### 第三步：同步数据

```bash
# 完整同步（首次推荐）
python scripts/sync.py

# 快速同步（仅更新播放量和收藏数）
BILIBILI_QUICK_SYNC=1 python scripts/sync.py
```

首次使用**必须执行一次同步**，将收藏数据下载到本地。

---

## 💡 使用示例

### 搜索视频

```
问：B站搜索 Java 教程
问：B站收藏的西安美食视频
问：我的B站收藏有多少个视频？
```

### 筛选观看状态

```
问：B站收藏中未看的视频
问：B站收藏中已看完的视频
```

### 同步收藏

```
问：同步我的B站收藏
```

---

## 📁 项目结构

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

---

## 🔧 故障排查

| 错误 | 原因 | 解决方案 |
|------|------|----------|
| HTTP 412 | 触发反爬 | 等待 30 分钟后重试 |
| Cookie 无效 | 已过期 | 运行 `login.py` 更新 |
| 无数据 | 未同步 | 运行 `sync.py` 初始化 |
| 结果不准 | 关键词太宽 | 使用组合关键词 |

---

## ⚠️ 注意事项

- **Cookie 有效期**：约 30 天，过期后重新配置即可
- **同步频率**：按需同步，避免频繁调用触发反爬
- **数据范围**：仅支持检索自己的收藏数据
- **字幕检索**：仅支持UP主已上传字幕的视频（约60-70%覆盖率）

---

## 📄 许可证

本项目仅供个人学习使用，禁止商用。视频内容版权归 B站及相应 UP主 所有。

---

## 🔗 相关资源

- [RAG Skill 参考](https://github.com/ConardLi/rag-skill)

---

<div align="center">

## English

### Bilibili Personal Video Knowledge Base — Smart Favorite Search AI Skill

A powerful skill that lets you search your Bilibili favorites using natural language.

### Features

| Feature | Description |
|---------|-------------|
| 🎯 Precise Trigger | Only executes when "B站/Bilibili" keywords are present |
| 📑 Layered Index | Smart navigation through `data_structure.md` |
| 🔍 Combined Search | Multi-keyword regex matching |
| 📊 Watch Status | Filter by unwatched/watched/partially watched |
| 👥 Following Sync | Sync followed UP owners |
| 🔤 Subtitle Search | Search video subtitles (requires UP owner uploaded) |

### Installation

```bash
# NPX (Recommended)
npx skills add weilanhanf/easy-bilibili-skill

# Local
git clone https://github.com/weilanhanf/easy-bilibili-skill.git
```

### Quick Start

```bash
# 1. Configure Cookie
python scripts/login.py

# 2. Verify login
python scripts/login.py --check

# 3. Sync data
python scripts/sync.py
```

### Usage Examples

```
Q: B站搜索 Java 教程
Q: B站收藏的西安美食视频
Q: 我的B站收藏有多少个视频？
```

### License

For personal learning only. Commercial use prohibited.

---

Created by [@weilanhanf](https://github.com/weilanhanf)

</div>
