"""Claude API クライアント"""
import os
import anthropic


class ClaudeClient:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    def generate(self, system: str, prompt: str, max_tokens: int = 1024) -> str:
        """生成系の呼び出し（Sonnet）"""
        msg = self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text.strip()

    def score(self, system: str, prompt: str, max_tokens: int = 512) -> str:
        """採点系の呼び出し（Haiku - 軽量で十分）"""
        msg = self.client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text.strip()
