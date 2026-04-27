from openai import OpenAI

client = OpenAI(
    api_key="sk-a633943d35414577a5c3ae87252569b6",  # 直接填进去测试
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)

try:
    completion = client.chat.completions.create(
        model="qwen-turbo", messages=[{"role": "user", "content": "你好"}]
    )
    print("✅ API Key 有效！返回：", completion.choices[0].message.content)
except Exception as e:
    print("❌ Key 无效：", e)
