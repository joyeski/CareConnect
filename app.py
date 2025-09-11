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

@app.route("/webhook", methods=['POST'])
def webhook():
    # Get user message
    user_text = request.values.get('Body', '').strip()
    
    if not user_text:
        reply = "Sorry, I didn't get that. Please type something."
        resp = MessagingResponse()
        resp.message(reply)
        return str(resp)
    
    # Step 1: Translate user input to English for matching
    try:
        translated_text = GoogleTranslator(source='auto', target='en').translate(user_text)
    except:
        translated_text = user_text  # fallback if translation fails
    
    # Step 2: Find the best match in responses
    match_question, score = process.extractOne(translated_text, responses.keys())
    
    if score < 50:  # threshold for fuzzy match
        reply_en = "Sorry, I don't have an answer for that. Please ask something else."
    else:
        reply_en = responses[match_question]["en"]
    
    # Step 3: Translate reply back to user language if needed
    try:
        # Detect language of the original message using Deep Translator auto-detect
        user_lang = GoogleTranslator(source='auto', target='en').detect(user_text)
    except:
        user_lang = 'en'  # fallback
    
    if user_lang != 'en':
        try:
            reply = GoogleTranslator(source='en', target=user_lang).translate(reply_en)
        except:
            reply = reply_en
    else:
        reply = reply_en
    
    # Step 4: Send reply via Twilio
    resp = MessagingResponse()
    resp.message(reply)
    return str(resp)

if __name__ == "__main__":
    app.run(debug=True)


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)


