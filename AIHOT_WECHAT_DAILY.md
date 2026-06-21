# AIHot 每日推送（Server酱 → 个人微信）

每天拉取 [AIHot 公开日报](https://aihot.virxact.com/api/public/daily)，通过 Server酱 推送到个人微信。

## 使用

1. 打开 [sct.ftqq.com](https://sct.ftqq.com)，微信扫码登录，复制 **SendKey**
2. 本地预览：

```powershell
python .\scripts\aihot_wechat_daily.py --dry-run
```

3. 发送测试：

```powershell
$env:SENDKEY="SCTxxxxxxxxxxxxx"
python .\scripts\aihot_wechat_daily.py
```

## GitHub Actions 自动推送

仓库里已有 `.github/workflows/aihot-wechat-daily.yml`，每天北京时间 08:00 运行。

在仓库配置 Secret：

- Name: `SENDKEY`
- 位置: Settings → Secrets and variables → Actions → New repository secret
- Value: 你的 Server酱 SendKey

保存后去 Actions 页面手动触发 `AIOt Daily WeCom` 测试。

## 可选配置

| 环境变量 | 说明 | 默认值 |
|----------|------|--------|
| `SENDKEY` | Server酱 SendKey | — |
| `AIHOT_DAILY_URL` | AIHot 日报接口 | `https://aihot.virxact.com/api/public/daily` |
| `AIHOT_DATE` | 指定日期 `YYYY-MM-DD` | 当天 |
| `AIHOT_MAX_ITEMS_PER_SECTION` | 每分类最多几条 | 8 |
| `WECHAT_MAX_CHARS` | 每条消息最大字符数 | 3800 |
| `DRY_RUN` | 设为 `true` 只打印不发送 | — |
