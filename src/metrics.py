"""メトリクス収集 + TOP5更新パイプライン"""
import json
import sys

from src.clients.notion import NotionClient
from src.clients.threads import ThreadsClient


def run() -> None:
    """
    24時間以上前の未取得投稿のメトリクスを取得し、
    Notion を更新して TOP5 キャッシュを再構築する。
    """
    print("[metrics] 開始")
    notion = NotionClient()
    threads = ThreadsClient()

    # メトリクス未取得の投稿を取得
    pending = notion.get_posted_without_metrics()
    print(f"[metrics] 未取得投稿: {len(pending)}件")

    for item in pending:
        page_id = item["page_id"]
        post_id = item["threads_post_id"]
        if not post_id:
            continue
        try:
            metrics = threads.get_insights(post_id)
            notion.update_metrics(page_id, metrics)
            print(f"[metrics] 更新完了: post_id={post_id}, views={metrics['views']}, likes={metrics['likes']}")
        except Exception as e:
            print(f"[metrics] エラー: post_id={post_id} - {e}", file=sys.stderr)

    # TOP5 を再計算
    top5 = notion.get_top5_candidates()
    top5_page_ids = [r["page_id"] for r in top5]
    top5_texts = [r["text"] for r in top5 if r["text"]]

    notion.mark_top5(top5_page_ids)
    notion.set_config("top5_posts", json.dumps(top5_texts, ensure_ascii=False))

    print(f"[metrics] TOP5 更新完了: {len(top5_texts)}件")
    print("[metrics] 完了")


if __name__ == "__main__":
    run()
