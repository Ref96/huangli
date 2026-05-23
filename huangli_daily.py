#!/usr/bin/env python3
"""
黄历日报 - 登录时自动抓取当日通书数据，存本地，推 macOS 通知
"""

import json
import shutil
import subprocess
import sys
import logging
from datetime import date
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE_DIR    = Path.home() / "Documents/ClaudeCode/Huangli"
DATA_DIR    = BASE_DIR / "data"
LOG_DIR     = BASE_DIR / "logs"
OBSIDIAN_DIR = Path("/Users/shawn/Documents/MAY/021 INBOX （未读）")

logging.basicConfig(
    filename=LOG_DIR / "huangli.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)


def today_str() -> str:
    return date.today().strftime("%Y-%m-%d")


def already_ran(date_str: str) -> bool:
    return (DATA_DIR / f"{date_str}.json").exists()


def fetch_huangli(date_str: str) -> dict:
    url = f"https://www.wannianli123.com/{date_str}.html"
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"}
    resp = requests.get(url, headers=headers, timeout=15)
    resp.encoding = "utf-8"
    soup = BeautifulSoup(resp.text, "html.parser")
    return parse_huangli(soup, date_str)


def _img_siblings_text(img_tag) -> list[str]:
    """提取 img 所在 field-name div 的兄弟 field-value div 中的 span 文本"""
    field_name = img_tag.parent  # div.field-name
    field = field_name.parent    # div.field
    value_div = field.find("div", class_="field-value")
    if value_div:
        return [s.get_text(strip=True) for s in value_div.find_all("span") if s.get_text(strip=True)]
    return []


def parse_huangli(soup: BeautifulSoup, date_str: str) -> dict:
    import re
    data: dict = {"date": date_str}
    text = soup.get_text(" ", strip=True)

    # 宜
    yi_img = soup.find("img", src=lambda s: s and "yi.png" in s)
    data["yi"] = _img_siblings_text(yi_img) if yi_img else []

    # 忌
    ji_img = soup.find("img", src=lambda s: s and "ji.png" in s)
    data["ji"] = _img_siblings_text(ji_img) if ji_img else []

    # 彭祖百忌（去重）
    pz_match = list(dict.fromkeys(re.findall(r"[甲乙丙丁戊己庚辛壬癸]不\S{3,10}", text)))
    data["pengzu"] = pz_match[:2] if pz_match else []

    # 冲煞
    chong_match = re.search(r"冲([^\s（(，。]{1,4})[（(][^)）]+[)）]煞([东西南北])", text)
    data["chong"] = f"冲{chong_match.group(1)} 煞{chong_match.group(2)}" if chong_match else ""

    # 农历
    nongli_match = re.search(r"农历[^\s，。]{4,10}", text)
    data["nongli"] = nongli_match.group(0) if nongli_match else ""

    # 干支
    ganzhi_match = re.search(
        r"[甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥]年\s*"
        r"[甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥]月\s*"
        r"[甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥]日",
        text,
    )
    data["ganzhi"] = ganzhi_match.group(0).replace(" ", "") if ganzhi_match else ""

    # 吉神（table: td.th "吉神宜趋" → 兄弟 td > span）
    ji_td = soup.find("td", class_="th", string=lambda t: t and "吉神宜趋" in t)
    if ji_td:
        val_td = ji_td.find_next_sibling("td")
        data["ji_shen"] = " ".join(s.get_text(strip=True) for s in val_td.find_all("span")) if val_td else ""
    else:
        data["ji_shen"] = ""

    # 凶煞（table: td.th "凶煞宜忌" → 兄弟 td > span）
    xiong_td = soup.find("td", class_="th", string=lambda t: t and "凶煞宜忌" in t)
    if xiong_td:
        val_td = xiong_td.find_next_sibling("td")
        data["xiong_sha"] = " ".join(s.get_text(strip=True) for s in val_td.find_all("span")) if val_td else ""
    else:
        data["xiong_sha"] = ""

    return data


def format_md(data: dict) -> str:
    yi  = " ".join(data.get("yi", []))
    ji  = " ".join(data.get("ji", []))
    pz  = "  \n".join(data.get("pengzu", []))
    lines = [
        f"# 通书 {data['date']}",
        "",
        f"**农历**：{data.get('nongli', '')}　**干支**：{data.get('ganzhi', '')}",
        "",
        f"**宜**：{yi}",
        "",
        f"**忌**：{ji}",
        "",
        f"**彭祖百忌**：{pz}",
        "",
        f"**冲煞**：{data.get('chong', '')}",
        "",
        f"**吉神**：{data.get('ji_shen', '')}",
        "",
        f"**凶煞**：{data.get('xiong_sha', '')}",
    ]
    return "\n".join(lines)


def send_notification(date_str: str, data: dict) -> None:
    yi_short = " ".join(data.get("yi", [])[:4])
    ji_short = " ".join(data.get("ji", [])[:3])
    body = f"宜：{yi_short}\n忌：{ji_short}"
    if data.get("chong"):
        body += f"\n{data['chong']}"
    nongli = data.get("nongli", "")
    script = f'display notification "{body}" with title "通书 {date_str}" subtitle "{nongli}"'
    subprocess.run(["osascript", "-e", script], capture_output=True)


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    date_str = today_str()

    if already_ran(date_str):
        log.info("今日(%s)已生成，跳过", date_str)
        return

    log.info("开始抓取 %s 黄历", date_str)
    try:
        data = fetch_huangli(date_str)
    except Exception as e:
        log.error("抓取失败: %s", e)
        send_notification(date_str, {"yi": ["（获取失败）"], "ji": [], "nongli": ""})
        sys.exit(1)

    json_path = DATA_DIR / f"{date_str}.json"
    md_path   = DATA_DIR / f"通书 {date_str}.md"

    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(format_md(data), encoding="utf-8")

    log.info("已保存 %s", date_str)

    obsidian_path = OBSIDIAN_DIR / f"通书 {date_str}.md"
    try:
        shutil.copy2(md_path, obsidian_path)
        log.info("已同步 Obsidian: %s", obsidian_path)
    except Exception as e:
        log.error("同步 Obsidian 失败: %s", e)

    send_notification(date_str, data)


if __name__ == "__main__":
    main()
