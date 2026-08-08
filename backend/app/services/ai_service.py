import ollama

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
    ollama_messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT,
        }
    ]

    for message in messages:
        ollama_messages.append(
            {
                "role": message.role,
                "content": message.content,
            }
        )

    stream = ollama.chat(
        model="qwen3:4b",
        messages=ollama_messages,
        stream=True,
    )

    for chunk in stream:
        yield chunk["message"]["content"]