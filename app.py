import os
import json
import time
from flask import Flask, request, Response
from twilio.twiml.messaging_response import MessagingResponse
from langdetect import detect
from rapidfuzz import fuzz, process
from groq import Groq
from deep_translator import GoogleTranslator

app = Flask(__name__)

# Load FAQ responses
with open("responses.json", "r", encoding="utf-8") as f:
    responses = json.load(f)
questions_list = list(responses.keys())

# Groq setup
api_key = os.getenv("GROQ_API_KEY")
client = Groq(api_key=api_key) if api_key else None

SYSTEM_PROMPT = """You are CareConnect, a rural health assistant.
1) Only answer health-related questions.
2) If unrelated, reply: 'I am here to answer health-related questions only. Please ask health related issues.'
3) Keep answers short and factual.
"""

user_contexts = {}

def ask_groq(user_input, context=""):
    if not client:
        return "AI not available."
    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"{context}\n\nUser: {user_input}"}
            ],
            temperature=0.2,
            max_tokens=200,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"AI request failed: {e}"

def fuzzy_match(user_input):
    result = process.extractOne(user_input, questions_list, scorer=fuzz.ratio)
    if result and result[1] >= 60:  # lowered threshold for better matching
        return result[0]
    return None

@app.route("/", methods=["GET"])
def home():
    return "CareConnect Bot is running!"

@app.route("/webhook", methods=["POST"])
def webhook():
    incoming_msg = request.values.get("Body", "").strip()
    user_id = request.values.get("From", "default_user")
    print("Message from", user_id, ":", incoming_msg)

    resp = MessagingResponse()
    msg = resp.message()

    # Detect language
    try:
        detected_lang = detect(incoming_msg)
    except Exception:
        detected_lang = "en"

    # Translate input to English
    try:
        user_text_en = GoogleTranslator(source="auto", target="en").translate(incoming_msg)
    except Exception:
        user_text_en = incoming_msg

    reply_en = None

    # Greetings
    greetings = ["hi", "hello", "hey", "hii", "helo", "hola", "bonjour"]
    if incoming_msg.lower() in greetings:
        reply_en = "Hello, I am CareConnect, your healthbot. How can I help you with health-related queries?"
    else:
        # FAQ check
        match_question = fuzzy_match(user_text_en)
        if match_question:
            reply_en = responses[match_question].get("en")
            user_contexts[user_id] = {"last_topic": match_question, "last_update": time.time()}
        else:
            # AI fallback
            context = ""
            if user_id in user_contexts and time.time() - user_contexts[user_id]["last_update"] < 900:
                context = "Previous topic: " + user_contexts[user_id]["last_topic"]
            reply_en = ask_groq(user_text_en, context=context)
            user_contexts[user_id] = {"last_topic": user_text_en, "last_update": time.time()}

    # Translate reply back to user language
    reply = reply_en
    if detected_lang != "en":
        try:
            reply = GoogleTranslator(source="en", target=detected_lang).translate(reply_en)
        except Exception:
            reply = reply_en

    msg.body(reply)
    print(f"Lang={detected_lang}, UserEN={user_text_en}, ReplyEN={reply_en}, Final={reply}")
    return Response(str(resp), mimetype="application/xml")

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
