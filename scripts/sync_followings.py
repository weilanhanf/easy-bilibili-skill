#!/usr/bin/env python3
"""
B站关注UP主同步脚本

用法：
    python scripts/sync_followings.py        # 同步关注列表（基础信息）
    python scripts/sync_followings.py --full # 全量更新（包含粉丝数、投稿数）

功能：
    1. 获取用户关注的所有UP主
    2. 获取UP主详细信息
    3. 生成 knowledge/followings/ 文档

注意：
    - 基础模式：仅获取关注列表API返回的基础信息（名称、简介、认证）
    - 完整模式：额外调用每个UP主详情接口获取粉丝数、投稿数
      警告：完整模式会产生大量API请求，可能触发反爬机制（HTTP 412）
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# 添加 lib 目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from lib.api import (
    BilibiliAPI,
    UpInfo,
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
FOLLOWINGS_DIR = KNOWLEDGE_DIR / "followings"


# ==================== 格式化工具函数 ====================

def format_fans(count: Optional[int]) -> str:
    """格式化粉丝数

    Args:
        count: 粉丝数量

    Returns:
        格式化的粉丝数字符串
    """
    if count is None or count <= 0:
        return "未知"

    if count >= 10000:
        return f"{count / 10000:.1f}万"

    return str(count)


def format_videos(count: Optional[int]) -> str:
    """格式化投稿数

    Args:
        count: 投稿数量

    Returns:
        格式化的投稿数字符串
    """
    if count is None or count <= 0:
        return "未知"
    return str(count)


# ==================== 文档生成 ====================

def generate_up_doc(up: UpInfo) -> str:
    """生成UP主文档

    Args:
        up: UP主信息对象

    Returns:
        Markdown格式的文档内容
    """
    fans_str = format_fans(up.fans)
    videos_str = format_videos(up.videos)
    level_str = f"Lv.{up.level}" if up.level else "未知"

    # 分类标签
    tags: List[str] = []

    if up.official:
        tags.append(f"认证: {up.official}")

    if up.videos and up.videos > 100:
        tags.append("高产UP主")

    if up.fans and up.fans > 100000:
        tags.append("10万+粉丝")

    if up.fans and up.fans > 1000000:
        tags.append("百万粉丝")

    tag_str = " | ".join(tags) if tags else "普通UP主"

    return f"""# {up.name}

## 基本信息

| 属性 | 值 |
|------|-----|
| UID | {up.mid} |
| 粉丝数 | {fans_str} |
| 投稿数 | {videos_str} |
| 等级 | {level_str} |

## 简介

{up.sign or '暂无简介'}

## 标签

{tag_str}

## 链接

- [UP主主页](https://space.bilibili.com/{up.mid})
"""


def generate_followings_index(
    ups: List[UpInfo],
    stats: Dict[str, Any]
) -> str:
    """生成关注列表索引

    Args:
        ups: UP主列表
        stats: 统计信息

    Returns:
        Markdown格式的索引内容
    """
    total = len(ups)

    # 统计分类
    verified_count = sum(1 for u in ups if u.is_verified)
    high_fans = sum(1 for u in ups if u.fans and u.fans > 100000)
    million_fans = sum(1 for u in ups if u.fans and u.fans > 1000000)
    high_videos = sum(1 for u in ups if u.videos and u.videos > 100)

    sync_time = stats.get('sync_time', '未知')
    sync_time_display = sync_time[:19] if len(sync_time) > 19 else sync_time

    content = f"""# 关注UP主索引

## 统计

| 指标 | 数量 |
|------|------|
| 关注总数 | {total} |
| 认证UP主 | {verified_count} |
| 10万+粉丝 | {high_fans} |
| 百万粉丝 | {million_fans} |
| 投稿100+ | {high_videos} |
| 最后同步 | {sync_time_display} |

---

## 全部关注

"""

    # 按粉丝数排序
    sorted_ups = sorted(ups, key=lambda u: u.fans or 0, reverse=True)

    for i, up in enumerate(sorted_ups, 1):
        fans_str = format_fans(up.fans)
        videos_str = format_videos(up.videos)

        link = f"[{up.name}](./up_{up.mid}.md)"
        official = f" | {up.official}" if up.official else ""

        content += f"{i}. {link} | 粉丝: {fans_str} | 投稿: {videos_str}{official}\n"

    return content


def generate_data_structure(stats: Dict[str, Any]) -> str:
    """生成根导航文档

    Args:
        stats: 统计信息

    Returns:
        Markdown格式的导航内容
    """
    sync_time = stats.get('sync_time', '未知')
    sync_time_display = sync_time[:19] if len(sync_time) > 19 else sync_time

    return f"""# 知识库导航

## 目录结构

```
knowledge/
├── videos/           # 收藏视频文档（{stats.get('video_count', 0)}个）
├── followings/       # 关注UP主文档（{stats.get('following_count', 0)}个）
├── folders.md        # 收藏夹索引
└── data_structure.md # 本文件
```

## 快速检索

### 收藏视频

阅读 `folders.md` 了解收藏夹结构，搜索视频标题或BV号。

### 关注UP主

阅读 `followings/data_structure.md` 了解关注列表，搜索UP主名称。

---

## 同步信息

- 用户ID: {stats.get('user_id', '未知')}
- 用户名: {stats.get('user_name', '未知')}
- 收藏视频: {stats.get('video_count', 0)} 个
- 关注UP主: {stats.get('following_count', 0)} 个
- 最后同步: {sync_time_display}
"""


# ==================== 错误处理 ====================

def show_error_guide(error: Exception) -> None:
    """显示错误指南

    Args:
        error: 异常对象
    """
    error_msg = str(error)

    print("\n" + "=" * 50)
    print("[ERROR] 同步失败")
    print("=" * 50)

    if isinstance(error, CookieExpiredError) or "-101" in error_msg or "未登录" in error_msg:
        print("\n错误类型: Cookie 已过期")
        print("\n可能原因:")
        print("  1. Cookie 有效期约 30 天，已自然过期")
        print("  2. 账号在其他设备登录导致 Cookie 失效")
        print("  3. 修改密码或退出登录")
        print("\n解决步骤:")
        print("  步骤一：重新获取 Cookie")
        print("    1. 打开浏览器，访问 bilibili.com")
        print("    2. 登录你的账号")
        print("    3. 按 F12 → Network → 刷新页面")
        print("    4. 点击请求 → Headers → Cookie")
        print("    5. 复制整行 Cookie")
        print("\n  步骤二：更新配置")
        print("    运行: python scripts/login.py")
        print("    按提示粘贴新 Cookie")
        print("\n  步骤三：验证成功")
        print("    运行: python scripts/login.py --check")

    elif isinstance(error, AntiCrawlError) or "412" in error_msg:
        print("\n错误类型: 反爬机制触发 (HTTP 412)")
        print("\n可能原因:")
        print("  1. 短时间内请求过于频繁")
        print("  2. 同步操作过于密集")
        print("\n解决建议:")
        print("  - 等待 30-60 分钟后再试")
        print("  - 避免在短时间内多次同步")
        print("  - 建议每天最多同步一次")

    elif isinstance(error, RateLimitError) or "429" in error_msg:
        print("\n错误类型: 请求频率限制 (HTTP 429)")
        print("\n解决建议:")
        print("  - 等待 1-2 小时后再试")
        print("  - 避开高峰时段（20:00-23:00）")

    elif isinstance(error, NetworkError):
        print("\n错误类型: 网络连接问题")
        print("\n解决建议:")
        print("  - 检查网络连接")
        print("  - 确认能访问 bilibili.com")

    else:
        print(f"\n错误类型: {type(error).__name__}")
        print(f"\n错误信息: {error_msg[:100]}{'...' if len(error_msg) > 100 else ''}")
        print("\n建议:")
        print("  1. 检查网络连接")
        print("  2. 稍后重试")
        print("  3. 查看 docs/troubleshooting.md")

    print("\n更多帮助: docs/troubleshooting.md")
    print("=" * 50)


# ==================== 同步主流程 ====================

def sync_followings(full_mode: bool = False) -> bool:
    """同步关注UP主数据

    Args:
        full_mode: 是否获取完整信息（粉丝数、投稿数）
                   完整模式会产生大量API请求，可能触发反爬

    Returns:
        是否同步成功
    """
    print("=== B站关注UP主同步 ===\n")

    if full_mode:
        print("[!] 完整模式：将获取每个UP主的详细信息")
        print("[!] 注意：这会产生大量API请求，可能触发反爬机制")
        print("[!] 建议在非高峰时段使用，且不要频繁执行\n")

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

    print(f"用户ID: {config['user_id']}")
    print(f"用户名: {config.get('user_name', '未知')}\n")

    # 创建目录
    FOLLOWINGS_DIR.mkdir(parents=True, exist_ok=True)

    api = BilibiliAPI(config["cookie"])

    try:
        # 1. 获取关注列表
        print("[1/4] 获取关注列表...")
        all_followings = api.get_all_followings(config["user_id"])
        following_count = len(all_followings)
        print(f"   关注了 {following_count} 个UP主\n")

        # 1.5 完整模式下获取详细信息
        if full_mode and all_followings:
            print("[1.5/4] 获取UP主详细信息...")
            estimated_time = len(all_followings) * api.retry_delay // 60
            print(f"   需要请求 {len(all_followings)} 次，预计耗时 {estimated_time:.0f} 分钟")

            success_count = 0
            for i, up in enumerate(all_followings):
                try:
                    detailed_info = api.get_up_info(up.mid)
                    up.fans = detailed_info.fans
                    up.videos = detailed_info.videos
                    up.level = detailed_info.level

                    if not up.official:
                        up.official = detailed_info.official

                    success_count += 1

                    if (i + 1) % 50 == 0:
                        print(f"   已处理 {i + 1}/{len(all_followings)}...")

                except Exception as e:
                    logger.warning(f"获取 {up.name} 详情失败: {e}")
                    print(f"   跳过 {up.name}: {str(e)[:30]}")

            print(f"   详细信息获取完成 ({success_count}/{len(all_followings)})\n")

        # 2. 生成UP主文档
        print("[2/4] 生成文档...")
        success_count = 0

        for up in all_followings:
            doc = generate_up_doc(up)
            doc_path = FOLLOWINGS_DIR / f"up_{up.mid}.md"

            try:
                with open(doc_path, "w", encoding="utf-8") as f:
                    f.write(doc)
                success_count += 1
            except IOError as e:
                logger.warning(f"写入文档失败 {up.mid}: {e}")

        print(f"   已生成 {success_count} 个UP主文档\n")

        # 3. 生成索引文件
        print("[3/4] 生成索引...")

        stats: Dict[str, Any] = {
            "user_id": config["user_id"],
            "user_name": config.get("user_name", ""),
            "sync_time": datetime.now().isoformat(),
            "following_count": len(all_followings),
            "video_count": config.get("video_count", 0)
        }

        # 关注列表索引
        followings_index = generate_followings_index(all_followings, stats)
        with open(FOLLOWINGS_DIR / "data_structure.md", "w", encoding="utf-8") as f:
            f.write(followings_index)

        # 更新根索引
        root_structure = generate_data_structure(stats)
        with open(KNOWLEDGE_DIR / "data_structure.md", "w", encoding="utf-8") as f:
            f.write(root_structure)

        # 4. 更新配置
        print("[4/4] 更新配置...")
        config["following_count"] = len(all_followings)
        config["last_following_sync"] = datetime.now().isoformat()

        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

        print("\n[OK] 关注UP主同步完成！\n")

        # 统计输出
        verified_count = sum(1 for u in all_followings if u.is_verified)
        high_fans_count = sum(1 for u in all_followings if u.fans and u.fans > 100000)
        high_videos_count = sum(1 for u in all_followings if u.videos and u.videos > 100)

        print("统计:")
        print(f"  - 关注UP主: {len(all_followings)} 个")
        print(f"  - 认证UP主: {verified_count} 个")
        print(f"  - 10万+粉丝: {high_fans_count} 个")
        print(f"  - 投稿100+: {high_videos_count} 个")
        print(f"  - API请求: {api.request_count} 次")

        if api.error_count > 0:
            print(f"  - 请求错误: {api.error_count} 次")

        return True

    except Exception as e:
        logger.error(f"同步失败: {e}")
        show_error_guide(e)
        return False


# ==================== 主函数 ====================

def main() -> None:
    """主函数"""
    parser = argparse.ArgumentParser(
        description="B站关注UP主同步",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
    python scripts/sync_followings.py           # 基础模式
    python scripts/sync_followings.py --full    # 完整模式（警告：可能触发反爬）
        """
    )

    parser.add_argument(
        "--full",
        action="store_true",
        help="获取完整信息（粉丝数、投稿数），会产生大量API请求"
    )

    args = parser.parse_args()

    try:
        success = sync_followings(full_mode=args.full)
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