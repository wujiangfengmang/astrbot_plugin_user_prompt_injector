from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.provider import ProviderRequest
from astrbot.api.star import Context, Star
from astrbot.api import logger, AstrBotConfig


class UserPromptInjector(Star):
    def __init__(self, context: Context, config: AstrBotConfig = None):
        super().__init__(context)
        self.config = config or {}
        users = self.config.get('users', [])
        count = len(users)
        if count > 0:
            qqs = [str(u.get('target_qq', '')).strip() for u in users]
            logger.info(f'[提示词注入器] 已启动，共加载 {count} 条规则，目标QQ: {", ".join(qqs)}')
        else:
            logger.info('[提示词注入器] 已启动，当前未配置任何规则')

    @filter.on_llm_request()
    async def inject_prompt(self, event: AstrMessageEvent, req: ProviderRequest):
        users = self.config.get('users', [])
        if not users:
            return
        sender = str(event.get_sender_id()).strip()
        for i, user in enumerate(users):
            qq = str(user.get('target_qq', '')).strip()
            if sender == qq:
                text = user.get('inject_text', '').strip()
                if text:
                    logger.info(f'[提示词注入器] 匹配成功！规则 #{i+1}  QQ={qq}  → 已向系统提示词注入 {len(text)} 个字符的规则')
                    req.system_prompt += '\n' + text + '\n'
                    return
                else:
                    logger.warning(f'[提示词注入器] 匹配到用户 QQ={qq}，但该规则的注入文本为空，已跳过')
                    return
        logger.info(f'[提示词注入器] 消息来自 QQ={sender}，不在规则列表中，正常处理')
