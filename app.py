@app.route("/webhook", methods=["POST"])
def webhook():
    incoming_msg = request.values.get("Body", "").strip()
    user_id = request.values.get("From", "default_user")
    print("Message from", user_id, ":", incoming_msg)

    resp = MessagingResponse()
    msg = resp.message()

    # 1. Detect language
    try:
        detected_lang = detect(incoming_msg)
    except:
        detected_lang = "en"

    # 2. Translate user input to English if needed
    user_msg_en = incoming_msg
    if detected_lang != "en":
        try:
            user_msg_en = GoogleTranslator(source="auto", target="en").translate(incoming_msg)
        except:
            user_msg_en = incoming_msg

    # 3. Greetings (force English for simplicity)
    greetings = ["hi", "hello", "hey", "hii", "helo"]
    if user_msg_en.lower() in greetings:
        reply_en = "Hello, I am CareConnect, your healthbot. How can I help you with health-related queries?"
    else:
        # Check JSON first
        reply_en = None
        if user_msg_en.lower() in [q.lower() for q in responses.keys()]:
            for q, ans in responses.items():
                if q.lower() == user_msg_en.lower():
                    reply_en = ans.get("en")
                    print("Exact match reply:", reply_en)
                    break

        # If no JSON match, try fuzzy
        if not reply_en:
            match_question = fuzzy_match(user_msg_en)
            if match_question:
                reply_en = responses[match_question].get("en")
                print("Fuzzy match reply:", reply_en)

        # If still nothing, go to AI
        if not reply_en:
            reply_en = ask_groq(user_msg_en)
            print("AI reply:", reply_en)

    # 4. Translate back if needed
    final_reply = reply_en
    if detected_lang != "en":
        try:
            final_reply = GoogleTranslator(source="en", target=detected_lang).translate(reply_en)
        except:
            final_reply = reply_en

    msg.body(final_reply)
    print("Sending to", user_id, ":", final_reply)
    return Response(str(resp), mimetype="application/xml")
