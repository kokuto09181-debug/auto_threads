"""重複チェックユーティリティ（Jaccard係数ベース）"""


def _tokenize(text: str) -> set[str]:
    """テキストを文字n-gram（bigram）のセットに変換する"""
    text = text.replace(" ", "").replace("\n", "")
    return {text[i:i+2] for i in range(len(text) - 1)}


def jaccard_similarity(a: str, b: str) -> float:
    """2つのテキストのJaccard係数を返す（0.0〜1.0）"""
    set_a = _tokenize(a)
    set_b = _tokenize(b)
    if not set_a or not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union


def is_duplicate(new_text: str, recent_texts: list[str], threshold: float = 0.7) -> bool:
    """過去の投稿リストと比較して重複していたら True を返す"""
    for past in recent_texts:
        if jaccard_similarity(new_text, past) >= threshold:
            return True
    return False
