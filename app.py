import os
import json
import time
from flask import Flask, request, Response
from twilio.twiml.messaging_response import MessagingResponse
from rapidfuzz import fuzz, process
from groq import Groq
from deep_translator import GoogleTranslator

app = Flask(__name__)

# Load responses
with open("responses.json", "r", encoding="utf-8") as f:
    responses = json.load(f)

questions_list = list(responses.keys())

# Groq setup
api_key = os.getenv("GROQ_API_KEY")
client = Groq(api_key=api_key) if api_key else None

SYSTEM_PROMPT = """You are CareConnect, a rural health assistant.
STRICT RULES:
1) Only answer health-related questions: diseases, symptoms, nutrition, hygiene, minor injuries, prevention, treatments.
2) If the question is unrelated to mental or physical health, reply EXACTLY:
'I am here to answer health-related questions only. Please ask health related issues.'
3) Keep answers SHORT, FACTUAL, and TO THE POINT. No extra chit-chat.
"""

# Store user contexts
user_contexts = {}

def ask_groq(user_input, context=""):
    if not client:
        return "AI engine not working (no API key found)."
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
    if result and result[1] >= 70:
        return result[0]
    return None

@app.route("/", methods=["GET"])
def home():
    return "CareConnect WhatsApp Bot is running!"

@app.route("/webhook", methods=["POST"])
def webhook():
    incoming_msg = request.values.get("Body", "").strip()
    user_id = request.values.get("From", "default_user")
    print("Message from", user_id, ":", incoming_msg)

    resp = MessagingResponse()
    msg = resp.message()

    # Detect language of current message
    try:
        detected_lang = GoogleTranslator(source="auto", target="en").detect(incoming_msg)
    except Exception:
        detected_lang = "en"

    # Always process in English
    try:
        user_text_en = GoogleTranslator(source="auto", target="en").translate(incoming_msg)
    except Exception:
        user_text_en = incoming_msg

    # Greetings
    greetings = ["hi", "hello", "hey", "hii", "helo", "hola", "bonjour"]
    if incoming_msg.lower() in greetings:
        reply_en = "Hello, I am CareConnect, your healthbot. How can I help you with health-related queries?"
    else:
        context = ""
        if user_id in user_contexts:
            last_time = user_contexts[user_id].get("last_update", 0)
            if time.time() - last_time < 900:
                context = "Previous topic: " + user_contexts[user_id].get("last_topic", "")
            else:
                user_contexts.pop(user_id, None)

        reply_en = None
        found = False

        # Exact match
        if user_text_en.lower() in [q.lower() for q in responses.keys()]:
            for q, ans in responses.items():
                if q.lower() == user_text_en.lower():
                    reply_en = ans.get("en")
                    found = True
                    user_contexts[user_id] = {"last_topic": q, "last_update": time.time()}
                    break

        # Fuzzy match
        if not found:
            match_question = fuzzy_match(user_text_en)
            if match_question:
                reply_en = responses[match_question].get("en")
                found = True
                user_contexts[user_id] = {"last_topic": match_question, "last_update": time.time()}

        # Groq AI fallback
        if not found:
            reply_en = ask_groq(user_text_en, context=context)
            user_contexts[user_id] = {"last_topic": user_text_en, "last_update": time.time()}

    # Translate reply back to user’s language if needed
    if detected_lang != "en":
        try:
            reply = GoogleTranslator(source="en", target=detected_lang).translate(reply_en)
        except Exception:
            reply = reply_en
    else:
        reply = reply_en

    msg.body(reply)
    print(f"Detected lang={detected_lang}, Reply={reply}")
    return Response(str(resp), mimetype="application/xml")

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
