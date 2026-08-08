from groq import Groq
from app.core.config import Settings


settings = Settings()

client = Groq(
    api_key=settings.GROQ_API_KEY
)


SYSTEM_PROMPT = """
You are AskLaw, an AI legal assistant.

Your job is to explain legal concepts in simple language.

Rules:

- Answer clearly and professionally.
- Use headings and bullet points when helpful.
- If the user asks about a country's law, answer for that country if specified.
- If no country is specified, ask which country's law they mean.
- Never claim to be a licensed lawyer.
- State that your responses are for educational purposes and not legal advice.
- Keep answers concise unless the user asks for more detail.
"""


def stream_response(messages):

    groq_messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT,
        }
    ]

    for message in messages:
        groq_messages.append(
            {
                "role": message.role,
                "content": message.content,
            }
        )

    stream = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=groq_messages,
        temperature=0.3,
        max_completion_tokens=2048,
        stream=True,
    )

    for chunk in stream:
        content = chunk.choices[0].delta.content

        if content:
            yield content