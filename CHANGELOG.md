# Changelog

## 2026-04-25

### Changed
- 调整登录后补签自检（`LogonFallback`）策略：同一站点同一天仅执行一次补签自检，避免当天失败后每次开机/登录重复自检。
- 在状态文件 `meta` 中新增 `fallback_last_check_date` 记录，用于判断当天是否已经执行过补签自检。
- 更新 `README.md` 的调度策略说明，明确“补签自检每天最多一次”。

