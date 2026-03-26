"""投稿時間ランダム化ユーティリティ"""
import random
import time


def apply_jitter(max_minutes: int = 30) -> None:
    """0〜max_minutes 分のランダムなスリープを実行する"""
    seconds = random.randint(0, max_minutes * 60)
    print(f"[jitter] {seconds // 60}分{seconds % 60}秒 待機します...")
    time.sleep(seconds)
