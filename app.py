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

# load responses
with open("responses.json", "r", encoding="utf-8") as f:
    responses = json.load(f)

questions_list = list(responses.keys())

# groq setup
api_key = os.getenv("GROQ_API_KEY")
client = Groq(api_key=api_key) if api_key else None

SYSTEM_PROMPT = """You are CareConnect, a rural health assistant.
STRICT RULES:
1) Always respond in ENGLISH, even if user writes in Hindi or Hinglish.
2) Only answer health-related questions: diseases, symptoms, nutrition, hygiene, minor injuries, prevention, treatments.
3) If the question is unrelated to mental or physical health, reply EXACTLY:
'I am here to answer health-related questions only. Please ask health related issues.'
4) Keep answers SHORT, FACTUAL, and TO THE POINT. No extra chit-chat.
5) Use the provided conversation context for follow-ups.
"""

# user context store
user_contexts = {}

def ask_groq(user_input, context="", lang="en"):
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
    text = user_input.lower()
    for key in questions_list:
        if key.lower() in text:
            return key
    match, score, _ = process.extractOne(user_input, questions_list, scorer=fuzz.ratio)
    return match if score > 80 else None

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

    # detect language
    try:
        detected_lang = detect(incoming_msg)
    except:
        detected_lang = "en"

    # greetings
    greetings = ["hi", "hello", "hey", "hii", "helo"]
    if incoming_msg.lower() in greetings:
        reply = "Hello, I am CareConnect, your healthbot. How can I help you with health-related queries?"
        if detected_lang != "en":
            try:
                reply = GoogleTranslator(source="en", target=detected_lang).translate(reply)
            except Exception as e:
                print("Translation failed:", e)
        msg.body(reply)
        print("Replied:", reply)
        return Response(str(resp), mimetype="application/xml")

    # restore context
    context = ""
    if user_id in user_contexts:
        last_time = user_contexts[user_id].get("last_update", 0)
        if time.time() - last_time < 900:
            context = "Previous topic: " + user_contexts[user_id].get("last_topic", "")
        else:
            user_contexts.pop(user_id, None)

    reply, found = None, False

    # exact match
    if incoming_msg.lower() in [q.lower() for q in responses.keys()]:
        for q, ans in responses.items():
            if q.lower() == incoming_msg.lower():
                reply = ans.get("en")
                found = True
                user_contexts[user_id] = {"last_topic": q, "last_update": time.time()}
                print("Exact match reply:", reply)
                break

    # fuzzy match
    if not found:
        match_question = fuzzy_match(incoming_msg)
        if match_question:
            reply = responses[match_question].get("en")
            found = True
            user_contexts[user_id] = {"last_topic": match_question, "last_update": time.time()}
            print("Fuzzy match reply:", reply)

    # AI fallback
    if not found:
        reply = ask_groq(incoming_msg, context=context)
        user_contexts[user_id] = {"last_topic": incoming_msg, "last_update": time.time()}
        print("AI reply:", reply)

    # translate if user not English
    if detected_lang != "en":
        try:
            reply = GoogleTranslator(source="en", target=detected_lang).translate(reply)
        except Exception as e:
            print("Translation failed:", e)

    msg.body(reply)
    print("Sending to", user_id, ":", reply)
    return Response(str(resp), mimetype="application/xml")


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)

