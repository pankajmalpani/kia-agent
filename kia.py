import os
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

key = os.getenv("GROQ_API_KEY")
client = Groq(api_key=key)

print("Kia is ready! Type your question below.")
print("(Type 'bye' to exit)")
print("-----------------------------------")

while True:
    user_input = input("You: ")
    
    if user_input.lower() == "bye":
        print("Kia: Goodbye! Have a great day! 👋")
        break

    message = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": "You are Kia, a friendly assistant who answers general questions simply and clearly."},
            {"role": "user", "content": user_input}
        ]
    )

    print("Kia:", message.choices[0].message.content)
    print("-----------------------------------")