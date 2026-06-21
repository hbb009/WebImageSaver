# app.py
import streamlit as st
from zhipuai import ZhipuAI
import base64
import mimetypes

st.set_page_config(page_title="角色识别小程序", page_icon="🎭", layout="centered")
st.title("🎭 角色识别小程序")

# API Key 输入（建议用环境变量生产环境）
api_key = st.text_input("请输入智谱清言 API Key", type="password")

# 图片上传并预览
uploaded_file = st.file_uploader("上传一张图片", type=["jpg", "jpeg", "png"])
if uploaded_file is not None:
    st.image(uploaded_file, caption="已上传图片预览", use_column_width=True)

# 提问输入（默认提示为识别角色名）
user_prompt = st.text_area("输入你的问题", "请告诉我这张图片中的角色是谁。只返回角色名，若无法识别则返回“无法识别”。")

# 按钮触发识别
if st.button("开始识别"):
    if not api_key:
        st.error("请先输入 API Key")
    elif uploaded_file is None:
        st.error("请先上传图片")
    else:
        client = ZhipuAI(api_key=api_key)

        # 读取文件字节并构造 base64 编码
        raw = uploaded_file.read()
        # 尝试推断 mime type
        mime_type, _ = mimetypes.guess_type(uploaded_file.name)
        if not mime_type:
            mime_type = "image/png"
        data_b64 = base64.b64encode(raw).decode("utf-8")

        # 构造 Zhipu AI API 的 messages 参数
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_prompt},
                    {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{data_b64}"}}
                ]
            }
        ]

        with st.spinner("识别中，请稍候..."):
            try:
                # 调用 Zhipu AI 的 chat.completions API（支持视觉模型，例如 GLM-4V）
                response = client.chat.completions.create(
                    model="glm-4v",  # 使用支持图像输入的模型，确认你有权限
                    messages=messages,
                )

                # 提取结果
                result_text = response.choices[0].message.content.strip()
                if not result_text:
                    result_text = "未获取到文本结果"

                st.success("识别结果：")
                st.write(result_text)

            except Exception as e:
                st.error("调用 API 出错，请检查以下内容：")
                st.write("- 确认 API Key 是否正确（从智谱清言平台获取）。")
                st.write("- 确认模型 'glm-4v' 是否支持图片输入且您有权限使用。")
                st.write("- 检查 API 配额是否已用尽。")
                st.write(f"错误信息（供调试）: {e}")