import os
import json
import time
from flask import Flask, request, Response
from twilio.twiml.messaging_response import MessagingResponse
from langdetect import detect
from rapidfuzz import fuzz, process
from groq import Groq

app = Flask(__name__)

# Load pre-written responses
with open("responses.json", "r", encoding="utf-8") as f:
    responses = json.load(f)

questions_list = list(responses.keys())

# Groq setup
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

SYSTEM_PROMPT = (
    "You are a rural health assistant in India. STRICT RULES:\n"
    "1) Only answer health-related questions: fever, malaria, dengue, minor injuries, waterborne diseases, nutrition, etc.\n"
    "2) If the question is unrelated, reply EXACTLY:\n"
    "'I am here to answer health-related questions only. Please ask about fever, malaria, dengue, or other health issues.'\n"
    "3) Respond in the SAME language as the user (Hindi if Hindi, else English).\n"
    "4) Keep answers SHORT, FACTUAL, and TO THE POINT. No extra chit-chat.\n"
    "5) Use provided conversation context for follow-ups.\n"
)

user_contexts = {}

def query_groq(user_input, context="", lang="en"):
    """Call Groq API"""
    if not client:
        return "⚠️ AI engine not configured (missing API key)."
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
        return f"⚠️ Groq request failed: {e}"

def get_fuzzy_match(user_input):
    """Find closest match from responses.json"""
    match, score, _ = process.extractOne(
        user_input, questions_list, scorer=fuzz.ratio
    )
    return match if score > 70 else None

@app.route("/", methods=["GET"])
def home():
    return "✅ CareConnect WhatsApp Bot is running!"

@app.route("/webhook", methods=["POST"])
def webhook():
    incoming_msg = request.values.get("Body", "").strip()
    user_id = request.values.get("From", "default_user")
    print(f"📩 Incoming from {user_id}: {incoming_msg}")

    # Detect language
    try:
        lang_detected = detect(incoming_msg)
        lang = "hi" if lang_detected.startswith("hi") else "en"
    except:
        lang = "en"

    reply = "⚠️ Sorry, I couldn’t process that. Please ask about fever, malaria, dengue, or other health issues."

    # Restore context
    context = ""
    if user_id in user_contexts:
        last_time = user_contexts[user_id].get("last_update", 0)
        if time.time() - last_time < 900:
            context = f"Previous topic: {user_contexts[user_id].get('last_topic','')}"
        else:
            user_contexts.pop(user_id, None)

    # 1. Exact match
    if incoming_msg.lower() in responses:
        reply = responses[incoming_msg.lower()].get(lang, responses[incoming_msg.lower()].get("en"))
        user_contexts[user_id] = {"last_topic": incoming_msg, "last_update": time.time()}
        print(f"✅ Exact match reply: {reply}")

    # 2. Fuzzy match
    else:
        match_question = get_fuzzy_match(incoming_msg)
        if match_question:
            reply = responses[match_question].get(lang, responses[match_question].get("en"))
            user_contexts[user_id] = {"last_topic": match_question, "last_update": time.time()}
            print(f"✅ Fuzzy match reply: {reply}")
        else:
            # 3. Dynamic Groq fallback
            reply = query_groq(incoming_msg, context=context, lang=lang)
            user_contexts[user_id] = {"last_topic": incoming_msg, "last_update": time.time()}
            print(f"🤖 Dynamic answer: {reply}")

    # Send back Twilio-compatible XML
    resp = MessagingResponse()
    resp.message(reply)
    print(f"📤 Outgoing to {user_id}: {reply}")
    return Response(str(resp), mimetype="application/xml")

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))  # Render sets PORT automatically
    app.run(host="0.0.0.0", port=port, debug=True)
