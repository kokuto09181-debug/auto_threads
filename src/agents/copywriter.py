"""投稿文生成エージェント"""
from src.clients.claude import ClaudeClient

_SYSTEM_TEMPLATE = """\
あなたは以下のペルソナを持つThreadsユーザーとして投稿文を書きます。

{persona}

## 投稿ルール
- 文字数: {min_len}〜{max_len}文字
- テンプレ的な書き出しは絶対に使わない（「ここだけの話」「これを知らないと損」等はNG）
- その日ふとした感情や体験から自然に書き始める
- 具体的なエピソード・数字・場面を入れる
- 最後に読者が「わかる」「コメントしたくなる」と感じる余韻を残す
- Threadsの投稿として自然な改行・テンポを意識する
- 業者っぽさ・宣伝っぽさは一切NG

## 過去にエンゲージメントが高かった投稿（参考）
{top5_examples}
"""

_LINK_SUFFIX = """

## 追加指示
投稿本文の末尾に、以下の文言を自然な流れで一行追加してください。
ただし、宣伝っぽくならないよう本文の文脈に合わせて馴染ませること。
---
{link_text}
---
"""


def generate_post(
    persona: str,
    topic: str,
    top5_texts: list[str],
    min_len: int,
    max_len: int,
    is_link_post: bool = False,
    link_text: str = "",
) -> str:
    """投稿文を生成して返す"""
    client = ClaudeClient()

    top5_block = "\n\n".join(
        [f"例{i+1}:\n{t}" for i, t in enumerate(top5_texts)]
    ) if top5_texts else "（まだデータがありません。ペルソナに忠実に書いてください）"

    system = _SYSTEM_TEMPLATE.format(
        persona=persona.strip(),
        min_len=min_len,
        max_len=max_len,
        top5_examples=top5_block,
    )

    if is_link_post and link_text:
        system += _LINK_SUFFIX.format(link_text=link_text)

    prompt = f"今日のトピック: {topic}\n\nこのトピックについて、投稿文を1本書いてください。投稿文のみを出力し、前置きや説明は不要です。"

    return client.generate(system=system, prompt=prompt, max_tokens=1200)


def generate_weekly_topics(persona: str, count: int = 21) -> list[str]:
    """翌週分のトピックシードを生成して返す"""
    client = ClaudeClient()

    system = f"""\
あなたは以下のペルソナを持つThreadsアカウントの運営者です。

{persona}

翌週の投稿テーマを考えてください。
恋愛・感情・人間関係に関する、共感を呼びやすいテーマを生成します。
"""
    prompt = f"""\
翌週の投稿トピックを{count}個生成してください。
各トピックは1行で、具体的なシチュエーションや感情を含む短い説明にしてください。
例：「好きな人に気持ちを伝えられなかった日の夜の感情」

{count}個のトピックを番号なし・箇条書きなしで、1行1トピックで出力してください。
"""
    raw = client.generate(system=system, prompt=prompt, max_tokens=1500)
    topics = [line.strip() for line in raw.splitlines() if line.strip()]
    return topics[:count]
