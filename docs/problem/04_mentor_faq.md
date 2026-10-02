# Mentor FAQ (official clarifications)

> Source: the hackathon Slack. Answers are quoted or closely paraphrased. Add new entries as they appear.

## Does the learned component have to be a model we train ourselves?

**No.** A model does not need to be trained from scratch.

> "A prompted or fine-tuned LLM can count as the learned component, as long as the team clearly defines what it's doing and evaluates it rigorously (and justifies it)."

The **baseline is not prescribed.** Rules, TF-IDF + Logistic Regression, a zero-shot LLM, or another justified reference are all acceptable.

> "The key is to compare the learned approach against the baseline on the same held-out data, with valid labels/ground truth and leakage prevention, so teams can demonstrate what the learned component actually adds."

— Antonio González Dumar (mentor)

## Is cloud deployment required?

**Not strictly.** Local tooling is fine if we clearly explain the path to production.

> "We care more about demonstrating a credible path to production, including scalability, reproducibility, monitoring, security, reliability, and the remaining work needed for deployment."
>
> "Cloud deployment can certainly help demonstrate those aspects, but we don't want cloud spend itself to be a barrier to participation. Remember we are not asking for a simple chatbot but a solution to a real problem."

— Antonio González Dumar (mentor)

**Our stance:** the submission form still asks for a deployed link, and "deployment" is part of the AI Engineering criterion. We will therefore deploy cheaply (free tier plus a reproducible `docker compose`) **and** document the target production architecture.

## How do we access the dataset?

The S3 connection parameters (read-only) are in the **updated** data dictionary PDF.

- Keep them in a local `.env`.
- Never commit them.
- Do not share them outside the hackathon.

— André R (organizer)
