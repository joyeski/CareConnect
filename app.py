import json
import os
import time
from flask import Flask, request, Response
from twilio.twiml.messaging_response import MessagingResponse
from langdetect import detect
from rapidfuzz import process
from groq import Groq

app = Flask(__name__)

# Load FAQs from JSON
with open("responses.json", "r", encoding="utf-8") as f:
    responses = json.load(f)

# In-memory user context
user_contexts = {}

# Groq client using environment variable
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

SYSTEM_PROMPT_TEMPLATE = (
    "You are a rural health assistant in India. STRICT RULES:\n"
    "1) Only answer health-related questions: fever, malaria, dengue, minor injuries, waterborne diseases, nutrition, etc.\n"
    "2) If the question is unrelated, reply exactly: "
    "'I am here to answer health-related questions only. Please ask about fever, malaria, dengue, or other health issues.'\n"
    "3) Respond in the SAME language as the user (Hindi if user wrote in Hindi, otherwise English).\n"
    "4) Keep answers SHORT, FACTUAL, and TO THE POINT. No extra chit-chat.\n"
    "5) Use the provided conversation context for follow-ups.\n"
)

def query_groq(user_input, context="", lang="en"):
    if client is None:
        print("DEBUG: Groq client not initialized")
        return ("Sorry, AI engine is not configured. I can still answer common FAQs. "
                "Please ask about fever, dengue, or malaria.")
    try:
        print("DEBUG: Sending request to Groq...", user_input)
        health_context = SYSTEM_PROMPT_TEMPLATE + f"\nConversation context: {context}"
        resp = client.chat.completions.create(
            model="llama-3.1-8b-instant",  
            messages=[
                {"role": "system", "content": health_context},
                {"role": "user", "content": user_input},
            ],
            temperature=0.15,
            max_tokens=200,
        )
        print("DEBUG: Response received")
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print("DEBUG: Groq request failed:", e)
        return f"Groq error: {str(e)}"

def get_semantic_match(user_input):
    choices = list(responses.keys())
    best = process.extractOne(user_input.lower(), choices)
    if not best:
        return None
    match_str, score, _ = best
    return match_str if score >= 70 else None

@app.route("/webhook", methods=["POST"])
def webhook():
    incoming_msg = request.values.get("Body", "").strip()
    user_id = request.values.get("From", "default_user")

    try:
        lang_detected = detect(incoming_msg)
        lang = "hi" if lang_detected.startswith("hi") else "en"
    except:
        lang = "en"

    resp = MessagingResponse()
    msg = resp.message()
    incoming_lower = incoming_msg.lower()

    # Context handling (15 min expiration)
    context = ""
    if user_id in user_contexts:
        last_time = user_contexts[user_id].get("last_update", 0)
        if time.time() - last_time < 900:
            topic = user_contexts[user_id].get("last_topic", "")
            if topic:
                context = f"Previous topic: {topic}"
        else:
            user_contexts.pop(user_id, None)

    found = False
    # Exact match JSON
    for question, answer in responses.items():
        if question.lower() == incoming_lower:
            msg.body(answer.get(lang, answer.get("en")))
            user_contexts[user_id] = {"last_topic": question, "last_update": time.time()}
            found = True
            break

    # Semantic match
    if not found:
        match_question = get_semantic_match(incoming_lower)
        if match_question:
            msg.body(responses[match_question].get(lang, responses[match_question].get("en")))
            user_contexts[user_id] = {"last_topic": match_question, "last_update": time.time()}
            found = True

    # Groq fallback
    if not found:
        dynamic_answer = query_groq(incoming_msg, context=context, lang=lang)
        msg.body(dynamic_answer)
        user_contexts[user_id] = {"last_topic": incoming_msg[:80], "last_update": time.time()}

    return Response(str(resp), mimetype="application/xml")

if __name__ == "__main__":
    print("DEBUG: Starting Flask app...")
    print("DEBUG: Groq client configured:", bool(client))
    app.run(port=5000, debug=True)

