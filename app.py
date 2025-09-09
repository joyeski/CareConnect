import os
import json
import time
from flask import Flask, request, Response
from twilio.twiml.messaging_response import MessagingResponse
from langdetect import detect
from rapidfuzz import fuzz, process
from groq import Groq

app = Flask(__name__)

with open("responses.json", "r", encoding="utf-8") as f:
    responses = json.load(f)

questions_list = list(responses.keys())

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
    match, score, _ = process.extractOne(
        user_input, questions_list, scorer=fuzz.ratio
    )
    if score > 70:
        return match
    return None

@app.route("/webhook", methods=["POST"])
def webhook():
    incoming_msg = request.values.get("Body", "").strip()
    user_id = request.values.get("From", "default_user")
    print(f"📩 Incoming from {user_id}: {incoming_msg}")

    try:
        lang_detected = detect(incoming_msg)
        lang = "hi" if lang_detected.startswith("hi") else "en"
    except:
        lang = "en"

    resp = MessagingResponse()
    msg = resp.message()
    reply = None

    context = ""
    if user_id in user_contexts:
        last_time = user_contexts[user_id].get("last_update", 0)
        if time.time() - last_time < 900:
            context = f"Previous topic: {user_contexts[user_id].get('last_topic','')}"
        else:
            user_contexts.pop(user_id, None)

    found = False
    for question, answer in responses.items():
        if question.lower() == incoming_msg.lower():
            reply = answer.get(lang, answer.get("en"))
            print(f"✅ Exact match reply: {reply}")
            found = True
            user_contexts[user_id] = {"last_topic": question, "last_update": time.time()}
            break

    if not found:
        match_question = get_fuzzy_match(incoming_msg)
        if match_question:
            reply = responses[match_question].get(lang, responses[match_question].get("en"))
            print(f"✅ Fuzzy match reply: {reply}")
            found = True
            user_contexts[user_id] = {"last_topic": match_question, "last_update": time.time()}

    if not found:
        reply = query_groq(incoming_msg, context=context, lang=lang)
        print(f"🤖 Dynamic answer: {reply}")
        user_contexts[user_id] = {"last_topic": incoming_msg, "last_update": time.time()}

    msg.body(reply)
    print(f"📤 Outgoing to {user_id}: {reply}")
    return Response(str(resp), mimetype="application/xml")

if __name__ == "__main__":
    app.run(port=5000, debug=True)
