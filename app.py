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

@app.route("/", methods=["GET"])
def home():
    return "CareConnect WhatsApp Bot is running!"

@app.route("/webhook", methods=["POST"])
def webhook():
    user_text = request.values.get("Body", "").strip()

    if not user_text:
        resp = MessagingResponse()
        resp.message("Sorry, I didn't get that. Please type something.")
        return str(resp)

    # Step 1: Translate user input to English for matching
    try:
        translated_text = GoogleTranslator(source="auto", target="en").translate(user_text)
    except Exception:
        translated_text = user_text  # fallback

    # Step 2: Fuzzy match in responses
    try:
        result = process.extractOne(translated_text, responses.keys(), scorer=fuzz.ratio)
        if result:
            match_question, score = result[0], result[1]
        else:
            match_question, score = None, 0
    except Exception:
        match_question, score = None, 0

    # Step 3: Select response
    if score >= 60 and match_question:
        reply_en = responses[match_question]["en"]
    else:
        # Use Groq AI as fallback
        reply_en = ask_groq(translated_text)

    # Step 4: Detect original language
    try:
        user_lang = detect(user_text)
    except:
        user_lang = "en"

    # Step 5: Translate reply back if needed
    if user_lang != "en":
        try:
            reply = GoogleTranslator(source="en", target=user_lang).translate(reply_en)
        except Exception:
            reply = reply_en
    else:
        reply = reply_en

    # Step 6: Send reply
    resp = MessagingResponse()
    resp.message(reply)
    return str(resp)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
