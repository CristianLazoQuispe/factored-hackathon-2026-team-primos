# User Guide

A customer-service assistant for a Latin American bank. You chat with it in **Spanish or Portuguese**. It runs on **synthetic data**: no real customers or money are involved.

## Open it

- **Local:** `cp .env.example .env && make up`, then open http://localhost:3000 and press **Hablar con Quipu**, or go straight to http://localhost:3000/chat (see the [root README](../../../README.md)).
- **Sign in:** at the top of the chat, a customer ID from the list the field offers (the password is the same ID), or one of the eight demo emails from the [demo guide](demo_guide.md). To try khipear, sign in as `DEMO-MX-KHIPU`: it has two accounts, a credit card and a loan. The eight email customers have one savings account and a card, enough to pay the card. That starts the session. **Salir** ends it.

## What you can ask today

| You write | The assistant |
|---|---|
| *¿Cuál es mi saldo?* / *Qual é o meu saldo?* | Lists your accounts and cards: balance, currency, credit limit and status. Card numbers show only the last 4 digits |
| *¿Cuánto tengo en mi tarjeta de crédito?* | Shows only that product type |
| *¿Y la de débito?* | Follows up in the same conversation |
| *¿Cuánto debo en mi tarjeta y cuándo vence?* / *¿Cuál es mi pago mínimo?* | Shows what you owe on cards and loans, the due date and the minimum payment or installment. The payment dates and amounts are illustrative figures as of 18 June 2026 (the dataset has none) |
| *Dime mis últimos movimientos* / *Muéstrame mis compras en Uber* | Lists your movements, by account or card, merchant, type or amount |
| *¿Cuánto gasté este mes?* / *¿En qué gasto más?* | Totals your approved purchases by category, merchant and month, against the period before |
| *¿Cuántas quejas tengo?* | Counts your complaints and says in what state they are |
| *¿A cuánto está el dólar?* | Gives the bank's reference exchange rate |
| *No reconozco un cargo de Uber* | Finds the charge and checks the bank's records: charged twice, still pending, already reversed, or bought abroad |
| Attach a photo of the charge and write *No reconozco estas transacciones* | Reads the merchant, amount and date from the photo and checks that charge. Sample photos for each demo customer are in `web/public/casos/` |
| *Bloquea mi tarjeta* / *Preciso bloquear meu cartão* (when the deployment has actions on) | Proposes it and **waits**. A card shows exactly what will be done, with **Confirmar** and **Cancelar**. Only after you confirm does it act, and it reads the result back before saying it is done |
| *No reconozco un cargo de Uber, abre una consulta y mándame el comprobante* | Proposes an inquiry about the charge (with its priority and the hours a person has to answer) and the receipt by email. You confirm both at once |
| *Me robaron la tarjeta* | Proposes blocking it right away and also asks for a person |
| *Quiero un reembolso* / *Cambia mi teléfono* | Says it does not do that on its own: a refund or a change of contact data goes to a person with your case |
| *Khipea 300 a mi tarjeta* / *Transfiere 500 a mi otra cuenta* / *Khipéale 200 a CLI-...* | Prepares the payment or transfer and shows a card with **Confirmar** and **Cancelar**. If you have several accounts it asks which one. Nothing moves until you press Confirmar |
| *¿Qué recibos tengo pendientes?* / *Paga la luz* / *Paga mi recibo de internet* | Lists your pending service bills (electricity, water, phone, internet, cable TV; illustrative figures), or prepares the payment of one for its whole amount and shows the same card. If several bills or accounts fit, it asks which |
| *¿Desde cuándo soy cliente?* | Shows your own data on record |
| *Quiero hablar con una persona* | Transfers you to a human agent at once, with your case summarized |
| Anything else (advice, other topics) | Answers briefly, says what it can help with, and offers a person |

You can also **talk to it**: click the large microphone under Quipu's avatar, say your question in Spanish or Portuguese, and click again to send it. What you said appears as your message. The two buttons at the top show what is allowed on this page: **Permitir micrófono** asks the browser for the microphone before your first message, and the **Silencio** / **Voz** button makes the assistant read its answers aloud, in your language. The avatar shows what the assistant is doing: it stretches out while idle, bends while it listens and closes into a crown while it looks things up and answers. With the voice on, an answer is written on screen as it is read; **Mostrar todo** under it shows the whole text at once while the voice goes on. The voice is off every time the page loads; pressing the button again, the microphone or sending another message stops the reading and shows the rest of the text.

When actions are on, **Mensajes** at the top of the chat shows what the system sent you. In the demo nothing goes to a real address: a message either stays in that tray (it says *simulado · no se envió*) or goes to a demo inbox of the team (it says *aceptado por el servidor*, never "delivered", because that cannot be checked).

Under each answer, small labels show what the assistant used (for example `balance_inquiry` and `get_balances`) or that you were transferred to a person. **Mis finanzas**, next to the chat, shows a summary of your own spending, from the bank's data, and so does the chart that answers *¿En qué gasto más?*.

## Your data and safety

- The assistant only sees the accounts of the customer in the session. It cannot show another customer's data, even if you ask for it by ID.
- It never asks for passwords, OTP codes or full card numbers, and never sends links.
- Where there is no sign-in (Telegram), it asks for your customer ID and checks that it exists before answering.

## Current limits

- **It never moves money on its own, and never refunds.** A transfer or payment is only prepared (khipear, below) and runs when you press Confirmar. With actions off (the default) it looks things up, prepares transfers and payments, and offers a person for the rest. With actions on it can, after you confirm, block or cancel a card, open an inquiry, ask for a call, set an alert and email you a summary; a card whose balance is owed, or that the bank itself blocked, is never cancelled by it and goes to a person.
- **Moving money (khipear)** works in the web chat only, between accounts in the same currency (a service bill is paid from an account in the bill's currency, whole, never in part), and always needs your click on Confirmar within 5 minutes. To another customer you give their account number or customer ID; there is a limit of USD 1,000 per operation and USD 3,000 per day (values chosen by the team). Writing or saying "sí" confirms nothing.
- **A snapshot, not live data.** The data ends on 18 June 2026, so "this month" means the last month in the data.
- **Response time:** a few seconds with the local model (Ollama), faster with Gemini.
- **Portuguese:** understood and answered, but the underlying dataset is Spanish-only (Mexico, Colombia, Argentina).
- **Test identity:** the customer ID field is a test login for synthetic data. A real deployment would require a verified sign-in before any sensitive action.
