"""週次トピックシード自動生成"""
import yaml
from pathlib import Path

from src.agents.copywriter import generate_weekly_topics
from src.clients.notion import NotionClient


def run(account_name: str = "default") -> None:
    """翌週分21トピックを生成して Notion Config に書き込む"""
    print("[topic_seeder] 開始")

    cfg_path = Path(__file__).parent.parent / "config" / "accounts" / f"{account_name}.yaml"
    with open(cfg_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    persona: str = cfg["persona"]
    topics = generate_weekly_topics(persona, count=21)

    print(f"[topic_seeder] 生成されたトピック: {len(topics)}件")
    for i, t in enumerate(topics, 1):
        print(f"  {i:2}. {t}")

    notion = NotionClient()
    notion.set_config("weekly_topics", "\n".join(topics))
    print("[topic_seeder] Notion に書き込み完了")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--account", default="default")
    args = parser.parse_args()
    run(account_name=args.account)
