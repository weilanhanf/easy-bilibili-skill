#!/usr/bin/env python3
"""
B站登录验证脚本

用法：
    python scripts/login.py           # 交互式输入Cookie
    python scripts/login.py --check   # 仅验证当前Cookie
    python scripts/login.py --help    # 显示帮助

功能：
    1. 支持粘贴完整Cookie（一键复制）
    2. 自动校验Cookie必需字段
    3. 验证Cookie有效性
    4. 获取用户信息并保存
"""

import json
import logging
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# 添加 lib 目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from lib.api import BilibiliAPI, CookieExpiredError

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# 配置文件路径
CONFIG_PATH = Path(__file__).parent.parent / "config.json"

# Cookie必需字段
REQUIRED_COOKIE_FIELDS = ["SESSDATA", "bili_jct"]
RECOMMENDED_COOKIE_FIELDS = ["buvid3", "buvid4", "DedeUserID"]


# ==================== Cookie 解析 ====================

def parse_cookie(cookie_str: str) -> Dict[str, str]:
    """解析Cookie字符串为字典

    支持多种格式：
    - 分号分隔：SESSDATA=xxx; bili_jct=xxx
    - 换行分隔：每行一个键值对

    Args:
        cookie_str: Cookie字符串

    Returns:
        Cookie键值对字典
    """
    cookies: Dict[str, str] = {}

    # 支持多种格式：分号分隔、换行分隔
    parts = re.split(r'[;\n]', cookie_str.strip())

    for part in parts:
        part = part.strip()
        if '=' in part:
            key, value = part.split('=', 1)
            cookies[key.strip()] = value.strip()

    return cookies


def validate_cookie_format(
    cookie_str: str
) -> Tuple[bool, List[str], List[str], Dict[str, str]]:
    """校验Cookie格式

    Args:
        cookie_str: Cookie字符串

    Returns:
        元组：(是否有效, 缺失的必需字段, 缺失的推荐字段, 解析后的Cookie字典)
    """
    cookies = parse_cookie(cookie_str)

    missing_required = [f for f in REQUIRED_COOKIE_FIELDS if f not in cookies]
    missing_recommended = [f for f in RECOMMENDED_COOKIE_FIELDS if f not in cookies]

    is_valid = len(missing_required) == 0

    return is_valid, missing_required, missing_recommended, cookies


# ==================== 用户交互 ====================

def get_cookie_from_user() -> str:
    """交互式获取Cookie

    Returns:
        用户输入的Cookie字符串
    """
    print("\n" + "=" * 50)
    print("获取完整 Cookie 的方法")
    print("=" * 50)
    print("""
1. 登录 bilibili.com
2. 按 F12 打开开发者工具
3. 切换到 Network（网络）标签
4. 刷新页面，点击任意请求
5. 在 Headers → Request Headers 中找到 Cookie
6. 复制整行 Cookie（包含所有字段）

示例格式：
SESSDATA=xxx; bili_jct=xxx; buvid3=xxx; DedeUserID=123; ...
""")
    print("=" * 50)
    print("\n请粘贴完整 Cookie（粘贴后按回车）：")
    print("（直接 Ctrl+V 粘贴，支持多行）")
    print("-" * 50)

    # 支持多行输入（直到遇到空行）
    lines: List[str] = []
    try:
        while True:
            line = input()
            if not line:
                break
            lines.append(line)
    except EOFError:
        pass

    cookie_str = " ".join(lines) if lines else ""
    return cookie_str


def display_cookie_info(cookies: Dict[str, str]) -> None:
    """显示解析后的Cookie信息

    Args:
        cookies: Cookie字典
    """
    print("\n已识别的 Cookie 字段：")

    # 只显示前8个字段
    display_count = min(8, len(cookies))

    for key in list(cookies.keys())[:display_count]:
        value = cookies[key]
        # 截断长值
        value_preview = value[:20] + "..." if len(value) > 20 else value

        # 标记字段类型
        if key in REQUIRED_COOKIE_FIELDS:
            field_type = "[必需]"
        elif key in RECOMMENDED_COOKIE_FIELDS:
            field_type = "[推荐]"
        else:
            field_type = ""

        print(f"  - {key}: {value_preview} {field_type}")


# ==================== 配置管理 ====================

def load_config() -> Optional[Dict]:
    """加载配置文件

    Returns:
        配置字典，如果文件不存在则返回None
    """
    if not CONFIG_PATH.exists():
        return None

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"读取配置文件失败: {e}")
        return None


def save_config(config: Dict) -> bool:
    """保存配置文件

    Args:
        config: 配置字典

    Returns:
        是否保存成功
    """
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        logger.info(f"配置已保存到 {CONFIG_PATH}")
        return True
    except IOError as e:
        logger.error(f"保存配置文件失败: {e}")
        return False


def create_initial_config() -> bool:
    """创建初始配置

    Returns:
        是否创建成功
    """
    print("=== B站登录配置 ===\n")

    # 获取Cookie
    cookie_str = get_cookie_from_user()

    if not cookie_str:
        print("\n[FAIL] 未输入 Cookie")
        return False

    # 校验格式
    is_valid, missing_required, missing_recommended, cookies = validate_cookie_format(cookie_str)

    if not is_valid:
        print(f"\n[FAIL] Cookie 缺少必需字段: {missing_required}")
        print("\n必需字段说明：")
        print("  - SESSDATA: 登录凭证（必须有）")
        print("  - bili_jct: CSRF Token（必须有）")
        print("\n请重新复制完整的 Cookie")
        return False

    if missing_recommended:
        print(f"\n[提示] Cookie 缺少推荐字段: {missing_recommended}")
        print("建议包含这些字段以提高稳定性：")
        for field in missing_recommended:
            print(f"  - {field}")
        print("\n继续验证...")

    # 显示解析结果
    display_cookie_info(cookies)

    # 验证Cookie
    print("\n正在验证 Cookie...")
    api = BilibiliAPI(cookie_str)
    result = api.validate_cookie()

    if not result.get("valid"):
        print(f"\n[FAIL] Cookie 无效")
        print(f"错误: {result.get('error')}")
        print("\n可能原因：")
        print("  1. Cookie 已过期（有效期约30天）")
        print("  2. 账号在其他设备登录导致Cookie失效")
        print("  3. 复制不完整")
        print("\n请重新登录 bilibili.com 并获取新的 Cookie")
        return False

    print("\n[OK] Cookie 有效！")

    # 保存配置
    config = {
        "user_id": result.get("mid"),
        "user_name": result.get("name"),
        "cookie": cookie_str,
        "vip_status": result.get("vip_status", False),
        "last_sync": None,
        "sync_interval_hours": 24
    }

    if not save_config(config):
        return False

    print(f"\n用户信息：")
    print(f"  - 用户ID: {result.get('mid')}")
    print(f"  - 用户名: {result.get('name')}")
    if result.get("vip_status"):
        print(f"  - 会员状态: 大会员")

    print(f"\n[OK] 配置已保存到 config.json")
    print("\n下一步：")
    print("  python scripts/sync.py  # 同步收藏数据")
    print("  建议同步间隔：24小时")

    return True


def check_existing_cookie() -> bool:
    """验证现有Cookie

    Returns:
        Cookie是否有效
    """
    print("=== B站登录验证 ===\n")

    config = load_config()

    if config is None:
        print("[FAIL] 配置文件不存在")
        print("\n请运行: python scripts/login.py")
        return False

    if not config.get("cookie"):
        print("[FAIL] Cookie 未配置")
        print("\n请运行: python scripts/login.py")
        return False

    # 校验格式
    is_valid, missing_required, missing_recommended, cookies = validate_cookie_format(config["cookie"])

    print("Cookie 格式检查：")
    if is_valid:
        print("  [OK] 必需字段完整")
    else:
        print(f"  [X] 缺少必需字段: {missing_required}")

    if missing_recommended:
        print(f"  [!] 缺少推荐字段: {missing_recommended}")

    print("\n正在验证 Cookie...")

    # 验证有效性
    api = BilibiliAPI(config["cookie"])
    result = api.validate_cookie()

    if not result.get("valid"):
        print(f"\n[FAIL] Cookie 无效")
        print(f"错误: {result.get('error')}")

        # 根据错误类型给出建议
        error = result.get("error", "")
        if "过期" in error or "-101" in error:
            print("\nCookie 已过期，请重新获取")
        print("\n请运行: python scripts/login.py 更新 Cookie")
        return False

    print("\n[OK] Cookie 有效")
    print(f"用户ID: {result.get('mid')}")
    print(f"用户名: {result.get('name')}")

    # 更新用户信息
    config["user_id"] = result.get("mid")
    config["user_name"] = result.get("name")
    config["vip_status"] = result.get("vip_status", False)

    save_config(config)

    # 显示上次同步时间
    last_sync = config.get("last_sync")
    if last_sync:
        # 格式化时间显示
        sync_time = last_sync[:19] if len(last_sync) > 19 else last_sync
        print(f"\n上次同步: {sync_time}")
    else:
        print("\n尚未同步数据")

    print("\n[OK] 配置已更新")
    return True


def update_cookie() -> bool:
    """更新Cookie

    Returns:
        是否更新成功
    """
    print("=== B站登录更新 ===\n")
    return create_initial_config()


# ==================== 帮助信息 ====================

def show_help() -> None:
    """显示帮助信息"""
    print("""
B站登录验证脚本

用法：
    python scripts/login.py           # 交互式配置Cookie
    python scripts/login.py --check   # 验证当前Cookie
    python scripts/login.py --update  # 更新Cookie

Cookie必需字段：
    - SESSDATA: 登录凭证
    - bili_jct: CSRF Token

推荐字段（提高稳定性）：
    - buvid3, buvid4: 设备指纹
    - DedeUserID: 用户ID

获取方法：
    1. 登录 bilibili.com
    2. F12 → Network → 点击请求 → Headers → Cookie
    3. 复制整行Cookie

更多信息：docs/troubleshooting.md
""")


# ==================== 主函数 ====================

def main() -> None:
    """主函数"""
    # 解析参数
    args = sys.argv[1:]

    if "--help" in args or "-h" in args:
        show_help()
        sys.exit(0)

    if "--check" in args:
        success = check_existing_cookie()
        sys.exit(0 if success else 1)

    if "--update" in args:
        success = update_cookie()
        sys.exit(0 if success else 1)

    # 默认：交互式配置或验证
    config = load_config()

    if config is not None:
        # 已有配置，验证并可选更新
        print("发现已有配置文件\n")
        success = check_existing_cookie()

        if not success:
            print("\n" + "-" * 50)
            print("是否要更新 Cookie？(y/n)")

            try:
                choice = input().strip().lower()
                if choice == 'y':
                    success = create_initial_config()
            except (EOFError, KeyboardInterrupt):
                print("\n已取消")
                success = False
    else:
        # 无配置，创建新配置
        success = create_initial_config()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
