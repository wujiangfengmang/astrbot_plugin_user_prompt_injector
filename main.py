"""AstrBot 用户提示词注入器。

根据 QQ 号自动向 LLM 系统提示词注入自定义规则，让 Bot 对不同用户展现不同态度。
配置由 AstrBot 管理（data/config/）。

指令：
- /tsc 导出规则 → 返回 JSON 数组
- /tsc 导入规则 + JSON → 以 QQ 号合并规则
"""

import json

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.provider import ProviderRequest
from astrbot.api.star import Context, Star

TEMPLATE_KEY = "user"


class UserPromptInjector(Star):
    """用户提示词注入器"""

    def __init__(self, context: Context, config: AstrBotConfig = None):
        super().__init__(context)
        self.config = config or {}

        users = self.config.get('users', [])
        if users:
            qqs = [str(u.get('target_qq', '')).strip() for u in users]
            logger.info(f'[提示词注入器] 已启动，共 {len(users)} 条规则，QQ: {", ".join(qqs)}')
        else:
            logger.info('[提示词注入器] 已启动，当前未配置任何规则')

    # ==================== 公共方法 ====================

    def _merge_users(self, incoming: list, existing: list) -> tuple:
        """以 QQ 号去重合并，返回 (merged_list, new_count, update_count)"""
        merged = {}
        for u in existing:
            qq = str(u.get('target_qq', '')).strip()
            if qq:
                u['target_qq'] = qq
                merged[qq] = u

        new_count = update_count = 0
        for item in incoming:
            if not isinstance(item, dict):
                continue
            qq = str(item.get('target_qq', '')).strip()
            if not qq:
                continue
            item['target_qq'] = qq
            item.setdefault('inject_text', '')
            item['__template_key'] = TEMPLATE_KEY
            if qq in merged:
                update_count += 1
            else:
                new_count += 1
            merged[qq] = item

        return list(merged.values()), new_count, update_count

    # ==================== 注入逻辑 ====================

    @filter.on_llm_request()
    async def inject_prompt(self, event: AstrMessageEvent, req: ProviderRequest):
        """匹配 QQ 后追加自定义规则到 system_prompt"""
        users = self.config.get('users', [])
        if not users:
            return
        sender = str(event.get_sender_id()).strip()
        for u in users:
            if str(u.get('target_qq', '')).strip() == sender:
                text = str(u.get('inject_text', '')).strip()
                if text:
                    logger.info(f'[提示词注入器] 匹配成功 QQ={sender}')
                    req.system_prompt += '\n' + text + '\n'
                else:
                    logger.warning(f'[提示词注入器] QQ={sender} 匹配但注入文本为空')
                return
        logger.debug(f'[提示词注入器] QQ={sender} 不在规则列表中')

    # ==================== 指令 ====================

    @filter.command_group("tsc")
    def tsc(self):
        pass

    @tsc.command("help")
    async def tsc_help(self, event: AstrMessageEvent):
        """/tsc help 显示帮助"""
        event.should_call_llm(False)
        yield event.plain_result(
            '[提示词注入器]\n'
            '/tsc 导出规则 → 导出当前规则\n'
            '/tsc 导入规则 [JSON] → 导入规则'
        )

    @tsc.command("导出规则")
    async def export_rules(self, event: AstrMessageEvent):
        """返回当前规则的 JSON 数组 /tsc 导出规则"""
        event.should_call_llm(False)
        users = self.config.get('users', [])
        clean = [{
            'target_qq': str(u.get('target_qq', '')).strip(),
            'inject_text': str(u.get('inject_text', ''))
        } for u in users]
        text = json.dumps(clean, ensure_ascii=False, indent=2)
        lines = text.split('\n')
        logger.info(f'[提示词注入器] 导出 {len(users)} 条规则')
        for i in range(0, len(lines), 20):
            yield event.plain_result('\n'.join(lines[i:i+20]))

    @tsc.command("导入规则")
    async def import_rules(self, event: AstrMessageEvent):
        """接收 JSON 数组，合并到当前规则 /tsc 导入规则"""
        event.should_call_llm(False)
        raw = event.message_str.strip()
        for prefix in ('/tsc 导入规则', 'tsc 导入规则'):
            if raw.startswith(prefix):
                raw = raw[len(prefix):].strip()
                break
        if not raw.startswith('['):
            yield event.plain_result(
                '[提示词注入器] 请传入 JSON 数组。示例：\n'
                '/tsc 导入规则 [{"target_qq":"123","inject_text":"规则内容"}]'
            )
            return
        try:
            items = json.loads(raw)
        except json.JSONDecodeError as e:
            yield event.plain_result(f'[提示词注入器] JSON 格式错误：{e}')
            return
        if not isinstance(items, list):
            yield event.plain_result('[提示词注入器] 需要 JSON 数组格式')
            return

        self.config['users'], new_count, update_count = self._merge_users(
            items, self.config.get('users', [])
        )
        try:
            self.config.save_config()
        except Exception as e:
            logger.error(f'[提示词注入器] 保存配置失败：{e}')
            yield event.plain_result('[提示词注入器] 保存配置失败，请检查磁盘空间')
            return
        total = len(self.config['users'])
        yield event.plain_result(f'[提示词注入器] 导入完成！新增 {new_count} 条，更新 {update_count} 条，当前共 {total} 条规则')
