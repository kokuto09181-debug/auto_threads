"""Threads アクセストークンの自動更新"""
import base64
import json
import os
import sys

import requests

from src.clients.threads import ThreadsClient


def _update_github_secret(repo: str, secret_name: str, secret_value: str, gh_token: str) -> None:
    """GitHub Actions Secret を API 経由で更新する"""
    headers = {
        "Authorization": f"Bearer {gh_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    # リポジトリの公開鍵を取得
    key_resp = requests.get(
        f"https://api.github.com/repos/{repo}/actions/secrets/public-key",
        headers=headers,
        timeout=10,
    )
    key_resp.raise_for_status()
    key_data = key_resp.json()

    # libsodium で暗号化（PyNaclが不要なシンプルな実装）
    from base64 import b64encode
    try:
        from nacl import encoding, public
        pub_key = public.PublicKey(key_data["key"].encode(), encoding.Base64Encoder)
        sealed_box = public.SealedBox(pub_key)
        encrypted = b64encode(sealed_box.encrypt(secret_value.encode())).decode()
    except ImportError:
        print("[token_refresh] PyNaCl が未インストールです。pip install PyNaCl を実行してください。", file=sys.stderr)
        sys.exit(1)

    # Secret を更新
    put_resp = requests.put(
        f"https://api.github.com/repos/{repo}/actions/secrets/{secret_name}",
        headers=headers,
        json={"encrypted_value": encrypted, "key_id": key_data["key_id"]},
        timeout=10,
    )
    put_resp.raise_for_status()


def run() -> None:
    print("[token_refresh] 開始")
    client = ThreadsClient()
    new_token = client.refresh_token()
    print("[token_refresh] トークン更新成功")

    gh_token = os.environ.get("GH_TOKEN", "")
    repo = os.environ.get("GH_REPO", "")

    if gh_token and repo:
        _update_github_secret(repo, "THREADS_ACCESS_TOKEN", new_token, gh_token)
        print(f"[token_refresh] GitHub Secret を更新しました: {repo}")
    else:
        print("[token_refresh] GH_TOKEN / GH_REPO が未設定のため Secret 更新をスキップ")
        print(f"[token_refresh] 新しいトークン（手動で更新してください）: {new_token[:20]}...")

    print("[token_refresh] 完了")


if __name__ == "__main__":
    run()
