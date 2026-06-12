from dataclasses import dataclass, field
from typing import Any

from aiogram import Bot
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramBadRequest
from loguru import logger

from ..config import DEBUG


def _chat_id_for_api(channel_ref: str) -> str | int:
    ref = channel_ref.strip()
    if ref.lstrip('-').isdigit():
        return int(ref)
    if not ref.startswith('@'):
        return f'@{ref}'
    return ref


def is_member_subscribed(status: ChatMemberStatus, is_member: bool | None = None) -> bool:
    if status in (
        ChatMemberStatus.CREATOR,
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.MEMBER,
    ):
        return True
    if status == ChatMemberStatus.RESTRICTED:
        return bool(is_member)
    return False


def _is_bot_access_error(exc: TelegramBadRequest) -> bool:
    text = str(exc).lower()
    return any(
        phrase in text
        for phrase in (
            'member list is inaccessible',
            'chat not found',
            'bot is not a member',
            'have no rights',
            'not enough rights',
            'user not found',
        )
    )


@dataclass
class OpSubscriptionStatus:
    """Результат проверки подписки на каналы ОП."""

    passed: bool = False
    not_subscribed: list[str] = field(default_factory=list)
    """Каналы, на которые пользователь не подписан."""

    check_failed: list[str] = field(default_factory=list)
    """Каналы, где бот не может проверить (нет прав админа и т.п.)."""

    @property
    def has_config_error(self) -> bool:
        return bool(self.check_failed)


async def check_user_op_subscription(
    bot: Bot,
    user_id: int,
    channels: list[dict[str, Any]],
) -> OpSubscriptionStatus:
    result = OpSubscriptionStatus()
    if not channels:
        result.passed = True
        return result

    for channel in channels:
        ref = channel['channel_ref']
        chat_id = _chat_id_for_api(ref)
        try:
            member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        except TelegramBadRequest as e:
            if _is_bot_access_error(e):
                logger.warning(f'ОП: бот не может проверить {chat_id}: {e}')
                result.check_failed.append(ref)
            else:
                logger.warning(f'ОП: ошибка проверки {chat_id} для {user_id}: {e}')
                result.not_subscribed.append(ref)
            continue

        ok = is_member_subscribed(member.status, getattr(member, 'is_member', None))
        if DEBUG:
            logger.debug(
                'ОП check: user_id={} channel={} status={} is_member={} ok={}',
                user_id,
                chat_id,
                member.status,
                getattr(member, 'is_member', None),
                ok,
            )
        if not ok:
            result.not_subscribed.append(ref)

    result.passed = not result.not_subscribed and not result.check_failed
    return result


async def user_subscribed_to_channels(
    bot: Bot,
    user_id: int,
    channels: list[dict[str, Any]],
) -> bool:
    """Совместимость: True только если подписан и проверка возможна."""
    status = await check_user_op_subscription(bot, user_id, channels)
    return status.passed


async def validate_bot_can_check_channels(
    bot: Bot,
    channels: list[dict[str, Any]],
) -> list[str]:
    """Проверяет, что бот — админ канала и может вызывать getChatMember."""
    errors: list[str] = []
    me = await bot.get_me()

    for channel in channels:
        ref = channel['channel_ref']
        chat_id = _chat_id_for_api(ref)
        label = ref
        try:
            await bot.get_chat(chat_id=chat_id)
        except TelegramBadRequest as e:
            errors.append(f'{label}: канал не найден ({e})')
            continue

        try:
            await bot.get_chat_member(chat_id=chat_id, user_id=me.id)
        except TelegramBadRequest as e:
            if _is_bot_access_error(e):
                errors.append(
                    f'{label}: добавьте бота <b>администратором</b> канала '
                    f'(иначе Telegram не даёт проверять подписку)'
                )
            else:
                errors.append(f'{label}: {e}')

    return errors
