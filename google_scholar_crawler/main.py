from scholarly import scholarly, ProxyGenerator
import json
from datetime import datetime
import os
from scholarly._proxy_generator import MaxTriesExceededException
import time


def get_author_with_retry(scholar_id, max_attempts=3):
    strategies = [
        ("直接连接（无代理）", None),
        ("免费代理", "free"),
    ]

    for attempt in range(max_attempts):
        for strategy_name, proxy_type in strategies:
            try:
                print(f"尝试策略: {strategy_name} (第 {attempt + 1} 次)...")
                scholarly.set_timeout(30)
                scholarly.set_retries(5)

                if proxy_type == "free":
                    pg = ProxyGenerator()
                    pg.FreeProxies()
                    scholarly.use_proxy(pg)
                else:
                    scholarly.use_proxy(None)

                author = scholarly.search_author_id(scholar_id)
                print("正在填充作者详细信息...")
                scholarly.fill(author, sections=["basics", "indices", "counts", "publications"])
                return author
            except (MaxTriesExceededException, AttributeError, Exception) as e:
                print(f"  {strategy_name} 失败: {e}")
                time.sleep(5)
                continue

    raise Exception("所有策略均无法获取作者数据，Google Scholar 可能临时屏蔽了请求。")


try:
    author = get_author_with_retry(os.environ["GOOGLE_SCHOLAR_ID"])
except Exception as e:
    print(f"发生异常: {e}")
    exit(1)

name = author["name"]
author["updated"] = str(datetime.now())
author["publications"] = {v["author_pub_id"]: v for v in author["publications"]}
print(json.dumps(author, indent=2))

print("正在创建结果目录...")
os.makedirs("results", exist_ok=True)

print("正在保存作者数据...")
with open("results/gs_data.json", "w") as outfile:
    json.dump(author, outfile, ensure_ascii=False)

print("正在生成 Shields.io 数据...")
shieldio_data = {
    "schemaVersion": 1,
    "label": "citations",
    "message": f"{author.get('citedby', 0)}",
}

print("正在保存 Shields.io 数据...")
with open("results/gs_data_shieldsio.json", "w") as outfile:
    json.dump(shieldio_data, outfile, ensure_ascii=False)

print("数据处理完成。")
