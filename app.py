
import os
import json
import re
from pathlib import Path

import streamlit as st

try:
    from openai import OpenAI
except Exception:
    OpenAI = None

BASE_DIR = Path(__file__).parent

with open(BASE_DIR / "knowledge_base.json", "r", encoding="utf-8") as f:
    KB = json.load(f)

with open(BASE_DIR / "sample_alerts.json", "r", encoding="utf-8") as f:
    SAMPLE_ALERTS = json.load(f)

st.set_page_config(
    page_title="AccessWeather｜天气可达",
    page_icon="☔",
    layout="centered",
)

st.title("AccessWeather｜天气可达")
st.caption("面向残障女性的 AI 极端天气准备信息助手 · MVP")
st.info(
    "这是灾前准备与信息理解工具，不替代官方预警、专业应急指令或个人判断。"
)

with st.expander("这个原型如何工作"):
    st.markdown(
        """ 1. 用户粘贴一条**官方天气预警**，并描述自己当天的实际需求。 2. 系统先从经人工整理的**官方信息与残障女性生活经验**中检索相关内容。 3. AI 只基于检索到的材料，生成一张**极端天气准备卡**。 4. 找不到可靠依据的内容必须进入“待确认”，而不是由模型补写。 """
    )

st.subheader("1｜天气信息")

alert_mode = st.radio(
    "天气预警来源",
    ["使用演示预警", "粘贴官方预警"],
    horizontal=True,
)

if alert_mode == "使用演示预警":
    sample_name = st.selectbox(
        "选择演示场景",
        list(SAMPLE_ALERTS.keys())
    )
    alert_text = SAMPLE_ALERTS[sample_name]["text"]
    st.text_area(
        "预警文本（演示用，非实时）",
        value=alert_text,
        height=150,
        disabled=True,
    )
    alert_source = SAMPLE_ALERTS[sample_name]["source"]
else:
    alert_text = st.text_area(
        "粘贴官方天气预警文本",
        placeholder="请粘贴气象部门、应急部门或其他权威来源发布的预警原文。",
        height=150,
    )
    alert_source = st.text_input(
        "来源链接或来源名称（建议填写）",
        placeholder="例如：北京市气象台 / 官方网页链接",
    )

st.subheader("2｜今天的我")

preset = st.selectbox(
    "可从一个示例开始，也可以自行修改",
    [
        "电动轮椅用户｜必须外出｜公共交通",
        "助听器使用者｜必须通勤｜独自出行",
        "手动轮椅用户｜可以调整行程",
        "自定义",
    ],
)

preset_map = {
    "电动轮椅用户｜必须外出｜公共交通":
        "我使用电动轮椅，今天必须外出去医院，主要乘坐公交和地铁，独自出行。我的轮椅不适合长时间淋雨，我也需要确认途中是否有可以避雨和充电的地方。",
    "助听器使用者｜必须通勤｜独自出行":
        "我使用助听器，今天必须通勤，主要乘坐公共交通，独自出行。我担心设备受潮，也希望提前准备在嘈杂暴雨环境下的备用沟通方式。",
    "手动轮椅用户｜可以调整行程":
        "我使用手动轮椅，今天原本有一次非紧急外出，可以调整时间。我比较在意湿滑路面、轮椅淋湿后的处理以及换乘站的无障碍情况。",
    "自定义": "",
}

user_needs = st.text_area(
    "请用自己的话说明：今天要做什么？怎么出行？有哪些无障碍需求或辅助器具需要考虑？",
    value=preset_map[preset],
    height=150,
)

st.caption("系统不会仅根据“轮椅使用者”“听障者”等身份标签推断个人需求。")

def tokenize(text):
    text = text.lower()
    zh = re.findall(r"[\u4e00-\u9fff]{1,4}", text)
    en = re.findall(r"[a-z0-9_-]+", text)
    return set(zh + en)

def retrieve(alert, needs, top_k=6):
    query = f"{alert}\n{needs}"
    qtokens = tokenize(query)
    scored = []
    for item in KB:
        hay = " ".join([
            item.get("title", ""),
            item.get("content", ""),
            " ".join(item.get("tags", [])),
        ])
        htokens = tokenize(hay)
        overlap = len(qtokens & htokens)
        # Explicit tag hits get extra weight.
        bonus = 0
        for tag in item.get("tags", []):
            if tag.lower() in query.lower():
                bonus += 3
        score = overlap + bonus
        if score > 0:
            scored.append((score, item))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [x[1] for x in scored[:top_k]]

def fallback_card(retrieved):
    checks = []
    confirmations = []
    relations = []

    for item in retrieved:
        if item["type"] == "community":
            relations.append({
                "text": item["content"],
                "sources": [item["id"]],
            })
        else:
            checks.append({
                "text": item["content"],
                "sources": [item["id"]],
            })

    if not checks:
        checks = [{
            "text": "根据你粘贴的官方预警，先确认预警有效时间、影响区域和官方安全指引。",
            "sources": ["USER_ALERT"],
        }]

    confirmations.extend([
        {"text": "你计划使用的公交、地铁或无障碍设施现在是否正常运行？", "sources": ["USER_ALERT"]},
        {"text": "目的地和途中是否有可避雨、休息或给必要设备充电的空间？", "sources": []},
    ])

    return {
        "relation": relations[:3] or [{
            "text": "当前演示模式只整理检索到的经验，不会替你判断是否应该出门。",
            "sources": [],
        }],
        "checks": checks[:4],
        "confirm": confirmations[:4],
        "boundary": [
            "本卡片用于帮助整理准备事项，不替代官方预警、专业应急指令或个人判断。",
            "实时交通、积水、停运和撤离信息必须向权威来源再次确认。",
            "未能从知识库找到可靠依据的事项应标记为“待确认”。",
        ],
    }

SYSTEM_PROMPT = """ 你是 AccessWeather 的信息整理模块。你的任务不是给灾害决策下结论，而是把官方天气预警、 用户本人描述的实际需求，以及检索到的可信材料，整理成一张“极端天气准备卡”。 必须遵守： 1. 不判断用户是否应该出门、撤离或留在原地。 2. 不自行升级或发布天气预警。 3. 不编造实时交通、积水、停运、设施开放等事实。 4. 不根据残障标签推断用户没有明确表达的个人需求。 5. 只使用给你的检索材料作为事实依据；没有依据的内容放入“待确认”。 6. 区分：用户提供的信息、官方信息、社区经验、待确认信息。 7. 输出简洁、具体、可行动，但不制造恐慌。 8. 返回严格 JSON，不要输出 JSON 之外的文字。 JSON 结构： { "relation":[{"text":"...", "sources":["K1"]}], "checks":[{"text":"...", "sources":["K2"]}], "confirm":[{"text":"...", "sources":["K3"]}], "boundary":["..."] } """

def call_deepseek(alert, source, needs, retrieved):
    api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not api_key or OpenAI is None:
        return None, "未配置 DEEPSEEK_API_KEY，当前使用可交互的演示模式。"

    client = OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com",
    )

    context = "\n\n".join(
        [
            f"[{x['id']}] 类型={x['type']}；标题={x['title']}；内容={x['content']}；来源={x['source']}"
            for x in retrieved
        ]
    )

    user_prompt = f""" 【天气预警】 {alert} 【预警来源】 {source or "用户未填写"} 【用户本人描述】 {needs} 【检索材料】 {context} 请生成极端天气准备卡。所有事实性陈述都必须能够对应上述材料；需要实时核实的内容放入 confirm。 """

    try:
        resp = client.chat.completions.create(
            model="deepseek-flash",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            stream=False,
        )
        raw = resp.choices[0].message.content
        return json.loads(raw), "AI 模式：DeepSeek API + 本地检索知识库"
    except Exception as e:
        return None, f"AI 调用失败，已切换演示模式。错误：{e}"

def source_badge(source_id):
    if source_id == "USER_ALERT":
        return "用户粘贴的官方预警"
    for item in KB:
        if item["id"] == source_id:
            return f"{source_id} · {item['type_label']} · {item['source_short']}"
    return source_id

generate = st.button("生成我的极端天气准备卡", type="primary", use_container_width=True)

if generate:
    if not alert_text.strip():
        st.error("请先填写天气预警。")
        st.stop()
    if not user_needs.strip():
        st.error("请先描述今天的实际需求。")
        st.stop()

    retrieved = retrieve(alert_text, user_needs)

    with st.spinner("正在匹配天气信息与个人需求……"):
        card, mode_msg = call_deepseek(alert_text, alert_source, user_needs, retrieved)
        if card is None:
            card = fallback_card(retrieved)

    st.divider()
    st.subheader("我的极端天气准备卡")
    st.caption(mode_msg)

    st.markdown("#### 这条天气信息可能与我有什么关系")
    for x in card.get("relation", []):
        st.write("• " + x.get("text", ""))
        if x.get("sources"):
            st.caption("来源：" + "；".join(source_badge(s) for s in x["sources"]))

    st.markdown("#### 出发前可以检查")
    for x in card.get("checks", []):
        st.checkbox(x.get("text", ""), key=f"check_{hash(x.get('text',''))}")
        if x.get("sources"):
            st.caption("依据：" + "；".join(source_badge(s) for s in x["sources"]))

    st.markdown("#### 还需要进一步确认")
    for x in card.get("confirm", []):
        st.write("❓ " + x.get("text", ""))
        if x.get("sources"):
            st.caption("相关来源：" + "；".join(source_badge(s) for s in x["sources"]))

    st.markdown("#### 信息来源与使用边界")
    for x in card.get("boundary", []):
        st.write("• " + x)

    with st.expander("查看本次检索到的材料"):
        for item in retrieved:
            st.markdown(f"**{item['id']}｜{item['title']}**")
            st.write(item["content"])
            st.caption(f"{item['type_label']}｜{item['source']}")

    st.divider()
    st.markdown("#### 这张卡适合你吗？")
    col1, col2 = st.columns(2)
    with col1:
        st.button("👍 有帮助", use_container_width=True)
    with col2:
        st.button("👎 有内容不适合我", use_container_width=True)
    st.text_area(
        "你还想补充什么？",
        placeholder="例如：某条建议不适合我；还缺少某类交通信息；我有自己的应对经验……",
    )

st.divider()
st.caption(
    "AccessWeather MVP · 首轮验证场景：北京 × 暴雨 × 残障女性出行。"
)
