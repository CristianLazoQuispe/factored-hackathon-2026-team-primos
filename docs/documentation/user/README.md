# User Guide

A customer-service assistant for a Latin American bank. You chat with it in **Spanish or Portuguese**. It runs on **synthetic data**: no real customers or money are involved.

## Open it

- **Local:** `cp .env.example .env && make up`, then open http://localhost:3000 and press **Hablar con Quipu**, or go straight to http://localhost:3000/chat (see the [root README](../../../README.md)).
- **Customer ID:** the **Cliente** field at the top of the chat. Locally it is prefilled with test customers from the organizer's synthetic dataset. Pick one from the list or type any `CLI-…` ID. Changing it starts a new conversation.

## What you can ask today

| You write | The assistant |
|---|---|
| *¿Cuál es mi saldo?* / *Qual é o meu saldo?* | Lists your accounts and cards: balance, currency, credit limit and status. Card numbers show only the last 4 digits |
| *¿Cuánto tengo en mi tarjeta de crédito?* | Shows only that product type |
| *¿Y la de débito?* | Follows up in the same conversation |
| *Quiero hablar con una persona* | Transfers you to a human agent at once, with your case summarized |
| Anything else (advice, other topics) | Answers briefly, says what it can help with, and offers a person |

You can also **talk to it**: click the large microphone under Quipu's avatar, say your question in Spanish or Portuguese, and click again to send it. What you said appears as your message. The two buttons at the top show what is allowed on this page: **Permitir micrófono** asks the browser for the microphone before your first message, and the **Silencio** / **Voz** button makes the assistant read its answers aloud, in your language. The avatar shows what the assistant is doing: it stretches out while idle, bends while it listens and closes into a crown while it looks things up and answers. With the voice on, an answer is written on screen as it is read; **Mostrar todo** under it shows the whole text at once while the voice goes on. The voice is off every time the page loads; pressing the button again, the microphone or sending another message stops the reading and shows the rest of the text.

Under each answer, small labels show what the assistant used (for example `balance_inquiry` and `get_balances`) or that you were transferred to a person. **Mis finanzas**, next to the chat, shows a summary of your spending; for now it is a sample with fixed figures, and so is the chart that answers *¿En qué gasto más?*.

## Your data and safety

- The assistant only sees the accounts of the customer in the session. It cannot show another customer's data, even if you ask for it by ID.
- It never asks for passwords, OTP codes or full card numbers, and never sends links.
- If you don't give a customer ID, it asks for it and checks that it exists before answering.

## Current limits

- **Balances only.** Disputes, card blocking, credit and other requests are planned; today they get a short answer and the offer of a person.
- **Response time:** a few seconds with the local model (Ollama), faster with Gemini.
- **Portuguese:** understood and answered, but the underlying dataset is Spanish-only (Mexico, Colombia, Argentina).
- **Test identity:** the customer ID field is a test login for synthetic data. A real deployment would require a verified sign-in before any sensitive action.
