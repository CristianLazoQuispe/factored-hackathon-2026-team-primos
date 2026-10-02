# Market Research: AI Customer Service and Agentic Banking (2024–2026)

> **Current proposal:** [10_proposal.md](10_proposal.md). This scan is reference material; cite sources from here in the pitch.

> Date: 2026-09-26. Produced by two independent research agents (Asia and West), using web searches.
> Items marked ⚠️ are unverified or come from secondary sources. Check them before quoting them in the pitch.

## Why this study

"Voice + image" is the obvious "wow" that many of the ~180 teams will try. We looked at what banks, fintechs, and super-apps across Asia, the US, the UK, Europe, and LATAM actually ship, to find non-obvious patterns worth bringing into one dispute-intake workflow.

---

## 1. Cross-cutting patterns

| # | Pattern | What it means for us |
|---|---|---|
| P1 | **The LLM interprets; deterministic systems act.** Seen at KakaoBank, Wells Fargo, Capital One, Decagon | The core architecture: typed proposals, a policy engine decides, the customer confirms, the ledger verifies |
| P2 | **Chasing "containment" backfires** (Klarna's reversal; CFPB's "doom loops" warning) | Report safe resolution and correct final state, not only containment |
| P3 | **Protective, reversible actions are instant; money-moving actions need step-up** (OCBC Money Lock, Singapore's kill switch, BOCHK cooling-off) | Authorization tiered by reversibility |
| P4 | **Regulation decides who pays** (Singapore SRF, UK APP reimbursement, Korea no-fault bill, EU PSR, Reg E, CONDUSEF) | Treat disputes as a legally timed process: a "dispute clock" encoded as rules |
| P5 | **Copilot for human agents, not replacement** (DBS CSO Assistant, China Merchants Bank "Human + Agent") | Put heavy investment in the human-agent console and the handoff |
| P6 | **Scam prevention is now the frontline of customer service** (Korea ASAP, KB × LG Uplus, Starling Scam Intelligence, NatWest Cora+) | Triage must tell unauthorized fraud apart from scams and confusion |
| P7 | **The bank must authenticate itself too** (GCash/Maya "we never ask for OTP"; Korean and Japanese impersonation waves) | Outbound "the bank calls you" looks like vishing. Invariant: never ask for OTP, card number, or links |
| P8 | **Customers' own AI agents are arriving** (Alipay AI Pay for agents, Google AP2, Visa Trusted Agent Protocol, Google "Ask for Me", Pine.ai) | Roadmap item: the same authorization layer can later serve delegated agents |
| P9 | **Evaluate by final state, not answer text** (Sierra τ-bench / τ²-bench, pass^k) | Our eval scores the resulting case/ledger state and repeated-run consistency |
| P10 | **The LLM never sees personal data** (Wells Fargo Fargo: 245M interactions, zero PII to the LLM) | Mask PII in prompts and logs; scope retrieval by session |

---

## 2. Asia

| Market | Precedent | Takeaway |
|---|---|---|
| **Korea** | KakaoBank AI Transfer (Nov 2025): the LLM fills a transfer form; confirmation and password happen outside the chat. Pen-tested with the Financial Security Institute | "The LLM fills forms, it never acts" |
| Korea | KB Kookmin × LG Uplus real-time voice-phishing detection; Samsung One UI 8 phishing detection | In-call scam interruption |
| Korea | ASAP anti-phishing platform (130 firms); 6 banks (including Toss) train a federated anti-phishing model | Shared fraud intelligence |
| Korea | No-fault voice-phishing reimbursement bill (2026): 50/50 split; banks exempt if they gave repeated warnings | Warnings shown are evidence that matters |
| **China** | Ping An: AI handled 80% of 2025 service volume (1.7B interactions); WeBank: 800+ AI agents | Scale benchmarks |
| China | China Merchants Bank "Human + Agent": an assistant for customers and a separate one for staff | Two-sided copilot |
| China | Alipay AI Pay (100M+ users), opened to third-party AI agents in Apr 2026; Ant × Google AP2; Alipay rebuilt around the "Abao" assistant (Jun 2026) | Agent-to-agent payments are already live at scale |
| China | WeBank Weilidai sign-language video service for hearing-impaired customers | Inclusion by design |
| **Japan** | ATMs that play a warning video when the camera sees a phone call; Osaka bans over-65s from phone calls at ATMs; lower withdrawal limits for elderly customers | Intervene at the physical moment of risk |
| Japan | SMBC trial of digital avatars in contact centers; MUFG × OpenAI | Avatars are being tried, but they are not the value |
| **Singapore** | MAS Shared Responsibility Framework (Dec 2024); OCBC Money Lock; 24/7 kill switch | Regulated, reversible protective actions |
| Singapore | DBS CSO Assistant: 500 officers, live transcription plus knowledge search, up to 20% shorter calls | Agent copilot with measured impact |
| **Hong Kong** | BOCHK 6-hour cooling-off after device changes; HKMA Charter 3.0 | Time-based safety envelopes |
| **Thailand** | Froze 3M+ mule accounts; tighter mobile transfer limits; SCB proactive "My Alert" | Proactive, rules-based protection |
| **Philippines** | Maya "scam inoculation" SMS campaign (2025); GCash warnings about AI-generated fake receipts | Fake receipts are a threat, so photo evidence needs verification |
| **SE Asia** | Grab "missing muffins": an LLM prices partial refunds; ~32k fewer manual tickets per month | Proportional resolution, with humans handling safety cases |
| **India** | RBI MuleHunter.AI (23 banks, 19 mule behaviours) | Network-level fraud signals |
| **Laos** | Little public detail on AI features (BCEL One, LaoQR); mostly phishing history | Low signal |

**Asia sources:**
- Korea:
  - [KakaoBank AI transfer](https://www.khan.co.kr/en/article/202511241639537)
  - [KB × LG Uplus](https://www.digitaltoday.co.kr/en/view/4317/kb-kookmin-bank-unveils-ai-based-real-time-voice-phishing-response-system-with-lg-uplus)
  - [Korea ASAP](https://www.koreatimes.co.kr/economy/policy/20251029/korea-launches-ai-based-platform-to-bolster-fight-against-voice-phishing)
  - [6-bank federated model](https://www.koreatimes.co.kr/www/biz/2025/02/602_392666.html)
  - [Korea no-fault 2026](https://www.seoulz.com/korea-voice-phishing-2026/)
  - [Samsung One UI 8](https://m.gsmarena.com/newscomm-68943.php)
- Singapore and Hong Kong:
  - [MAS SRF](https://www.mas.gov.sg/regulation/guidelines/guidelines-on-shared-responsibility-framework)
  - [OCBC Money Lock](https://www.ocbc.com/personal-banking/security/security-advisories.page)
  - [DBS CSO Assistant](https://www.dbs.com/newsroom/DBS_empowers_its_Customer_Service_Officers_with_Gen_AI_powered_virtual_assistant_to_reduce_toil_and_enhance_customer_experience)
  - [HKMA Charter 3.0](https://www.hkma.gov.hk/eng/news-and-media/press-releases/2025/07/20250709-3/)
- China:
  - [CMB Human+Agent](https://finance.biggo.com/news/57e3291e-5a62-4f29-89bc-7648aeed0f64)
  - [Ping An 2025](https://group.pingan.com/media/news/2026/ar-25.html)
  - [WeBank](https://www.prnewswire.com/apac/news-releases/webank-wins-four-awards-from-the-asian-banker-gaining-international-recognition-for-its-digital-inclusive-finance-practices-302714473.html)
  - [Alipay AI Pay](https://fintechnews.hk/37526/fintechchina/alipay-ai-pay-120m-transactions/)
  - [Alipay for AI agents](https://www.businesswire.com/news/home/20260421171651/en/Alipay-AI-Pay-Launches-New-Service-Enabling-OpenClaw-type-AI-Agents-to-Make-Payments)
  - [Alipay Abao](https://www.caixinglobal.com/2026-06-17/ant-revamps-alipay-with-ai-assistant-in-biggest-app-overhaul-102454831.html)
  - [Ant × AP2](https://fintechmagazine.com/news/ant-international-partners-google-on-agent-payments-protocol)
- Japan:
  - [Japan ATM videos](https://soranews24.com/2024/02/25/atms-that-automatically-play-anti-fraud-videos-to-people-talking-on-mobile-phones-in-development/)
  - [Osaka ordinance](https://soranews24.com/2025/03/26/osaka-prefecture-bans-seniors-from-talking-on-the-phone-while-using-atms/)
  - [SMBC avatars](https://www.cxtoday.com/contact-center/japanese-bank-smbc-trialing-customer-service-digital-avatars-in-contact-centers/)
  - [MUFG × OpenAI](https://openai.com/index/mufg/)
- Thailand, Philippines and SE Asia:
  - [Thailand transfer rules](https://www.bangkokpost.com/business/general/3089526/thailand-tightens-mobile-banking-transfer-limits)
  - [SCB](https://www.scb.co.th/en/about-us/news/oct-2025/scb-digital-ai-awards)
  - [Maya inoculation](https://insiderph.com/maya-flips-scam-playbook-with-holiday-sms-bait-to-inoculate-users)
  - [GCash fake receipts](https://mynt.com.ph/newsroom/gcash-warns-public-on-emerging-ai-generated-fake-receipts-scams-urges-users-to-always-check-transactions-tab)
  - [Grab missing muffins](https://www.grab.com/inside-grab/stories/how-we-taught-llms-to-solve-the-missing-muffins-mystery/)
- India:
  - [RBI MuleHunter.AI](https://www.medianama.com/2025/12/223-rti-23-banks-mulehunter-mule-accounts/)

---

## 3. USA, UK and Europe

| Market | Precedent | Takeaway |
|---|---|---|
| **Sweden (global)** | Klarna's AI did the work of ~700 agents (Feb 2024), then the CEO admitted "lower quality" and brought humans back (May 2025) | Containment is the wrong target |
| **US** | CFPB chatbot report: "doom loops" and wrong answers are supervision risks; 2024 signal to guarantee access to a human | Always offer a human path |
| US | Wells Fargo "Fargo": 245M interactions in 2024, zero PII sent to the LLM, all calculations on the bank's side | Blind LLM pattern |
| US | Capital One Chat Concierge: planner, validator and explainer agents; 5× lower latency | Validation step before acting |
| US | Bank of America Erica: 3B+ interactions; 50–60% start proactively | Proactive service at scale |
| US | Reg E §1005.11: 10 business days to investigate, or 45 with provisional credit; consumer has 60 days to report | Dispute deadlines as code |
| US | Sierra τ-bench / τ²-bench (final-state scoring, pass^k, dual control); Decagon "Agent Operating Procedures" (natural language compiled to deterministic workflows) | How to evaluate and structure agents |
| US | Google AP2 (signed mandates), Visa Trusted Agent Protocol (signed agent requests), Mastercard Agent Pay, Google "Ask for Me" | Customers' agents as a new channel; "know your agent" |
| US | Visa Compelling Evidence 3.0: 2+ earlier undisputed transactions matching on device/IP elements can defeat a friendly-fraud claim | Evidence rules can predict dispute outcomes |
| **UK** | APP scam reimbursement (Oct 2024): up to £85k, 50/50 split between sending and receiving banks; vulnerable customers are protected | Case type drives liability |
| UK | Starling Scam Intelligence (Oct 2025): upload an ad, AI flags scam signals; +300% payment cancellations in testing | AI scam checks before payment |
| UK | NatWest Cora+ × OpenAI (fraud and scam resolution); FCA AI Live Testing cohort (NatWest, Monzo) | Regulator-supervised AI rollout |
| **EU** | EU AI Act Art. 50 transparency ("you are talking to an AI"), applies from 2 Aug 2026 | Mandatory disclosure |
| EU | PSR/PSD3 political deal (Nov 2025): full refund for bank-impersonation scams; mandatory payee-name check | Bank-impersonation liability |
| **Germany / NL** | Commerzbank "Ava" avatar blocks and unblocks cards and changes limits; bunq Finn (~97% of support ⚠️, 38 languages, runs on Claude via Bedrock) | Avatars act through tools; multilingual support at scale |

**West sources:**
- Klarna and CFPB:
  - [Klarna (CX Dive)](https://www.customerexperiencedive.com/news/klarna-reinvests-human-talent-customer-service-AI-chatbot/747586/)
  - [Klarna (Forbes)](https://www.forbes.com/sites/quickerbettertech/2025/05/18/business-tech-news-klarna-reverses-on-ai-says-customers-like-talking-to-people/)
  - [CFPB chatbots](https://www.consumerfinance.gov/data-research/research-reports/chatbots-in-consumer-finance/chatbots-in-consumer-finance/)
  - [CFPB human access](https://www.consumerfinancemonitor.com/2024/08/13/cfpb-to-issue-proposal-to-make-it-easier-for-consumers-to-reach-real-person-when-seeking-assistance/)
- US banks and agent platforms:
  - [Wells Fargo Fargo](https://venturebeat.com/ai/wells-fargos-ai-assistant-just-crossed-245-million-interactions-with-zero-humans-in-the-loop-and-zero-pii-to-the-llm)
  - [Capital One](https://venturebeat.com/ai/how-capital-one-built-production-multi-agent-ai-workflows-to-power-enterprise-use-cases)
  - [BofA Erica](https://newsroom.bankofamerica.com/content/newsroom/press-releases/2025/08/a-decade-of-ai-innovation--bofa-s-virtual-assistant-erica-surpas.html)
  - [Decagon AOPs](https://decagon.ai/blog/from-sops-to-agent-operating-procedures)
  - [Sierra τ-bench](https://sierra.ai/blog/benchmarking-ai-agents)
  - [τ²-bench](https://arxiv.org/abs/2506.07982)
- US regulation and card rules:
  - [Reg E §1005.11](https://www.consumerfinance.gov/rules-policy/regulations/1005/11/)
  - [Reg E examiner guidance](https://www.consumercomplianceoutlook.org/2025/third-issue/error-resolution-under-regulation/)
  - [Visa CE 3.0](https://www.chargeflow.io/blog/visa-compelling-evidence-3-0-explained)
- Agent payments and "know your agent":
  - [AP2](https://cloud.google.com/blog/products/ai-machine-learning/announcing-agents-to-payments-ap2-protocol)
  - [Visa TAP](https://usa.visa.com/about-visa/newsroom/press-releases.releaseId.21716.html)
  - [Visa/Mastercard agentic](https://www.digitalcommerce360.com/2025/10/16/visa-mastercard-both-launch-agentic-ai-payments-tools/)
  - [Gemini calls](https://techcrunch.com/2026/09/24/google-tests-letting-gemini-make-phone-calls-initially-for-us-pixel-owners/)
  - [Know your agent](https://www.americanbanker.com/opinion/ai-agents-are-going-to-test-the-limits-of-bank-compliance)
- UK:
  - [UK APP reimbursement](https://www.psr.org.uk/publications/policy-statements/ps247-faster-payments-app-scams-reimbursement-requirement-confirming-the-maximum-level-of-reimbursement/)
  - [Starling](https://www.starlingbank.com/news/scam-intelligence-launch/)
  - [NatWest Cora+](https://www.natwestgroup.com/news-and-insights/news-room/press-releases/ai-and-data/2025/mar/natwest-open-ai-collaborate-to-accelerate-cutting-edge-ai-transf.html)
  - [FCA AI Live Testing](https://www.fca.org.uk/news/press-releases/fca-announces-second-cohort-ai-live-testing)
- EU, Germany and Netherlands:
  - [EU AI Act Art. 50](https://digital-strategy.ec.europa.eu/en/faqs/transparency-obligations-under-article-50-ai-act)
  - [EU PSR deal](https://www.consilium.europa.eu/en/press/press-releases/2025/11/27/payment-services-council-and-parliament-agree-to-step-up-the-fight-against-fraud-and-increase-transparency/)
  - [Commerzbank Ava](https://www.commerzbank.de/group/newsroom/press-releases/avatar.html)
  - [bunq Finn](https://www.cxtoday.com/ai-automation-in-cx/bunq-finn-financial-ai-assistant/)

---

## 4. LATAM (our judges' home market)

| Market | Precedent | Takeaway |
|---|---|---|
| **Mexico** | BBVA México "Blue" replaced the phone keypad menu (IVR): >90% of calls handled, average service time from 4 min to under 1 | Local proof that AI-first contact centers work |
| Mexico | CONDUSEF: the bank has up to 45 days to rule on a disputed charge, or the claim counts as valid; no late fees or credit-bureau reports while it is open (⚠️ confirm the article number) | Dispute-clock rule for MX |
| **Colombia** | Superfinanciera SmartSupervision: complaints must be pushed to the regulator by REST API, in real time or the same day | The route to production includes regulatory reporting |
| **Argentina** | BCRA: 60 days to contest pull transfers; refund within 3 business days (⚠️ only partly confirmed) | Dispute-clock rule for AR |
| **Brazil** | Nubank: Pix via WhatsApp from voice, text, or image, tested with 2M customers | Why the Portuguese requirement matters |
| Brazil | Pix MED 2.0 (Resolução BCB 493/2025): customer self-service contest; blocks funds across up to 5 accounts; old recovery rate was 9.3% | Instant-payment reference. It does **not** apply to our card data, so do not model it |

**LATAM sources:**
- [BBVA Blue](https://www.bbva.com/es/mx/innovacion/bbva-mexico-adopta-inteligencia-artificial-generativa-para-transformar-la-atencion-a-clientes-y-eliminar-la-marcacion-por-tonos-ivr/)
- [CONDUSEF (Infobae)](https://www.infobae.com/mexico/2025/12/19/te-hicieron-un-cargo-no-reconocido-condusef-explica-como-reportarlo-y-cuando-deben-reembolsarte/)
- [SFC SmartSupervision](https://smart.superfinanciera.gov.co/)
- [BCRA claims](https://www.bcra.gob.ar/en/make-a-claim-to-the-central-bank-for-fraud-or-scam/)
- [Nubank Pix AI](https://tiinside.com.br/en/11/12/2024/nubank-amplia-servico-de-pix-com-ia-generativa-para-app-e-whastapp/)
- [Pix MED 2.0](https://blog.starkbank.com/med-pix-2-0-mecanismo-especial-de-devolucao-o-guia-definitivo/)

---

## 5. Caveats

- **Unverified figures.** The "−22% CSAT" figure for Klarna and bunq's 97% come from secondary sources. The Air Canada Moffatt case (2024, the airline was held to its chatbot's promise) was cited from memory, not from a search. The CONDUSEF and BCRA details need checking against primary sources.
- **Laos coverage.** Little public information exists on AI features at BCEL One or LaoQR.
- **Regulatory rules.** Any rule we encode must cite its primary source and be labeled **illustrative, not legal advice**.
