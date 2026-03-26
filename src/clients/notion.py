"""Notion API クライアント"""
import os
from datetime import datetime, timezone
from notion_client import Client


class NotionClient:
    def __init__(self):
        self.client = Client(auth=os.environ["NOTION_API_KEY"])
        self.posts_db_id = os.environ["NOTION_POSTS_DB_ID"]
        self.config_db_id = os.environ["NOTION_CONFIG_DB_ID"]

    # ── Config DB ──────────────────────────────────────────

    def get_config(self, key: str) -> str | None:
        """Config DB から値を取得する"""
        results = self.client.databases.query(
            database_id=self.config_db_id,
            filter={"property": "key", "title": {"equals": key}},
        )
        pages = results.get("results", [])
        if not pages:
            return None
        prop = pages[0]["properties"].get("value", {})
        texts = prop.get("rich_text", [])
        return texts[0]["text"]["content"] if texts else None

    def set_config(self, key: str, value: str) -> None:
        """Config DB の値を作成または更新する"""
        results = self.client.databases.query(
            database_id=self.config_db_id,
            filter={"property": "key", "title": {"equals": key}},
        )
        pages = results.get("results", [])
        props = {
            "key": {"title": [{"text": {"content": key}}]},
            "value": {"rich_text": [{"text": {"content": value[:2000]}}]},
        }
        if pages:
            self.client.pages.update(page_id=pages[0]["id"], properties=props)
        else:
            self.client.pages.create(
                parent={"database_id": self.config_db_id},
                properties=props,
            )

    # ── Posts DB ───────────────────────────────────────────

    def record_post(
        self,
        text: str,
        topic: str,
        ai_score: float,
        threads_post_id: str,
        is_link_post: bool,
        regeneration_count: int,
    ) -> str:
        """投稿結果を Posts DB に記録し、page_id を返す"""
        title_excerpt = text[:40].replace("\n", " ")
        page = self.client.pages.create(
            parent={"database_id": self.posts_db_id},
            properties={
                "title": {"title": [{"text": {"content": title_excerpt}}]},
                "body": {"rich_text": [{"text": {"content": text[:2000]}}]},
                "status": {"select": {"name": "posted"}},
                "threads_post_id": {"rich_text": [{"text": {"content": threads_post_id}}]},
                "posted_at": {"date": {"start": datetime.now(timezone.utc).isoformat()}},
                "topic": {"rich_text": [{"text": {"content": topic}}]},
                "ai_score": {"number": round(ai_score, 2)},
                "is_link_post": {"checkbox": is_link_post},
                "regeneration_count": {"number": regeneration_count},
                "is_top5": {"checkbox": False},
            },
        )
        return page["id"]

    def record_failure(
        self,
        topic: str,
        ai_score: float,
        failure_reason: str,
        regeneration_count: int,
    ) -> None:
        """採点失敗した投稿を Posts DB に記録する"""
        self.client.pages.create(
            parent={"database_id": self.posts_db_id},
            properties={
                "title": {"title": [{"text": {"content": f"[FAILED] {topic[:35]}"}}]},
                "body": {"rich_text": [{"text": {"content": ""}}]},
                "status": {"select": {"name": "failed"}},
                "threads_post_id": {"rich_text": [{"text": {"content": ""}}]},
                "posted_at": {"date": {"start": datetime.now(timezone.utc).isoformat()}},
                "topic": {"rich_text": [{"text": {"content": topic}}]},
                "ai_score": {"number": round(ai_score, 2)},
                "failure_reason": {"rich_text": [{"text": {"content": failure_reason[:2000]}}]},
                "is_link_post": {"checkbox": False},
                "regeneration_count": {"number": regeneration_count},
                "is_top5": {"checkbox": False},
            },
        )

    def update_metrics(self, page_id: str, metrics: dict) -> None:
        """投稿のメトリクスを更新する"""
        views = metrics.get("views", 0)
        likes = metrics.get("likes", 0)
        replies = metrics.get("replies", 0)
        reposts = metrics.get("reposts", 0)
        engagement = (likes + replies + reposts) / views if views > 0 else 0.0
        self.client.pages.update(
            page_id=page_id,
            properties={
                "views": {"number": views},
                "likes": {"number": likes},
                "replies": {"number": replies},
                "reposts": {"number": reposts},
                "engagement_rate": {"number": round(engagement * 100, 2)},
            },
        )

    def get_recent_posts(self, limit: int = 30) -> list[str]:
        """直近 limit 件の投稿本文を返す（重複チェック用）"""
        results = self.client.databases.query(
            database_id=self.posts_db_id,
            filter={"property": "status", "select": {"equals": "posted"}},
            sorts=[{"property": "posted_at", "direction": "descending"}],
            page_size=limit,
        )
        texts = []
        for page in results.get("results", []):
            rich = page["properties"].get("body", {}).get("rich_text", [])
            if rich:
                texts.append(rich[0]["text"]["content"])
        return texts

    def get_posted_without_metrics(self) -> list[dict]:
        """メトリクス未取得（views=0）の投稿を返す"""
        results = self.client.databases.query(
            database_id=self.posts_db_id,
            filter={
                "and": [
                    {"property": "status", "select": {"equals": "posted"}},
                    {"property": "views", "number": {"equals": 0}},
                    {"property": "threads_post_id", "rich_text": {"is_not_empty": True}},
                ]
            },
            sorts=[{"property": "posted_at", "direction": "ascending"}],
        )
        rows = []
        for page in results.get("results", []):
            props = page["properties"]
            tid = props.get("threads_post_id", {}).get("rich_text", [])
            rows.append({
                "page_id": page["id"],
                "threads_post_id": tid[0]["text"]["content"] if tid else "",
            })
        return rows

    def get_top5_candidates(self) -> list[dict]:
        """エンゲージメント率上位5件を返す"""
        results = self.client.databases.query(
            database_id=self.posts_db_id,
            filter={
                "and": [
                    {"property": "status", "select": {"equals": "posted"}},
                    {"property": "views", "number": {"greater_than": 0}},
                ]
            },
            sorts=[{"property": "engagement_rate", "direction": "descending"}],
            page_size=5,
        )
        rows = []
        for page in results.get("results", []):
            props = page["properties"]
            body = props.get("body", {}).get("rich_text", [])
            er = props.get("engagement_rate", {}).get("number", 0)
            rows.append({
                "page_id": page["id"],
                "text": body[0]["text"]["content"] if body else "",
                "engagement_rate": er,
            })
        return rows

    def mark_top5(self, top5_page_ids: list[str]) -> None:
        """is_top5 フラグを更新する（全件リセット → 対象をTrue）"""
        # まず全件 False に
        all_posted = self.client.databases.query(
            database_id=self.posts_db_id,
            filter={"property": "is_top5", "checkbox": {"equals": True}},
        )
        for page in all_posted.get("results", []):
            self.client.pages.update(
                page_id=page["id"],
                properties={"is_top5": {"checkbox": False}},
            )
        # 対象を True に
        for page_id in top5_page_ids:
            self.client.pages.update(
                page_id=page_id,
                properties={"is_top5": {"checkbox": True}},
            )
