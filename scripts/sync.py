#!/usr/bin/env python3
"""
B站收藏数据同步脚本

用法：
    python scripts/sync.py           # 增量同步
    python scripts/sync.py --full    # 全量更新

功能：
    1. 获取所有收藏夹列表
    2. 获取每个收藏夹内的视频
    3. 获取观看进度
    4. 生成 knowledge/ 文档

数据流程：
    Cookie验证 → 获取收藏夹 → 获取视频列表 → 获取观看历史 → 生成文档
"""

import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# 添加 lib 目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from lib.api import (
    BilibiliAPI,
    VideoInfo,
    WatchProgress,
    CookieExpiredError,
    AntiCrawlError,
    RateLimitError,
    NetworkError,
    APIResponseError,
)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# 路径配置
ROOT_DIR = Path(__file__).parent.parent
CONFIG_PATH = ROOT_DIR / "config.json"
KNOWLEDGE_DIR = ROOT_DIR / "knowledge"
VIDEOS_DIR = KNOWLEDGE_DIR / "videos"
SYNC_LOG_PATH = ROOT_DIR / ".agent" / "easy-bilibili" / "sync_log.json"

# 同步间隔建议（小时）
RECOMMENDED_SYNC_INTERVAL = 24
DATA_STALE_THRESHOLD = 168  # 7天



def load_sync_log() -> Dict[str, Any]:
    """加载同步日志

    Returns:
        同步日志字典
    """
    if SYNC_LOG_PATH.exists():
        try:
            with open(SYNC_LOG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"读取同步日志失败: {e}")

    return {"attempts": [], "last_success": None}


def save_sync_log(log_data: Dict[str, Any]) -> None:
    """保存同步日志

    Args:
        log_data: 日志数据字典
    """
    try:
        SYNC_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(SYNC_LOG_PATH, "w", encoding="utf-8") as f:
            json.dump(log_data, f, indent=2, ensure_ascii=False)
    except IOError as e:
        logger.error(f"保存同步日志失败: {e}")


def record_sync_attempt(
    success: bool,
    error_msg: Optional[str] = None,
    stats: Optional[Dict[str, int]] = None
) -> None:
    """记录同步尝试

    Args:
        success: 是否成功
        error_msg: 错误信息（如果失败）
        stats: 同步统计信息
    """
    log = load_sync_log()

    attempt: Dict[str, Any] = {
        "time": datetime.now().isoformat(),
        "success": success,
    }

    if error_msg:
        attempt["error"] = error_msg

    if stats:
        attempt["stats"] = stats

    # 保留最近20次记录
    log["attempts"].append(attempt)
    log["attempts"] = log["attempts"][-20:]

    if success:
        log["last_success"] = attempt["time"]

    save_sync_log(log)


def get_recent_failures(hours: int = 24) -> List[Dict[str, Any]]:
    """获取最近N小时内的失败记录

    Args:
        hours: 时间范围（小时）

    Returns:
        失败记录列表
    """
    log = load_sync_log()
    cutoff = datetime.now() - timedelta(hours=hours)
    failures: List[Dict[str, Any]] = []

    for attempt in log.get("attempts", []):
        try:
            t = datetime.fromisoformat(attempt["time"])
            if t > cutoff and not attempt.get("success"):
                failures.append(attempt)
        except (ValueError, TypeError):
            continue

    return failures



def check_sync_status(config: Dict[str, Any]) -> Tuple[str, Optional[float], str]:
    """检查同步状态

    Args:
        config: 配置字典

    Returns:
        元组：(状态, 距上次同步小时数, 状态消息)

    状态值：
    - "never": 从未同步
    - "stale": 数据可能过期（超过7天）
    - "recent": 最近同步过
    - "unknown": 无法解析同步时间
    """
    last_sync = config.get("last_sync")

    if not last_sync:
        return "never", None, "从未同步"

    try:
        last_time = datetime.fromisoformat(last_sync)
        now = datetime.now()
        hours_elapsed = (now - last_time).total_seconds() / 3600

        if hours_elapsed > DATA_STALE_THRESHOLD:
            days = hours_elapsed / 24
            return "stale", hours_elapsed, f"数据已过期（距上次同步 {days:.1f} 天）"

        return "recent", hours_elapsed, f"最近同步于 {hours_elapsed:.1f} 小时前"

    except (ValueError, TypeError) as e:
        logger.warning(f"解析同步时间失败: {e}")
        return "unknown", None, "无法解析同步时间"



def format_duration(seconds: int) -> str:
    """格式化时长

    Args:
        seconds: 秒数

    Returns:
        格式化的时长字符串
    """
    if seconds <= 0:
        return "未知"

    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}分钟"

    hours = minutes // 60
    remaining_minutes = minutes % 60
    return f"{hours}小时{remaining_minutes}分钟" if remaining_minutes else f"{hours}小时"


def format_timestamp(ts: Optional[int]) -> str:
    """格式化时间戳

    Args:
        ts: Unix时间戳

    Returns:
        格式化的日期字符串
    """
    if not ts:
        return "未知"
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")


def calc_watch_progress(progress: int, duration: int) -> int:
    """计算观看进度百分比

    Args:
        progress: 当前进度（秒）
        duration: 总时长（秒）

    Returns:
        进度百分比（0-100）
    """
    if not progress or not duration:
        return 0
    return min(int((progress / duration) * 100), 100)



def generate_video_doc(
    video: VideoInfo,
    watch_info: Optional[WatchProgress]
) -> str:
    """生成视频文档

    Args:
        video: 视频信息
        watch_info: 观看进度（可选）

    Returns:
        Markdown格式的文档内容
    """
    progress = calc_watch_progress(
        watch_info.progress, video.duration
    ) if watch_info else 0

    if progress == 0:
        watch_status = "未看"
    elif progress >= 90:
        watch_status = "已看完"
    else:
        watch_status = f"已看{progress}%"

    return f"""# {video.title}

## 基本信息

| 属性 | 值 |
|------|-----|
| BV号 | {video.bvid} |
| UP主 | [{video.author}](https://space.bilibili.com/{video.author_id}) |
| UP主简介 | {video.author_sign or "暂无简介"} |
| 时长 | {format_duration(video.duration)} |
| 分区 | {video.tname or "未知"} |
| 发布时间 | {format_timestamp(video.pubdate) if video.pubdate else "未知"} |
| 收藏时间 | {format_timestamp(video.fav_time)} |
| 收藏夹 | {video.fav_folder} |
| 链接 | [观看视频](https://www.bilibili.com/video/{video.bvid}) |

## 简介

{video.intro or "暂无简介"}

## 观看状态

| 属性 | 值 |
|------|-----|
| 进度 | {progress}% |
| 状态 | {watch_status} |
| 最近观看 | {format_timestamp(watch_info.view_at) if watch_info else "未观看"} |

## 统计数据

| 属性 | 值 |
|------|-----|
| 播放量 | {video.play_count:,} |
| 点赞数 | {video.like_count:,} |
| 投币数 | {video.coin_count:,} |
| 收藏数 | {video.collect_count:,} |
| 分享数 | {video.share_count:,} |
| 弹幕数 | {video.danmaku_count:,} |
| 评论数 | {video.reply_count:,} |
"""


def generate_folders_index(
    folders: List[Dict[str, Any]],
    folder_counts: Dict[int, int]
) -> str:
    """生成收藏夹索引

    Args:
        folders: 收藏夹列表
        folder_counts: 收藏夹视频数量映射

    Returns:
        Markdown格式的索引内容
    """
    total_videos = sum(folder_counts.values())
    total_folders = len(folders)
    sync_time = datetime.now().isoformat()

    content = f"""# 收藏夹索引

## 统计

- 收藏夹总数：{total_folders}
- 视频总数：{total_videos}
- 最后同步：{sync_time}

## 收藏夹列表

"""

    for folder in folders:
        folder_id = folder.get("id")
        folder_name = folder.get("title", "")
        video_count = folder_counts.get(folder_id, folder.get("media_count", 0))

        content += f"""### [FOLDER] {folder_name} ({video_count}个视频)

- 收藏夹ID: {folder_id}
- 视频数量: {video_count}

"""

    return content


def generate_data_structure(stats: Dict[str, Any]) -> str:
    """生成根导航文档

    Args:
        stats: 统计信息字典

    Returns:
        Markdown格式的导航内容
    """
    return f"""# 知识库导航

## 目录结构

```
knowledge/
├── videos/           # 视频文档（{stats['video_count']}个）
├── folders.md       # 收藏夹索引
└── data_structure.md # 本文件
```

## 快速检索

### 按收藏夹检索

阅读 `folders.md` 了解收藏夹结构，然后搜索视频标题或BV号。

### 按关键词检索

使用文件搜索工具搜索 `videos/` 目录中的内容。

### 按UP主检索

搜索 `UP主:` 关键词找到对应UP主的视频。

### 按观看状态检索

搜索 `状态:` 关键词：
- `未看` - 未观看的视频
- `已看` - 已看过的视频
- `已看完` - 看完的视频

## 同步信息

- 用户ID: {stats['user_id']}
- 用户名: {stats.get('user_name', '未知')}
- 最后同步: {stats['sync_time']}
- 同步视频数: {stats['video_count']}
- 同步收藏夹数: {stats['folder_count']}
"""



def analyze_error(error: Exception) -> Tuple[str, str]:
    """分析错误类型

    Args:
        error: 异常对象

    Returns:
        元组：(错误类型, 错误标题)
    """
    if isinstance(error, AntiCrawlError):
        return "anti_crawl", "反爬机制触发 (HTTP 412)"

    if isinstance(error, RateLimitError):
        return "rate_limit", "请求频率限制 (HTTP 429)"

    if isinstance(error, CookieExpiredError):
        return "cookie_expired", "Cookie 已过期"

    if isinstance(error, NetworkError):
        return "network", "网络连接问题"

    if isinstance(error, APIResponseError):
        return "response_error", "API响应异常"

    error_msg = str(error).lower()

    # 基于错误消息的补充判断
    if "412" in error_msg or "precondition" in error_msg:
        return "anti_crawl", "反爬机制触发 (HTTP 412)"

    if "429" in error_msg or "too many" in error_msg:
        return "rate_limit", "请求频率限制 (HTTP 429)"

    if "-101" in error_msg or "未登录" in error_msg or "login" in error_msg:
        return "cookie_expired", "Cookie 已过期"

    if "-400" in error_msg or "参数" in error_msg:
        return "param_error", "参数错误"

    if "-403" in error_msg or "forbidden" in error_msg or "权限" in error_msg:
        return "permission", "权限不足"

    if "connection" in error_msg or "timeout" in error_msg or "network" in error_msg:
        return "network", "网络连接问题"

    if "json" in error_msg or "decode" in error_msg:
        return "response_error", "响应解析失败"

    return "unknown", "未知错误"


def show_error_guide(error_type: str, error_msg: str) -> None:
    """显示错误指南

    Args:
        error_type: 错误类型
        error_msg: 错误消息
    """
    guides: Dict[str, Dict[str, Any]] = {
        "anti_crawl": {
            "title": "反爬机制触发 (HTTP 412)",
            "reasons": [
                "短时间内请求过于频繁",
                "Cookie缺少必需字段（如 bili_jct）",
                "请求头特征被识别为爬虫"
            ],
            "solutions": [
                "等待 30-60 分钟后再尝试同步",
                "确保 Cookie 包含完整字段（运行 login.py --check 验证）",
                "避免在短时间内多次同步"
            ],
            "next_step": "等待一段时间后重新运行: python scripts/sync.py"
        },
        "rate_limit": {
            "title": "请求频率限制 (HTTP 429)",
            "reasons": [
                "请求次数超过B站限制",
                "同一IP短时间内大量请求"
            ],
            "solutions": [
                "等待 1-2 小后再尝试",
                "更换时间段（避开高峰期 20:00-23:00）"
            ],
            "next_step": "稍后重试: python scripts/sync.py"
        },
        "cookie_expired": {
            "title": "Cookie 已过期",
            "reasons": [
                "Cookie 有效期约 30 天，已自然过期",
                "账号在其他设备登录导致 Cookie 失效",
                "修改密码或退出登录"
            ],
            "solutions": [
                "重新登录 bilibili.com",
                "获取新的完整 Cookie",
                "运行 python scripts/login.py 更新配置"
            ],
            "next_step": "更新 Cookie: python scripts/login.py"
        },
        "param_error": {
            "title": "参数错误",
            "reasons": [
                "用户ID配置不正确",
                "请求参数格式异常"
            ],
            "solutions": [
                "检查 config.json 中的 user_id",
                "运行 login.py --check 重新获取用户信息"
            ],
            "next_step": "验证配置: python scripts/login.py --check"
        },
        "permission": {
            "title": "权限不足",
            "reasons": [
                "Cookie 不完整，缺少关键字段",
                "账号权限异常"
            ],
            "solutions": [
                "确保 Cookie 包含 SESSDATA 和 bili_jct",
                "检查账号是否正常登录 bilibili.com"
            ],
            "next_step": "更新完整 Cookie: python scripts/login.py"
        },
        "network": {
            "title": "网络连接问题",
            "reasons": [
                "无法连接到 B站服务器",
                "网络超时",
                "代理或防火墙拦截"
            ],
            "solutions": [
                "检查网络连接是否正常",
                "尝试访问 bilibili.com 确认网络",
                "检查是否需要代理"
            ],
            "next_step": "确认网络后重试: python scripts/sync.py"
        },
        "response_error": {
            "title": "响应解析失败",
            "reasons": [
                "服务器返回非预期格式",
                "被反爬机制拦截返回空响应",
                "服务端临时异常"
            ],
            "solutions": [
                "等待一段时间后重试",
                "验证 Cookie 是否有效"
            ],
            "next_step": "验证后重试: python scripts/login.py --check"
        },
        "unknown": {
            "title": "未知错误",
            "reasons": ["其他未分类错误"],
            "solutions": [
                "查看详细错误信息",
                "检查 docs/troubleshooting.md",
                "等待后重试"
            ],
            "next_step": "查看文档或重试"
        }
    }

    guide = guides.get(error_type, guides["unknown"])

    print(f"\n错误类型: {guide['title']}")
    print(f"原始信息: {error_msg[:60]}{'...' if len(error_msg) > 60 else ''}\n")

    print("可能原因:")
    for i, reason in enumerate(guide["reasons"], 1):
        print(f"  {i}. {reason}")

    print("\n解决建议:")
    for i, solution in enumerate(guide["solutions"], 1):
        print(f"  {i}. {solution}")

    print(f"\n下一步操作: {guide['next_step']}")
    print("\n更多帮助: docs/troubleshooting.md")
    print("=" * 50)



def sync() -> bool:
    """执行同步

    Returns:
        是否同步成功
    """
    print("=== B站收藏数据同步 ===\n")

    # 检查配置
    if not CONFIG_PATH.exists():
        print("[FAIL] 请先运行 python scripts/login.py 完成登录")
        return False

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"读取配置文件失败: {e}")
        print("[FAIL] 配置文件读取失败")
        return False

    if not config.get("cookie") or not config.get("user_id"):
        print("[FAIL] 配置不完整，请检查 config.json")
        return False

    # 检查同步状态
    status, hours_elapsed, status_msg = check_sync_status(config)
    log_data = load_sync_log()
    recent_failures = get_recent_failures(24)

    # 显示状态提示
    if status == "never":
        print("[i] 首次同步")
    elif status == "stale":
        print(f"[i] {status_msg}")
        print("    建议同步以获取最新收藏数据\n")

    if recent_failures:
        print("[!] 最近同步失败记录")
        print(f"    最近24小时失败 {len(recent_failures)} 次")
        for fail in recent_failures[-3:]:
            error_preview = fail.get('error', '未知错误')[:40]
            print(f"    - {fail['time'][:19]}: {error_preview}")
        print("\n")

    print(f"用户ID: {config['user_id']}")
    print(f"用户名: {config.get('user_name', '未知')}\n")

    # 创建目录
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    VIDEOS_DIR.mkdir(parents=True, exist_ok=True)

    api = BilibiliAPI(config["cookie"])

    # 检查是否跳过完整统计（快速同步模式）
    import os
    quick_sync = os.environ.get("BILIBILI_QUICK_SYNC", "").lower() in ("1", "true", "yes")

    try:
        # 1. 获取收藏夹列表
        print("[1/6] 获取收藏夹列表...")
        folders, videos, folder_counts = api.get_all_favorite_videos(config["user_id"])
        print(f"   找到 {len(folders)} 个收藏夹，{len(videos)} 个视频\n")

        # 2. 获取完整统计数据（默认启用，快速模式跳过）
        if not quick_sync:
            print("[2/6] 获取完整统计数据...")
            print(f"   点赞/投币/分享/弹幕/评论/分区/发布时间")
            print(f"   需要请求 {len(videos)} 次，预计耗时 {len(videos) * 1.5 / 60:.1f} 分钟")

            def progress_cb(current, total, bvid):
                if current % 50 == 0 or current == total:
                    print(f"   进度: {current}/{total}")

            try:
                videos = api.enrich_videos_batch(videos, delay=1.5, progress_callback=progress_cb)
                print(f"   统计数据获取完成\n")
            except (AntiCrawlError, RateLimitError) as e:
                print(f"   警告: 触发限流，停止补充统计数据")
                print(f"   已获取部分数据，继续同步...\n")
        else:
            print("[2/6] 快速同步：跳过完整统计")
            print("   仅包含播放量和收藏数\n")

        # 3. 获取观看历史
        print("[3/6] 获取观看历史...")
        watch_map = api.get_watch_progress_map()
        print(f"   找到 {len(watch_map)} 条观看记录\n")

        # 4. 生成视频文档
        print("[4/6] 生成文档...")
        success_count = 0
        for video in videos:
            watch_info = watch_map.get(video.bvid)
            doc = generate_video_doc(video, watch_info)
            doc_path = VIDEOS_DIR / f"{video.bvid}.md"

            try:
                with open(doc_path, "w", encoding="utf-8") as f:
                    f.write(doc)
                success_count += 1
            except IOError as e:
                logger.warning(f"写入文档失败 {video.bvid}: {e}")

        print(f"   已生成 {success_count} 个视频文档\n")

        # 5. 生成索引文件
        print("[5/6] 生成索引...")
        folders_index = generate_folders_index(folders, folder_counts)
        with open(KNOWLEDGE_DIR / "folders.md", "w", encoding="utf-8") as f:
            f.write(folders_index)

        stats = {
            "user_id": config["user_id"],
            "user_name": config.get("user_name", ""),
            "sync_time": datetime.now().isoformat(),
            "video_count": len(videos),
            "folder_count": len(folders)
        }

        data_structure = generate_data_structure(stats)
        with open(KNOWLEDGE_DIR / "data_structure.md", "w", encoding="utf-8") as f:
            f.write(data_structure)

        # 6. 更新配置
        print("[6/6] 更新配置...")
        config["last_sync"] = datetime.now().isoformat()
        config["video_count"] = len(videos)
        config["folder_count"] = len(folders)

        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

        # 记录成功
        record_sync_attempt(True, stats={
            "videos": len(videos),
            "folders": len(folders),
            "watch_records": len(watch_map)
        })

        print("\n[OK] 同步完成！\n")
        print("统计:")
        print(f"  - 收藏夹: {len(folders)} 个")
        print(f"  - 视频: {len(videos)} 个")
        print(f"  - 观看记录: {len(watch_map)} 条")
        print(f"  - API请求: {api.request_count} 次")

        if api.error_count > 0:
            print(f"  - 请求错误: {api.error_count} 次")

        return True

    except Exception as e:
        # 记录失败
        record_sync_attempt(False, str(e))

        logger.error(f"同步失败: {e}")

        print("\n" + "=" * 50)
        print("[ERROR] 同步失败")
        print("=" * 50)

        error_type, error_title = analyze_error(e)
        show_error_guide(error_type, str(e))

        return False


def main() -> None:
    """主函数"""
    try:
        success = sync()
        sys.exit(0 if success else 1)

    except KeyboardInterrupt:
        print("\n用户取消")
        sys.exit(130)

    except Exception as e:
        logger.exception(f"发生未预期错误: {e}")
        print(f"\n[ERROR] 发生错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
