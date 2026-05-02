# 收藏夹索引

> 此文件为示例模板，同步后自动生成

## 状态

知识库未初始化时显示此模板。

## 统计

初始化后将显示：
- 收藏夹总数
- 视频总数
- 最后同步时间

## 收藏夹列表

同步后将列出所有收藏夹及其视频数量。

---

## 初始化方法

```bash
# 1. 配置 Cookie
cp config.template.json config.json
# 编辑 config.json，填入你的 SESSDATA

# 2. 安装依赖
pip install requests

# 3. 验证登录
python scripts/login.py

# 4. 同步数据
python scripts/sync.py
```