from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from bot.database import repositories


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


async def build_chat_statistics_report(session: AsyncSession, chat_id: int, days: int) -> str:
    since = _utc_now() - timedelta(days=days)
    violations = await repositories.count_violations(session, chat_id, since)
    punishments = await repositories.count_punishments(session, chat_id, since)
    joins = await repositories.count_members_joined(session, chat_id, since)
    verify_total = await repositories.count_verification_total(session, chat_id, since)
    verify_passed = await repositories.count_verification_passed(session, chat_id, since)
    top_users = await repositories.top_active_users(session, chat_id, 10)

    pass_rate = 0.0
    if verify_total > 0:
        pass_rate = verify_passed * 100.0 / verify_total

    total_messages = sum(int(item.total_messages) for item in top_users)
    ad_intercepts = violations

    lines: list[str] = [
        f"统计周期: 最近 {days} 天",
        f"群组: {chat_id}",
        f"成员变化(入群): {joins}",
        f"消息量(Top10合计): {total_messages}",
        f"违规次数: {violations}",
        f"处罚次数: {punishments}",
        f"入群验证通过率: {verify_passed}/{verify_total} ({pass_rate:.2f}%)",
        f"广告拦截数量: {ad_intercepts}",
        "活跃用户排行(Top10):",
    ]

    if len(top_users) == 0:
        lines.append("- 暂无数据")
    else:
        for idx, item in enumerate(top_users, start=1):
            lines.append(
                f"{idx}. user={item.user_id} messages={item.total_messages} violations={item.total_violations}"
            )

    lines.append("趋势摘要: 若违规次数连续上升，请提高关键词与刷屏策略敏感度。")
    lines.append("扩展接口预留: 可接入 Web/Mini App 看板查询。")
    return "\n".join(lines)
