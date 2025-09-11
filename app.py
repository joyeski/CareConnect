import os
import json
import time
from flask import Flask, request, Response
from twilio.twiml.messaging_response import MessagingResponse
from langdetect import detect
from rapidfuzz import fuzz, process
import groq
from googletrans import Translator


app = Flask(__name__)

# loading responses from file
with open("responses.json", "r", encoding="utf-8") as f:
    responses = json.load(f)

questions_list = list(responses.keys())

# groq setup
api_key = os.getenv("GROQ_API_KEY")
if api_key:
    client = Groq(api_key=api_key)
else:
    client = None

# the system rules for the AI
SYSTEM_PROMPT = """You are CareConnect, a rural health assistant.
STRICT RULES:
1) Always respond in ENGLISH, even if user writes in Hindi or Hinglish.
2) Only answer health-related questions: diseases, symptoms, nutrition, hygiene, minor injuries, prevention, treatments.
3) If the question is unrelated to mental or physical health, reply EXACTLY:
'I am here to answer health-related questions only. Please ask health related issues.'
4) Keep answers SHORT, FACTUAL, and TO THE POINT. No extra chit-chat.
5) Use the provided conversation context for follow-ups.
"""

# storing user context
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
    if score > 60:
        return match
    return None

@app.route("/", methods=["GET"])
def home():
    return "CareConnect WhatsApp Bot is running!"

from googletrans import Translator

translator = Translator()

@app.route("/webhook", methods=["POST"])
def webhook():
    incoming_msg = request.values.get("Body", "").strip()
    user_id = request.values.get("From", "default_user")
    print("Message from", user_id, ":", incoming_msg)

    resp = MessagingResponse()
    msg = resp.message()

    # detect language
    try:
        detected_lang = translator.detect(incoming_msg).lang
    except:
        detected_lang = "en"

    # greetings
    greetings = ["hi", "hello", "hey", "hii", "helo"]
    if incoming_msg.lower() in greetings:
        reply = "Hello, I am CareConnect, your healthbot. How can I help you with health-related queries?"
        # translate if needed
        if detected_lang != "en":
            try:
                reply = translator.translate(reply, dest=detected_lang).text
            except Exception as e:
                print("⚠️ Translation failed:", e)
        msg.body(reply)
        print("Replied:", reply)
        return Response(str(resp), mimetype="application/xml")

    lang = "en"  # always process in English

    # context restore
    context = ""
    if user_id in user_contexts:
        last_time = user_contexts[user_id].get("last_update", 0)
        if time.time() - last_time < 900:
            context = "Previous topic: " + user_contexts[user_id].get("last_topic", "")
        else:
            user_contexts.pop(user_id, None)

    reply = None
    found = False

    # check exact match
    if incoming_msg.lower() in [q.lower() for q in responses.keys()]:
        for q, ans in responses.items():
            if q.lower() == incoming_msg.lower():
                reply = ans.get("en")  # always store English answers
                found = True
                print("Exact match reply:", reply)
                user_contexts[user_id] = {"last_topic": q, "last_update": time.time()}
                break

    # check fuzzy match
    if not found:
        match_question = fuzzy_match(incoming_msg)
        if match_question:
            reply = responses[match_question].get("en")
            found = True
            print("Fuzzy match reply:", reply)
            user_contexts[user_id] = {"last_topic": match_question, "last_update": time.time()}

    # if no match found, ask groq
    if not found:
        reply = ask_groq(incoming_msg, context=context, lang=lang)
        print("AI reply:", reply)
        user_contexts[user_id] = {"last_topic": incoming_msg, "last_update": time.time()}

    # translate reply if needed
    if detected_lang != "en":
        try:
            reply = translator.translate(reply, dest=detected_lang).text
        except Exception as e:
            print("Translation failed:", e)

    msg.body(reply)
    print("Sending to", user_id, ":", reply)
    return Response(str(resp), mimetype="application/xml")


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)


