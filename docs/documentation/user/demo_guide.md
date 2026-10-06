# Demo guide

Everything you can try in the running app: the pages, the questions the agent answers, the eight statement
images, and the customers that have data to show. Start it with `cp .env.example .env && make up` (see the
[root README](../../../README.md)) and open http://localhost:3000.

## Pages

| Page | What it is | Data |
|---|---|---|
| `/` | Landing | Static |
| `/chat` | The customer's chat, typed or spoken | Real: the agent |
| `/mis-finanzas` | The customer's spending | Real: `GET /api/me/finances` (Postgres) |
| `/consola` | The team's console: every chat, take one over, give it back (needs `OPERATOR_KEY`) | Real: the API's memory |
| `/consola/perfil` | A customer's 360 profile | Sample (`web/lib/profile.ts`) |
| `/consola/gerencia` | Management dashboard | Sample (`web/lib/ops.ts`) |

## What to ask

The pages marked Sample show the idea with fixed figures until the API serves them. In `/chat`, sign in with a customer ID from `DEMO_CUSTOMER_IDS` (the password is the same ID) or one of the eight demo emails below; with `*` in that list, the ID of any customer in the database signs in too (the UI asks `POST /api/auth/token` and keeps the short-lived bearer token). The agent handles **balances**, **charges you don't recognize** and **questions about your own data**, and prepares **transfers, payments and service bills** (khipear; try it as `DEMO-MX-KHIPU`, who has two accounts, a card and a loan, with `DEMO-MX-RECIBE` to receive):

| Ask | What happens |
|---|---|
| `¿cuál es mi saldo?` / `qual é o meu saldo?` | Skill `balance_inquiry` → MCP tool `get_balances` → real balances and totals from Postgres |
| `¿cuánto debo en mi tarjeta y cuándo vence?` | Skill `balance_inquiry` → `get_debts`: debt, due date and minimum payment (the payment schedule is team-generated, see [data/model.md](../technical/data/model.md)) |
| `no reconozco un cargo de Uber` (customer `DEMO-MX-DUPLICATE`) | Skill `charge_investigation` → `investigate_charges`: finds the charges and checks the bank's records (duplicate, pending, foreign) |
| Attach `web/public/casos/lucia-uber.png` and write `no reconozco estas transacciones` | The same skill reads Uber, 312.40 MXN and the date from the photo, then reports the duplicate |
| `dime mis últimos movimientos` / `¿en qué gasto más?` / `¿cuántas quejas tengo?` / `¿a cuánto está el dólar?` | Skill `data_lookup` → a tool with reviewed SQL (`get_movements`, `get_spending_summary`, `get_complaints`, `get_exchange_rate`) |
| A question about their data that no tool covers | Skill `data_lookup` → the model writes one SQL `SELECT`; code checks it and only lets it see this customer's rows |
| `khipea 300 a mi tarjeta` / `transfiere 500 a mi otra cuenta` / `khipéale 200 a CLI-...` | Skill `money_movement` → `propose_transfer`: asks which account when there are several, then shows a card. Only the customer's **Confirmar** button moves the money ([ADR 0004](../technical/adr/0004-khipear-money-movement.md)) |
| `¿y la de débito?` | Follows up in the same conversation |
| `quiero hablar con una persona` | Handoff to a human, decided by code with no LLM call |
| `¿me recomiendas una hipoteca?` | Short out-of-scope answer |
| No customer ID (Telegram, or `curl` locally without a token) | The agent asks for it and validates it against the database |
| Click the **microphone**, speak in Spanish or Portuguese, click again | faster-whisper transcribes it and the agent answers as above. With the **Silencio** button switched to **Voz**, Kokoro also reads the answer aloud |

The API is `POST /api/chat {message, thread_id?, image?, image_type?}`. Outside `APP_ENV=local` it needs `Authorization: Bearer <token>`. `POST /api/auth/token` takes `{user, password}`: `user` is an ID in `DEMO_CUSTOMER_IDS` (any customer's ID when the list has `*`) or a demo email, and the password is that same text (`email` is still accepted as the field name). The customer is the token's, never the body's. Locally `curl` can still send `customer_id` in the body without a token. Swagger: http://localhost:8080/docs.

The password of each account is the email itself. The statement images are in `web/public/casos/`. In `/chat`, sign in, attach that customer's image with the clip, and write the question. The text is required: the photo alone is not sent.

| Email (also the password) | Case | Image |

## The eight statement images

|---|---|---|
| `demo-mx-duplicate@demo.bank` | Lucía, two Uber Trip charges of 312.40 MXN | `web/public/casos/lucia-uber.png` |
| `demo-mx-fx@demo.bank` | Mariana, a Best Buy purchase in dollars | `web/public/casos/mariana-bestbuy.png` |
| `demo-co-pending@demo.bank` | Andrés, an Amazon charge still pending | `web/public/casos/andres-amazon.png` |
| `demo-br-portuguese@demo.bank` | Ana, two iFood charges | `web/public/casos/ana-ifood.png` |
| `demo-ar-fraud@demo.bank` | Martina, three ElectroMax charges in Córdoba | `web/public/casos/martina-electromax.png` |
| `demo-co-ambiguous@demo.bank` | Camilo, four charges on the same day | `web/public/casos/camilo-dia.png` |
| `demo-mx-own-purchase@demo.bank` | Diego, a Liverpool purchase from the app | `web/public/casos/diego-liverpool.png` |
| `demo-ar-reversed@demo.bank` | Sofía, a Mercado Libre charge already reversed | `web/public/casos/sofia-mercadolibre.png` |

Example, Lucía's duplicate Uber charge:

1. Sign in as `demo-mx-duplicate@demo.bank` with that same text as the password.
2. Attach `web/public/casos/lucia-uber.png`.
3. Write `no reconozco estas transacciones` and send.

The assistant should name the two Uber Trip charges of 312.40 MXN on 11 Jun 2026, at 09:00:00 and 09:00:04, and say they are 4 seconds apart. The same question works for the other seven images. For Ana, write `não reconheço estas transações`.


## Customers to try

The deployed demo has `*` in `DEMO_CUSTOMER_IDS`: the ID of any customer in the database signs in, with that same ID as the password. Many of the organizer's 150,000 customers are thin (no account with a balance, no recent purchase, or closed), and with those a screen comes back empty. These 25 were checked against the full dataset in Cloud SQL on 2026-10-05, and the chat field offers them:

| Customer ID (also the password) | Who | What to try |
|---|---|---|
| `DEMO-MX-KHIPU` | Valeria: two accounts, a credit card, a loan, three service bills | Khipear: `khipea 300 a mi tarjeta`, `pasa 500 de mi cuenta de ahorro a mi cuenta corriente`, `khipéale 200 a la cuenta 4000000033`, `paga la luz`. No purchases, so Mis finanzas is empty |
| `DEMO-MX-RECIBE` | Renata: one account in MXN (`4000000033`) and one in USD | The customer who receives. No card and no purchases |
| `DEMO-MX-DUPLICATE`, `DEMO-MX-FX`, `DEMO-CO-PENDING`, `DEMO-BR-PORTUGUESE`, `DEMO-AR-FRAUD`, `DEMO-CO-AMBIGUOUS`, `DEMO-MX-OWN-PURCHASE`, `DEMO-AR-REVERSED` | The eight customers of the table above (they also sign in by email): a credit card with about 30 purchases, a savings account, three service bills | Everything: the dispute of each case, Mis finanzas, paying the card or a bill |
| `CLI-35DQ8W3F31GF`, `CLI-T317OM6FPX6Q`, `CLI-VJ9MZ55A1TNX` | Organizer customers with the most to show: Carolina (Colombia, 5 accounts, 4 cards), Guadalupe Adriana (México, 2 accounts, 3 cards), Rosa (Argentina, 4 accounts, 1 card); 6 or 7 purchases in the last 90 days, in 4 or 5 categories | Everything, on the organizer's own data |
| `CLI-2HCAV5E4NFLH`, `CLI-714PN0OOE0WX`, `CLI-7LCAX6I6DX5F`, `CLI-9S264QYHP5E1`, `CLI-G3JO7K2GEVIF`, `CLI-MG4JR9V0OWYH`, `CLI-O4HNT6A74L3G`, `CLI-OHC9GVNM29TN`, `CLI-QAWTGLT3BESD`, `CLI-T2ZP6QXLFRLL`, `CLI-UJOW50WUBO63`, `CLI-XL20OA8V7GSM` | Organizer customers with an active account with a balance, a credit card with debt, 7 to 12 purchases in the last 90 days and three service bills | Everything |

Any other `CLI-...` ID signs in too, and money can be sent to any customer who has an active account in the same currency. What that customer sees depends on their data: without purchases in the last 90 days Mis finanzas says there is no spending, and without an account khipear answers that there is nothing to send from.


## If something fails

`make up` / `make smoke` print which piece failed:

| Message | Fix |
|---|---|
| `Ollama not found` | `brew install ollama` |
| `FAIL api` | Docker Desktop not running, or check `make logs` |
| `deps ... llm: error` | `make llm` |
| `deps ... db: error` | `make down && make up` |

