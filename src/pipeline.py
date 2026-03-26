"""メイン投稿パイプライン"""
import json
import os
import sys
import yaml
from pathlib import Path

from src.agents.copywriter import generate_post
from src.agents.scorer import score_post
from src.clients.notion import NotionClient
from src.clients.threads import ThreadsClient
from src.utils.dedup import is_duplicate
from src.utils.jitter import apply_jitter

LINK_POST_INTERVAL = 5  # 5投稿に1回リンク付き投稿


def _load_account_config(account_name: str) -> dict:
    path = Path(__file__).parent.parent / "config" / "accounts" / f"{account_name}.yaml"
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _get_next_topic(topics_raw: str, post_count: int) -> str:
    """週次トピックリストから今回分を取得する"""
    topics = [t.strip() for t in topics_raw.splitlines() if t.strip()]
    if not topics:
        return "今日ふと感じた、人間関係についての気づき"
    return topics[post_count % len(topics)]


def run(account_name: str = "default", dry_run: bool = False) -> None:
    """
    投稿パイプラインを実行する。
    dry_run=True の場合は Threads への実際の投稿をスキップする。
    """
    print(f"[pipeline] 開始: account={account_name}, dry_run={dry_run}")

    # ジッター（定時起動のパターン化を防ぐ）
    if not dry_run:
        apply_jitter(max_minutes=30)

    # 設定読み込み
    cfg = _load_account_config(account_name)
    persona: str = cfg["persona"]
    min_len: int = cfg["posting_rules"]["min_length"]
    max_len: int = cfg["posting_rules"]["max_length"]
    threshold: float = cfg["scoring_threshold"]
    max_regen: int = cfg["max_regeneration"]
    dedup_window: int = cfg["dedup_window"]
    dedup_threshold: float = cfg["dedup_threshold"]
    link_text_template: str = cfg["posting_rules"]["link_text_suffix"]

    # Notion から動的設定を取得
    notion = NotionClient()
    weekly_topics_raw = notion.get_config("weekly_topics") or ""
    top5_raw = notion.get_config("top5_posts") or "[]"
    post_count = int(notion.get_config("post_count") or "0")
    affiliate_url = notion.get_config("affiliate_url") or ""

    top5_texts: list[str] = json.loads(top5_raw) if top5_raw.startswith("[") else []
    topic = _get_next_topic(weekly_topics_raw, post_count)
    is_link_post = (post_count + 1) % LINK_POST_INTERVAL == 0
    link_text = link_text_template.replace("{url}", affiliate_url) if is_link_post and affiliate_url else ""

    print(f"[pipeline] topic='{topic}', is_link_post={is_link_post}, post_count={post_count+1}")

    # 重複チェック用に過去投稿を取得
    recent_texts = notion.get_recent_posts(limit=dedup_window)

    # 生成 → 採点ループ（最大 max_regen 回）
    final_text = None
    final_score = None
    last_feedback = ""

    for attempt in range(max_regen):
        print(f"[pipeline] 生成試行 {attempt+1}/{max_regen}")

        text = generate_post(
            persona=persona,
            topic=topic,
            top5_texts=top5_texts,
            min_len=min_len,
            max_len=max_len,
            is_link_post=is_link_post,
            link_text=link_text,
        )

        result = score_post(text, threshold=threshold)
        print(f"[pipeline] 採点: {result.average:.1f}点 (通過: {result.passed})")
        last_feedback = result.feedback

        if not result.passed:
            print(f"[pipeline] 不合格 - {result.feedback}")
            continue

        if is_duplicate(text, recent_texts, dedup_threshold):
            print("[pipeline] 重複検出 - 再生成します")
            last_feedback = "重複投稿と判定されました"
            continue

        final_text = text
        final_score = result
        break

    # 全試行失敗
    if final_text is None:
        print(f"[pipeline] {max_regen}回すべて失敗。記録してスキップします。")
        notion.record_failure(
            topic=topic,
            ai_score=0.0,
            failure_reason=last_feedback,
            regeneration_count=max_regen,
        )
        sys.exit(0)

    # 投稿実行
    if dry_run:
        print(f"[pipeline][dry_run] 投稿内容:\n{'='*40}\n{final_text}\n{'='*40}")
        print(f"[pipeline][dry_run] スコア: {final_score.average:.1f}")
        return

    threads = ThreadsClient()
    remaining = threads.check_limit()
    if remaining <= 0:
        print("[pipeline] 本日の投稿上限に達しました。スキップします。")
        sys.exit(0)

    post_id = threads.post(final_text)
    print(f"[pipeline] 投稿完了: post_id={post_id}")

    # Notion に記録
    notion.record_post(
        text=final_text,
        topic=topic,
        ai_score=final_score.average,
        threads_post_id=post_id,
        is_link_post=is_link_post,
        regeneration_count=max_regen - (max_regen - 1),  # 実際の試行回数
    )

    # 投稿カウンターを更新
    notion.set_config("post_count", str(post_count + 1))

    print("[pipeline] 完了")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--account", default="default")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(account_name=args.account, dry_run=args.dry_run)
