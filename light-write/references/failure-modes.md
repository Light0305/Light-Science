# 分册：失败模式附录

> light-write SKILL 分册（WRT-D06 分册化）。来源 = v1.0 SKILL §17 verbatim 下沉；主文件路由表指此。

## §17 失败模式附录

| 编号 | 失败形态 | 检出点 | 处置 |
|---|---|---|---|
| F1 | 离线自称已核引用 | 门一状态 unverified 冒充 pass | 整门不许 PASS；注入在线记录重跑 |
| F2 | 单路查无此条即定罪编造 | 门一 identity_unresolved | 补第二路阴性证据再落字 |
| F3 | 零容差误杀（年份 ±1、venue 变体） | 门一 warning 被当 error | 按 FIELD_TOLERANCES 定级，不许私自升格 |
| F4 | DOI 凭记忆写进正文/账本 | validate 裸 DOI 检出 + 门一 doi 核 | 标识符只许 lock 回填，在线反查修正 |
| F5 | 润色改数字串、账未同步 | 门二 printed_vs_ledger/trace | 回改呈现串或更新账（溯源值不许动） |
| F6 | 正文夹带未登记数字 | 门二 unregistered_in_text 点名 | 登记入账（须溯源）或删 |
| F7 | 措辞强于强度档（如 suggestive 用 demonstrates/证实） | 门三 exceeds_ceiling + 降格建议 | 按建议降格；不许升档绕行 |
| F8 | 主张改词后哈希漂移未重验 | 门三 hash_drift_unreverified | 重验贴合度后 reverify-claim 落字 |
| F9 | 披露缺字段临场编期刊口径 | disclose 点名拦停 | 补模板记录官方原文 / 补 use_log |
| F10 | 同族自审、同人自赦 | review record/import 拒 | 换异家族复核者；无则落 UNAVAILABLE |
| F11 | 带异议收据放行 | record/import 拒收 disagree | 先改稿/改登记，重新备包复核 |
| F12 | 稿改后沿用旧审计/旧收据/旧披露 | validate audit.stale + 段门 STALE 检出 | 重跑 audit / disclose / review |
| F13 | 回复信与稿脱节（稿改信未更） | revision check letter_stale | 更新回复后重新 bind |
| F14 | 声称改动无实位 / 无主改动 | revision 双向对账 | 补 [rev:] 标记与锚点，或撤销声称 |
| F15 | 编号冻结后静默插队改号 | figures check 编号不符 | 追加编号或全量重编并落日志 |
| F16 | contested 合同稿件强行置真 | ready 门点名拦停 | 争议由人类裁决并重议合同后再走门 |

---

