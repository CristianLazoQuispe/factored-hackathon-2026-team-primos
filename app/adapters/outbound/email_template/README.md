# Email template

One layout and one generic Markdown template for every email quipu sends: a summary of balances, the
state of payments, the receipt of an inquiry, a blocked card, a transfer. The code chooses the data;
the look is decided here and nowhere else.

| File | What it is |
|---|---|
| `message.md` | The generic template: the slots every message can fill |
| `layout.html` | The frame: dark header with the logo, body, footer. Table-based, styles inline |
| `examples/*.md` | The template already filled, one per kind of message (Spanish, and one in Portuguese) |
| `assets/logo_email.png` | The logo cropped and sized for the header: 440 px wide, shown at 220 |
| `renderer.py` | A reference that turns a filled Markdown into HTML and plain text |
| `tests/test_email_template.py` | Tests of the template and of the safety of the renderer |
| `preview/` | How the examples look (drawn with an old WebKit: an approximation, not Gmail) |

## How a message is made

```
data (a dict)  ->  fill message.md  ->  Markdown  ->  HTML (layout.html)  +  plain text
```

The e-mail has two parts, `text/html` and `text/plain`, built from the same Markdown.

## Where the code uses it

Two kinds of message are connected to the code; the others still go as plain text.

| Message | Content (pure, `app/domain/email_content.py`) | Sent by |
|---|---|---|
| Summary of balances | `balances_content` | the `send_summary_email` action, topic `balances` |
| Receipt of a transfer or a payment | `transfer_receipt_content` | `app/adapters/inbound/confirmation_mail.py`, after the button |

The content is a small structure (title, intro, a big figure, sections of rows, a notice). The domain writes
the plain-text part from it (`content_text`, which is also what the outbox keeps); `compose.py` fills
`message.md` with it and makes the HTML; `mailer.py` sends both parts and attaches the logo
(`multipart/alternative` with a `multipart/related` that holds the page and `cid:quipu-logo`). If the page
cannot be made, the message goes as plain text.

To connect another message (the payment status, the case receipt): write its `*_content` function in
`email_content.py`, make the action or the route pass it as `content` in the `EmailDraft`, and add it to
`tests/test_email_connected.py`. Nothing in `compose.py` or the mailer changes.

## The slots of `message.md`

Written `{{ name }}`. A slot with no value is empty. A block between `<!-- if:name -->` and
`<!-- endif -->` appears only if the slot has a value; `<!-- unless:name -->` ... `<!-- endunless -->`
is the opposite.

| Slot | What goes there |
|---|---|
| `kind` | `balances`, `payment_status`, `case_receipt`, `card_blocked`, `transfer_receipt`, `movements`... Only for the code and for statistics: it changes nothing in the look |
| `language` | `es` or `pt`. Chooses the footer. Any other falls back to Spanish |
| `subject` | The subject of the email. Plain text |
| `preheader` | The line the inbox shows beside the subject. Invisible in the message |
| `eyebrow` | The small label above the title ("Resumen de saldos") |
| `title` | The title, one line |
| `first_name` | Optional. With it the greeting is "Hola Ana,", without it "Hola," |
| `intro` | One or two sentences that say why the customer gets this |
| `highlight_label` | The label of the big figure ("Monto transferido") |
| `highlight_value` | The big figure. If empty, the panel does not appear |
| `items_title` | A small heading above the list of rows ("Detalle", "Tarjetas") |
| `items` | **Markdown written by the code**: the rows (see below) |
| `table` | **Markdown written by the code**: a table, for lists of movements |
| `notice` | A warning or a reminder, in the amber panel |
| `button_label` | The text of the button |
| `button_url` | Where it goes. Only `http` and `https`; any other and the button does not appear |
| `closing` | **Markdown written by the code**: a last paragraph, if the message needs one |

## The Markdown of a message

Only this is understood; everything else is shown as plain paragraphs.

| You write | It becomes |
|---|---|
| `# Title` | The title (the first `#`) |
| `## Section` | A small grey heading |
| a paragraph | A paragraph |
| `- **Label**: value` | A row: label on the left, value in bold on the right |
| the next line, indented, in a row | A smaller grey detail under the label |
| `> [!HIGHLIGHT] Label \| Value` | The panel with a big figure |
| `> [!NOTICE] Text` | The amber panel |
| `> [!BUTTON] Text \| https://url` | The button |
| a Markdown table | A table; `---:` aligns a column to the right |
| `---` | A line |

## What the code must do

1. **Escape every value that comes from data** before it goes into Markdown (`md_escape`): a merchant called
   `**Uber**` or `[click](http://...)` must be shown as it is. The slots `items`, `table` and `closing`
   are Markdown the code wrote; the values inside them must be escaped the same way.
2. **Never let raw HTML through.** The renderer switches it off; keep it off.
3. **Send both parts**, HTML and plain text.
4. **Deliver the logo so Gmail shows it.** Gmail does not show images given as `data:` addresses. Two ways:
   attach it inline (`multipart/related`, with `Content-ID: <logo>` and `src="cid:logo"`), or serve it from a
   public address of the web (`https://.../logo_email.png`). The first needs no public file; the second makes
   a lighter message. In the layout, `{{ logo_src }}` takes either.
5. **Keep `demo=True` while the data is synthetic.** It adds the line "Mensaje de demostración con datos
   sintéticos" to the footer.
6. **Say what is true.** The wording of a message must not promise more than the system did: "queda
   bloqueada" only after the system read it back; "aceptado por el servidor" is not "entregado".

## About e-mail clients

- The layout uses tables and inline styles because many clients ignore everything else. It is built for a
  light page; it declares `color-scheme: light only`, so a client that darkens messages may still change
  colours. The header keeps its own dark band, so the logo always sits on its own background.
- Rounded corners and some spacing are ignored by older Outlook; the message stays readable.
- The previews in `preview/` were drawn with an old WebKit, close to a demanding client but not one. Send
  the messages to a real Gmail and to a phone before trusting the look.
- Colours: header `#061319`, green `#60C0B4`, text `#28383F`, titles `#061319`, panel `#EAF6F4`, warning
  `#FFF6E0`. They come from the logo.

## Tests

```bash
uv run pytest tests/test_email_template.py tests/test_email_connected.py
```

The first is the template and the safety of the renderer; the second is the template connected to the code
(see above). `tests/test_email_connected_sql.py` needs Postgres.
