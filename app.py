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
    "You are CareConnect, a rural health assistant.\n"
    "STRICT RULES:\n"
    "1) Always respond in ENGLISH, even if user writes in Hindi or Hinglish.\n"
    "2) Only answer health-related questions: diseases, symptoms, nutrition, hygiene, minor injuries, prevention, treatments.\n"
    "3) If the question is completely unrelated to mental or physical health, reply EXACTLY:\n"
    "'I am here to answer health-related questions only. Please ask health related issues.'\n"
    "4) Keep answers SHORT, FACTUAL, and TO THE POINT. No extra chit-chat.\n"
    "5) Use the provided conversation context for follow-ups.\n"
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
    user_input_lower = user_input.lower()
    for key in questions_list:
        if key.lower() in user_input_lower:
            return key  
    match, score, _ = process.extractOne(
        user_input, questions_list, scorer=fuzz.ratio
    )
    if score > 60:  
        return match

    return None

@app.route("/", methods=["GET"])
def home():
    return "✅ CareConnect WhatsApp Bot is running!"

@app.route("/webhook", methods=["POST"])
def webhook():
    incoming_msg = request.values.get("Body", "").strip()
    user_id = request.values.get("From", "default_user")
    print(f"📩 Incoming from {user_id}: {incoming_msg}")

    resp = MessagingResponse()
    msg = resp.message()

    # Greeting check
    greetings = ["hi", "hello", "hey", "hii", "helo"]
    if incoming_msg.lower() in greetings:
        reply = "Hello, I am CareConnect, your healthbot. How can I help you with health-related queries?"
        msg.body(reply)
        print(f"👋 Greeting reply: {reply}")
        return Response(str(resp), mimetype="application/xml")

    lang = "en"  # force English only

    # Restore context
    context = ""
    if user_id in user_contexts:
        last_time = user_contexts[user_id].get("last_update", 0)
        if time.time() - last_time < 900:
            context = f"Previous topic: {user_contexts[user_id].get('last_topic','')}"
        else:
            user_contexts.pop(user_id, None)

    reply = None
    found = False

    # ✅ Exact match check
    if incoming_msg.lower() in [q.lower() for q in responses.keys()]:
        for question, answer in responses.items():
            if question.lower() == incoming_msg.lower():
                reply = answer.get("en")
                found = True
                print(f"✅ Exact match reply: {reply}")
                user_contexts[user_id] = {"last_topic": question, "last_update": time.time()}
                break

    # ✅ Fuzzy match check
    if not found:
        match_question = get_fuzzy_match(incoming_msg)
        if match_question:
            reply = responses[match_question].get("en")
            found = True
            print(f"✅ Fuzzy match reply: {reply}")
            user_contexts[user_id] = {"last_topic": match_question, "last_update": time.time()}

    # ✅ Only call Groq if no JSON match
    if not found:
        reply = query_groq(incoming_msg, context=context, lang=lang)
        print(f"🤖 Dynamic answer: {reply}")
        user_contexts[user_id] = {"last_topic": incoming_msg, "last_update": time.time()}

    msg.body(reply)
    print(f"📤 Outgoing to {user_id}: {reply}")
    return Response(str(resp), mimetype="application/xml")



if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))  # Render sets PORT automatically
    app.run(host="0.0.0.0", port=port, debug=True)





