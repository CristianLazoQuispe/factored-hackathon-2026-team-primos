# Forced-Divergence Ideas

> **Current proposal:** [10_proposal.md](10_proposal.md). RASTRO came out of this doc, trimmed to 3 checks (duplicate, pending, FX); the outbreak radar and merchant confusion were cut.

> Date: 2026-09-26. Status: **exploration, pending team vote and the day-1 signal census.**
> Why: team feedback said "LLM at the edges + deterministic rules" is standard banking practice, not disruptive (see [06](06_disruptive_concepts_debate.md)). Three independent brainstormers were each given one lens and a **ban list** of everything already proposed: rules architecture, voice, OCR, proactive outreach, console, red-team arena, simulator, regulation-as-code, autonomy levels, promise ledger, replay, cloning the best agent, accent matching, agent gateway, avatars.

## 1. The convergence

All three lenses, working independently, landed on the same core insight:

> **"Before asking the customer to prove anything, the bank investigates itself. Often the answer is already in its own data."**

| Lens | How it reached the insight |
|---|---|
| Inversion | **"Culpa Nuestra"**: the bot first checks whether the bank caused the problem (duplicate charge, failed reversal, app error) and admits it, with proof |
| Data insight | **"Half of disputes are explanations the bank already has"**: a pending charge that will reverse on its own, an FX difference, which decline the customer means |
| Cross-industry | **RASTRO**: "You don't know which charge it was. We do." The bank locates the transaction from a vague description (a robotics particle filter) |

## 2. Unified concept: RASTRO, the bank investigates itself first

*"Rastro"* means trace / track in both Spanish and Portuguese.
**Tagline:** *"Tú no sabes cuál fue. Nosotros sí." / "Você não sabe qual foi. Nós sabemos."*

A dispute-intake system that goes from a vague complaint to an explained, resolved, or tracked case in under a minute:

1. **Localize.** The customer says something vague ("cobraram umas coisas estranhas semana passada, tipo um Uber"). A belief over their recent transactions narrows with each sentence (the robotics particle-filter analogy). The system asks the single most informative question. The top candidates appear as cards and the customer swipes to confirm.
   - **Learned component:** a model that scores how likely a sentence refers to each transaction, vs. a keyword + date-rule baseline.
   - **Metrics:** top-1 accuracy and turns to identify the transaction.
2. **Self-investigate.** Before opening a case, the system checks the bank's own tables for an explanation. All checks are deterministic, verified queries:
   - **Bank error:** duplicate charge (same merchant, amount, and seconds apart); failed reversal; app error in the same session. → *"You're right, it was our error. The second charge is already being reversed."*
   - **Pending, will reverse on its own:** a model of how long transactions take to go from pending to settled or reversed. → *"91% of holds like this release within 48 h. If it posts, the dispute opens automatically."*
   - **FX difference:** a daily exchange-rate breakdown. → *"The USD/MXN rate moved 4.3% between Tuesday and Friday."*
   - **Merchant name confusion:** matching the merchant against the customer's own history. → *"It's Spotify. You've paid it every 12th since March 2024."*
   - **Outbreak:** many customers disputing the same merchant (a statistical scan over space and time). → *"212 similar reports; your case is already pre-filled."*
3. **Forecast.** A calibrated probability of approval plus a date, shown as a weather card: *"82% · by Thursday."* Evaluated against base rates with a reliability diagram.
4. **Settle or track.**
   - Small, low-risk claims can be refunded immediately when investigating would cost more than paying. That decision and the payment run outside the LLM, capped by policy.
   - Every other case gets a delivery-style tracking link.
   - Fraud signals, high amounts, or low confidence go to a human with the case file.

**Why it's different:**
- **Every other dispute bot interrogates the customer; this one interrogates the bank.**
- It turns the "ambiguous case" requirement into the headline, and the demo gets better the vaguer the judge types.
- It has a P&L story: disputes avoided, early settlements, money saved.
- The "rules architecture" is still there underneath, as an entry ticket, not the pitch.

**Safety metrics that come from the idea itself:**
- **False-concession rate:** the bank admitted fault when it wasn't at fault.
- **Missed-fraud rate:** the system said "it's just Spotify" when it was fraud.
- **Wrong-wait rate:** the system said "it will reverse" and it didn't.

## 3. Other strong ideas (by lens)

**Inversion:**
- **"La llamada que no vendrá":** answer the question plus the follow-up the customer would call about next week. Evaluated by 7-day repeat-contact rate.
- **"El cliente es el bug":** calls caused by app errors are also billed to the product team as a bug with a price, e.g. *"v4.2.1 Payments screen → 11,300 calls → $X."*
- **"Te pagamos tu tiempo":** settle before the formal complaint.
- **"No hoy, sí el 14 de marzo":** for credit rejections, tell the customer exactly what to change and by when.

**Data insight:**
- **"The 'resolved' flag lies":** train on what actually happened next (a recontact or a complaint), not the agent's flag. E.g. *"Resolved per agent 78% → actually resolved 51%."* This is Factored's "your labels are wrong" pitch.
- **"The first call lies":** contact-reason journeys reveal hidden disputes (show it as a Sankey diagram).
- **Compensation depends on how loud the customer is:** check whether compensation tracks merit or loudness, and use it as a fairness audit.

**Cross-industry:**
- **ER triage queue:** a harm-based acuity score instead of first-in, first-out.
- **F1 "tire wear" of patience:** hand off one lap before the customer's patience fails.
- **CV "spending fingerprint":** the customer's history as an image, with the anomalous charge glowing (Grad-CAM-style).
- **VAR evidence replay:** a phone pin in Medellín vs. a card pin in Cancún at 14:02.
- **Game save points:** resume a case across channel and language (ES on web → PT on mobile).

## 4. Day-1 signal census (mandatory before committing)

Synthetic generators often sample columns independently. For each candidate join:
1. Declare the lag window and the null (shuffled dates) in advance.
2. Measure lift against the null.
3. Put the results in one heatmap.

The heatmap doubles as a data-analytics slide ("how we found where the signal is").

| Check | Needed by |
|---|---|
| Duplicate charges (same merchant and amount within seconds) exist | Bank error |
| `transactions.status` shows Pending → Reversed/Approved over time | Will reverse on its own |
| Claimed vs. charged amount correlates with FX moves (ARS volatility) | FX explanation |
| Disputes cluster by merchant/geo/time beyond chance | Outbreak radar |
| Complaints can be linked to transactions (customer, product, date ±N, amount ≈ claimed) | Everything in dispute intake |
| `compensation_granted` depends on features (not random); amount vs. boolean | Forecast, early settlement |
| Recontact within 7 days contradicts `was_resolved` | "Resolved flag lies" |
| App `Error` events precede calls for the same customer | "The customer is the bug" |

**Rule:** keep only the parts of RASTRO whose signal survives. Each piece also has a fallback: if the data has no signal, it still works as a verified explanation tool, and we report the negative result honestly.

## 5. Proposed team split for RASTRO

| Member | Owns |
|---|---|
| Robotics | Localization engine: the belief over transactions, choosing the most informative question |
| GenAI/LLM | Bilingual language layer; evaluation set of vague descriptions in ES/PT |
| Finance | Self-investigation checks (FX, pending lifecycle, duplicates); forecast and settlement economics |
| CV / mechanical | Outbreak radar or spending fingerprint; demo visuals |
