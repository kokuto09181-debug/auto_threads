"""投稿採点エージェント"""
import json
import re
from dataclasses import dataclass
from src.clients.claude import ClaudeClient

_SYSTEM = """\
あなたはThreads投稿の品質審査員です。
以下の7項目それぞれを0〜10点で採点し、JSON形式で返してください。

採点基準:
1. 自然さ        - 人間が書いたような自然な語り口か（AIっぽくないか）
2. 具体性        - 抽象論でなく、具体的な体験・場面・数字があるか
3. 感情移入しやすさ - 読者が「わかる」「自分のことみたい」と思えるか
4. ペルソナ一致度  - キャラ設定の口調・価値観とブレていないか
5. テンポ感      - 読みやすい文章のリズム・改行の使い方か
6. 体験語り感    - 「自分の経験から」という感触が出ているか
7. 業者臭さのなさ  - 宣伝・セールス感が皆無か（完全にNGなら0点）

出力形式（JSON以外は一切出力しない）:
{
  "scores": {
    "naturalness": 8,
    "specificity": 7,
    "empathy": 9,
    "persona_match": 8,
    "rhythm": 7,
    "experiential": 8,
    "non_salesy": 9
  },
  "average": 8.0,
  "feedback": "改善点があれば具体的に1〜2行で。なければ空文字"
}
"""


@dataclass
class ScoreResult:
    average: float
    scores: dict
    feedback: str
    passed: bool


def score_post(text: str, threshold: float = 7.0) -> ScoreResult:
    """投稿を採点して ScoreResult を返す"""
    client = ClaudeClient()
    raw = client.score(
        system=_SYSTEM,
        prompt=f"以下の投稿を採点してください:\n\n{text}",
    )

    # JSONを抽出（余分なテキストがついていても対応）
    json_match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not json_match:
        return ScoreResult(average=0.0, scores={}, feedback=raw, passed=False)

    try:
        data = json.loads(json_match.group())
        average = float(data.get("average", 0))
        scores = data.get("scores", {})
        feedback = data.get("feedback", "")
        return ScoreResult(
            average=average,
            scores=scores,
            feedback=feedback,
            passed=average >= threshold,
        )
    except (json.JSONDecodeError, ValueError):
        return ScoreResult(average=0.0, scores={}, feedback=raw, passed=False)
