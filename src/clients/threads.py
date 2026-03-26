"""Threads API クライアント"""
import os
import time
import requests


THREADS_API_BASE = "https://graph.threads.net/v1.0"


class ThreadsClient:
    def __init__(self):
        self.access_token = os.environ["THREADS_ACCESS_TOKEN"]
        self.user_id = os.environ["THREADS_USER_ID"]

    def _get(self, path: str, params: dict = None) -> dict:
        url = f"{THREADS_API_BASE}/{path}"
        p = {"access_token": self.access_token, **(params or {})}
        resp = requests.get(url, params=p, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, data: dict = None) -> dict:
        url = f"{THREADS_API_BASE}/{path}"
        d = {"access_token": self.access_token, **(data or {})}
        resp = requests.post(url, data=d, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def check_limit(self) -> int:
        """残り投稿可能数を返す"""
        result = self._get(
            f"{self.user_id}/threads_publishing_limit",
            {"fields": "config,quota_usage"},
        )
        items = result.get("data", [])
        if not items:
            return 250
        quota = items[0].get("quota_usage", 0)
        limit = items[0].get("config", {}).get("quota_total", 250)
        return limit - quota

    def post(self, text: str) -> str:
        """テキスト投稿を作成・公開し、post_id を返す"""
        # Step 1: メディアコンテナ作成
        container = self._post(
            f"{self.user_id}/threads",
            {"media_type": "TEXT", "text": text},
        )
        container_id = container["id"]

        # Threads API の推奨: コンテナ作成後に少し待つ
        time.sleep(3)

        # Step 2: 公開
        result = self._post(
            f"{self.user_id}/threads_publish",
            {"creation_id": container_id},
        )
        return result["id"]

    def get_insights(self, post_id: str) -> dict:
        """投稿のメトリクスを取得する"""
        result = self._get(
            f"{post_id}/insights",
            {"metric": "views,likes,replies,reposts,quotes"},
        )
        metrics = {}
        for item in result.get("data", []):
            metrics[item["name"]] = item.get("values", [{}])[0].get("value", 0)
        return {
            "views": metrics.get("views", 0),
            "likes": metrics.get("likes", 0),
            "replies": metrics.get("replies", 0),
            "reposts": metrics.get("reposts", 0),
            "quotes": metrics.get("quotes", 0),
        }

    def refresh_token(self) -> str:
        """長期トークンを更新して新しいトークンを返す"""
        resp = requests.get(
            f"{THREADS_API_BASE}/refresh_access_token",
            params={
                "grant_type": "th_refresh_token",
                "access_token": self.access_token,
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["access_token"]
